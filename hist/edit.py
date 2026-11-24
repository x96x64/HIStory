"""Batch edits of the catalog's tags: 'hist catalog edit' reads a JSON array of operations.

Each operation is an object:

    {"op": "set", "album": "Album Name", "disc": 1, "track": 3, "tag": "Title", "value": "New Title"}
    {"op": "unset", "album": "Album Name", "tag": "Composer"}

"disc" and "track" are optional; without them the operation covers the whole album. "exact": true selects the
album by its exact name. Every operation is checked before anything is changed, and the whole batch is written
once, or not at all.
"""

import copy
import json
import re
from pathlib import Path

from hist import catalog, state
from hist.catalog import CatalogError
from hist.config import Config

KEYS = {"op", "album", "disc", "track", "tag", "value", "exact"}
NUMBER = re.compile(r"\d+( of \d+)?")
RELEASE = re.compile(r"\d{4}:\d\d:\d\d 00:00:00Z")


def load_operations(text: str) -> list[dict]:
    try:
        operations = json.loads(text)
    except json.JSONDecodeError as error:
        raise CatalogError(
            f"the operations are not valid JSON: {error}; see 'hist agent-help' for the format"
        ) from None
    if not isinstance(operations, list):
        raise CatalogError("the operations must be a JSON array of objects; see 'hist agent-help' for the format")
    return operations


def check_operation(op: object) -> list[str]:
    """The problems of one operation (an empty list when it is valid)."""
    if not isinstance(op, dict):
        return ["must be an object"]
    problems = [f"unknown key '{key}'" for key in sorted(set(op) - KEYS)]
    if op.get("op") not in ("set", "unset"):
        problems.append('\'op\' must be "set" or "unset"')
    if not isinstance(op.get("album"), str) or not op.get("album"):
        problems.append("'album' must be a non-empty string")
    if not isinstance(op.get("tag"), str) or not op.get("tag"):
        problems.append("'tag' must be a non-empty string")
    for key in ("disc", "track"):
        if key in op and (not isinstance(op[key], int) or isinstance(op[key], bool)):
            problems.append(f"'{key}' must be an integer")
    if "exact" in op and not isinstance(op["exact"], bool):
        problems.append("'exact' must be true or false")
    if op.get("op") == "set":
        if not isinstance(op.get("value"), str):
            problems.append("'value' must be a string")
        elif not op["value"]:
            problems.append("'value' must not be empty; use \"unset\" to remove a tag")
    elif op.get("op") == "unset" and "value" in op:
        problems.append("'unset' takes no 'value'")
    if problems or not isinstance(op.get("tag"), str):
        return problems
    tag = catalog.short_tag(op["tag"])
    if op["op"] == "set":
        if tag in catalog.PROTECTED_ADD:
            problems.append(f"{tag} is never stored in the catalog")
        elif tag in ("ItemList:TrackNumber", "ItemList:DiskNumber") and not NUMBER.fullmatch(op["value"]):
            problems.append(f"{tag} must look like '3 of 12'")
        elif tag == "ItemList:ContentCreateDate" and not RELEASE.fullmatch(op["value"]):
            problems.append(f"{tag} must look like '2001:02:03 00:00:00Z'")
    elif tag in catalog.PROTECTED_REMOVE:
        problems.append(f"{tag} is required on every track; use 'set' to change it")
    return problems


def plan(records: list[dict], operations: list) -> list[tuple]:
    """Check every operation against the records; returns [(operation, indexes of the tracks it covers)]."""
    problems, planned = [], []
    for number, op in enumerate(operations, 1):
        found = check_operation(op)
        if not found:
            try:
                album = catalog.select_album(records, op["album"], op.get("exact", False))
                picked = catalog.pick_records(records, album, op.get("disc"), op.get("track"))
                chosen = {id(p) for p in picked}
                planned.append((op, [i for i, r in enumerate(records) if id(r) in chosen]))
            except CatalogError as error:
                found = [str(error)]
        problems += [f"operation {number}: {text}" for text in found]
    if problems:
        raise CatalogError("\n".join(problems))
    return planned


def track_label(record: dict) -> dict:
    disc, number = catalog.record_number(record)
    return {
        "file": record["file"],
        "album": record["tags"]["ItemList:Album"],
        "disc": disc,
        "track": number,
        "title": record["tags"].get("ItemList:Title", ""),
    }


def changes(before: list[dict], after: list[dict]) -> list[dict]:
    """Per changed track: its label and the tags that differ, as {"tag", "before", "after"} (None = absent)."""
    out = []
    for old, new in zip(before, after, strict=False):
        diff = [
            {"tag": tag, "before": old["tags"].get(tag), "after": new["tags"].get(tag)}
            for tag in sorted(set(old["tags"]) | set(new["tags"]))
            if old["tags"].get(tag) != new["tags"].get(tag)
        ]
        if diff:
            out.append({**track_label(old), "changes": diff})
    return out


def compute(config: Config, operations: list, exact: bool = False) -> tuple:
    """Validate and apply the operations in memory; returns (old records, new records, changed tracks).

    Raises CatalogError, listing every problem found, when any operation is invalid or the result would have
    two tracks with the same album, disc and track.
    """
    if exact:
        operations = [{**op, "exact": True} if isinstance(op, dict) else op for op in operations]
    records = catalog.read_records(config)
    planned = plan(records, operations)
    new = copy.deepcopy(records)
    for op, indexes in planned:
        tag = catalog.short_tag(op["tag"])
        for i in indexes:
            if op["op"] == "set":
                new[i]["tags"][tag] = op["value"]
            else:
                new[i]["tags"].pop(tag, None)
    seen, problems = {}, []
    for r in new:
        key = (r["tags"]["ItemList:Album"], catalog.record_number(r))
        if key in seen:
            problems.append(f"{r['file']}: would have the same album, disc and track as {seen[key]}")
        seen[key] = r["file"]
    if problems:
        raise CatalogError("\n".join(problems))
    return records, new, changes(records, new)


def run(config: Config, operations: list, dry_run: bool, exact: bool = False) -> dict:
    """Apply a batch of operations (or, with dry_run, only compute it); returns the report.

    The report: {"dry_run", "operations", "tracks_changed", "changes", "folders", "backup"}. "folders" are the
    album folders, relative to the library, of the changed tracks.
    """
    old, new, found = compute(config, operations, exact)
    report = {
        "dry_run": dry_run,
        "operations": len(operations),
        "tracks_changed": len(found),
        "changes": found,
        "folders": sorted({c["file"].rsplit("/", 1)[0] for c in found}),
        "backup": None,
    }
    if found and not dry_run:
        backup = state.Backup(config.state, "catalog-edit")
        catalog.write_records(config, new, backup)
        report["backup"] = str(backup.folder())
    return report


def read_operations(source: str, stdin) -> list:
    """The operations from a file, or from stdin when source is '-'."""
    if source == "-":
        return load_operations(stdin.read())
    path = Path(source).expanduser()
    if not path.is_file():
        raise CatalogError(f"{path} is not a file; pass a JSON file, or '-' to read standard input")
    return load_operations(path.read_text(encoding="utf-8"))
