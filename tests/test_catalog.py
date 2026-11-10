import hashlib
import json

import pytest

from conftest import make_cover, needs_tools, spec
from history_music import catalog, state


def write_records(env, records):
    env.home.joinpath("tracks.json").write_text(json.dumps({"format": 2, "tracks": records}))


def record(title, number):
    return {"file": f"A/B/{number:02d} {title}.m4a",
            "tags": {"ItemList:Title": title, "ItemList:Album": "Best Of", "ItemList:AlbumArtist": "A",
                     "ItemList:Artist": "A", "ItemList:Genre": "Pop", "ItemList:TrackNumber": f"{number} of 2",
                     "ItemList:DiskNumber": "1 of 1", "ItemList:ContentCreateDate": "2000:01:01 00:00:00Z"},
            "blobs": {}}


def test_set_and_unset_keep_history_and_guard_the_policy(env):
    write_records(env, [record("One", 1), record("Two", 2)])
    cfg = env.config()
    album, changed, n = catalog.set_tag(cfg, "best", "Genre", "Soul")
    assert (album, changed, n) == ("Best Of", 2, 2)
    assert list((cfg.state / "history").iterdir())
    assert catalog.set_tag(cfg, "best of", "Genre", "Rock", track=2)[1:] == (1, 1)
    with pytest.raises(catalog.CatalogError):
        catalog.set_tag(cfg, "best", "Comment", "no")
    with pytest.raises(catalog.CatalogError):
        catalog.set_tag(cfg, "best", "DiskNumber", None)
    with pytest.raises(catalog.CatalogError):
        catalog.set_tag(cfg, "nothing", "Genre", "Pop")


def test_check_reports_missing_tags_and_covers(env):
    bad = record("One", 1)
    del bad["tags"]["ItemList:DiskNumber"]
    bad["blobs"] = {"ItemList:CoverArt": ["0" * 64]}
    write_records(env, [bad, record("Two", 2)])
    problems = catalog.check(env.config())
    assert any("DiskNumber is missing" in p for p in problems)
    assert any("cover" in p for p in problems)


@needs_tools
def test_add_spec_uses_the_embedded_cover_or_a_given_one(env):
    d = env.download("Store Name", "Store Name", "Band", ["Uno", "Dos"])
    s = spec("First Album", "Band", "2001-02-03", ["One", "Two"])
    assert catalog.add_spec(env.config(), s, d) == 2
    records = catalog.read_records(env.config())
    assert [r["file"] for r in records] == ["Band/First Album/01 One.m4a", "Band/First Album/02 Two.m4a"]
    assert records[0]["tags"]["ItemList:ContentCreateDate"] == "2001:02:03 00:00:00Z"
    assert records[1]["tags"]["ItemList:TrackNumber"] == "2 of 2"
    digest = records[0]["blobs"]["ItemList:CoverArt"][0]
    assert (env.home / "covers" / digest).exists()

    other = make_cover(env.root / "blue.jpg", "blue")
    s2 = spec("Second: Album", "Band", "2002-01-01", ["One", "Two"])
    s2["cover"] = str(other)
    catalog.add_spec(env.config(), s2, d)
    second = [r for r in catalog.read_records(env.config()) if r["tags"]["ItemList:Album"] == "Second: Album"]
    assert second[0]["file"].startswith("Band/Second_ Album/")
    assert second[0]["blobs"]["ItemList:CoverArt"][0] != digest


@needs_tools
def test_specs_with_undecided_composers_are_refused(env):
    d = env.download("X", "X", "Band", ["Uno"])
    s = spec("X", "Band", "2001-01-01", ["One"])
    s["tracks"][0]["composer"] = None
    with pytest.raises(catalog.CatalogError):
        catalog.add_spec(env.config(), s, d)


A_COVER = hashlib.sha256(b"a").hexdigest()
B_COVER = hashlib.sha256(b"b").hexdigest()


def test_remove_album_cleans_every_file_of_the_catalog_folder(env):
    other = record("Hit", 1)
    other["file"] = "C/Other/01 Hit.m4a"
    other["tags"].update({"ItemList:Album": "Other", "ItemList:AlbumArtist": "C", "ItemList:TrackNumber": "1 of 1"})
    gone = [record("One", 1), record("Two", 2)]
    for r in gone:
        r["blobs"] = {"ItemList:CoverArt": [A_COVER]}
    other["blobs"] = {"ItemList:CoverArt": [B_COVER]}
    write_records(env, gone + [other])
    (env.home / "covers").mkdir()
    (env.home / "covers" / (A_COVER)).write_bytes(b"a")
    (env.home / "covers" / (B_COVER)).write_bytes(b"b")
    env.home.joinpath("dates.json").write_text(json.dumps({"entries": [
        {"kind": "artist", "path": "A", "date": "1990-01-01"},
        {"kind": "album", "path": "A/B", "date": "2000-01-01"},
        {"kind": "artist", "path": "C", "date": "1991-01-01"},
        {"kind": "album", "path": "C/Other", "date": "2001-01-01"}]}))
    cfg = env.config()
    state.added(cfg.state).add("Best Of", tracks=2)

    preview = catalog.remove_album(cfg, "best", dry_run=True)
    assert preview == {"album": "Best Of", "tracks": 2, "dates": ["A", "A/B"], "specs": [], "covers": [A_COVER]}
    assert len(catalog.read_records(cfg)) == 3

    catalog.remove_album(cfg, "best")
    assert [r["file"] for r in catalog.read_records(cfg)] == ["C/Other/01 Hit.m4a"]
    assert [e["path"] for e in json.loads(cfg.dates_file.read_text())["entries"]] == ["C", "C/Other"]
    assert not (cfg.covers / (A_COVER)).exists() and (cfg.covers / (B_COVER)).exists()
    assert "Best Of" not in state.added(cfg.state).names()
    kept = {p.name.split(".")[0] for p in (cfg.state / "history").iterdir()}
    assert {"tracks", "dates", A_COVER} <= kept
    assert catalog.check(cfg) == []


def test_remove_album_keeps_an_artist_entry_still_in_use(env):
    write_records(env, [record("One", 1), record("Two", 2)])
    env.home.joinpath("dates.json").write_text(json.dumps({"entries": [
        {"kind": "artist", "path": "A", "date": "1990-01-01"},
        {"kind": "album", "path": "A/B", "date": "2000-01-01"},
        {"kind": "album", "path": "A/Later", "date": "2005-01-01"}]}))
    removed = catalog.remove_album(env.config(), "best")
    assert removed["dates"] == ["A/B"]
