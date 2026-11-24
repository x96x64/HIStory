"""The commands for agents and scripts: --json output, catalog edit, cover, export, exact albums, dates set."""
import hashlib
import io
import json

import pytest

from conftest import Env, needs_tools, spec
from hist import catalog, retag, state
from hist.cli import main


def record(album, title, number, artist="A", total=2, disc="1 of 1"):
    return {"file": f"{artist}/{album}/{number:02d} {title}.m4a",
            "tags": {"ItemList:Title": title, "ItemList:Album": album, "ItemList:AlbumArtist": artist,
                     "ItemList:Artist": artist, "ItemList:Genre": "Pop", "ItemList:TrackNumber": f"{number} of {total}",
                     "ItemList:DiskNumber": disc, "ItemList:ContentCreateDate": "2000:01:01 00:00:00Z"},
            "blobs": {}}


@pytest.fixture
def home(tmp_path):
    assert main(["init"]) == 0
    records = [record("Best Of", "One", 1), record("Best Of", "Two", 2), record("Best Of Live", "Live", 1, total=1)]
    path = tmp_path / "home" / "tracks.json"
    path.write_text(json.dumps({"format": 2, "tracks": records}))
    return tmp_path / "home"


def tracks(home):
    return json.loads((home / "tracks.json").read_text())["tracks"]


def backups(home):
    folder = home / "state" / "backups"
    return sorted(p.name for p in folder.iterdir()) if folder.exists() else []


def run_json(capsys, *argv):
    code = main(list(argv))
    out = capsys.readouterr()
    return code, out.out, out.err


# ------------------------------------------------------------------ --json

def test_catalog_list_json(home, capsys):
    code, out, _ = run_json(capsys, "catalog", "list", "--json")
    assert code == 0
    albums = json.loads(out)["albums"]
    assert [a["name"] for a in albums] == ["Best Of", "Best Of Live"]
    assert albums[0] == {"name": "Best Of", "album_artist": "A", "release": "2000-01-01", "tracks": 2,
                         "folder": "A/Best Of"}


def test_catalog_show_json_and_exact(home, capsys):
    code, out, err = run_json(capsys, "catalog", "show", "best of", "--json", "--track", "2")
    assert code == 0 and json.loads(out)["tracks"][0]["track"] == 2          # an exact match wins over "Best Of Live"
    code, out, _ = run_json(capsys, "catalog", "show", "Best Of", "--json")
    doc = json.loads(out)
    assert doc["album"] == "Best Of" and [t["track"] for t in doc["tracks"]] == [1, 2]
    assert doc["tracks"][0]["tags"]["ItemList:Title"] == "One" and doc["tracks"][0]["blobs"] == {}


def test_substring_ambiguity_errors_and_exact_resolves_it(home, capsys):
    code, out, err = run_json(capsys, "catalog", "show", "of", "--json")
    assert code == 1
    error = json.loads(err)["error"]
    assert error["code"] == "catalog" and "must match exactly one album" in error["message"]
    code, out, err = run_json(capsys, "catalog", "show", "Best Of Liv", "--exact", "--json")
    assert code == 1 and "no album is named" in json.loads(err)["error"]["message"]
    code, out, _ = run_json(capsys, "catalog", "show", "Best Of Live", "--exact", "--json")
    assert code == 0 and json.loads(out)["album"] == "Best Of Live"


def test_errors_without_json_stay_plain(home, capsys):
    code, out, err = run_json(capsys, "catalog", "show", "nothing")
    assert code == 1 and err.startswith("hist: error:")


def test_dates_list_json_and_errors(home, tmp_path, capsys):
    (home / "dates.json").write_text(json.dumps({"entries": [{"kind": "artist", "path": "A", "date": "1990-01-01"}]}))
    code, out, _ = run_json(capsys, "dates", "list", "--json")
    assert code == 0
    assert json.loads(out) == {"entries": [{"kind": "artist", "path": "A", "date": "1990-01-01",
                                            "in_library": False}]}
    code, out, err = run_json(capsys, "dates", "check", "--json")
    assert code == 0 and json.loads(out)["ok"] is True or code == 1
    code, out, err = run_json(capsys, "dates", "apply", "--json")
    assert code == 2 and json.loads(err)["error"]["code"] == "usage"


def test_status_json(home, capsys):
    code, out, _ = run_json(capsys, "status", "--json")
    assert code == 0
    doc = json.loads(out)
    assert doc["total"] == 2 and [a["name"] for a in doc["albums"]] == ["Best Of", "Best Of Live"]
    assert set(doc["albums"][0]) == {"order", "release", "name", "status", "tracks", "music_tracks"}
    assert doc["albums"][0]["music_tracks"] is None


# ------------------------------------------------------------------- edit

def edit_file(tmp_path, operations):
    path = tmp_path / "ops.json"
    path.write_text(json.dumps(operations))
    return str(path)


def test_edit_applies_everything_in_one_write_and_one_backup(home, tmp_path, capsys):
    ops = [{"op": "set", "album": "Best Of", "track": 1, "tag": "Title", "value": "Uno"},
           {"op": "set", "album": "Best Of", "tag": "Genre", "value": "Soul"},
           {"op": "unset", "album": "Best Of", "disc": 1, "track": 2, "tag": "Genre"}]
    assert main(["catalog", "edit", edit_file(tmp_path, ops)]) == 0
    one, two, live = tracks(home)
    assert one["tags"]["ItemList:Title"] == "Uno" and one["tags"]["ItemList:Genre"] == "Soul"
    assert "ItemList:Genre" not in two["tags"] and live["tags"]["ItemList:Genre"] == "Pop"
    [name] = backups(home)
    assert name.endswith("-catalog-edit") and (home / "state" / "backups" / name / "tracks.json").exists()


def test_edit_dry_run_prints_a_diff_and_writes_nothing(home, tmp_path, capsys):
    before = (home / "tracks.json").read_text()
    ops = [{"op": "set", "album": "Best Of", "tag": "Genre", "value": "Soul"}]
    code, out, _ = run_json(capsys, "catalog", "edit", edit_file(tmp_path, ops), "--dry-run")
    assert code == 0 and "ItemList:Genre: Pop -> Soul" in out and "nothing was written" in out
    code, out, _ = run_json(capsys, "catalog", "edit", edit_file(tmp_path, ops), "--dry-run", "--json")
    report = json.loads(out)
    assert report["dry_run"] and report["tracks_changed"] == 2 and report["backup"] is None
    assert report["changes"][0]["changes"] == [{"tag": "ItemList:Genre", "before": "Pop", "after": "Soul"}]
    assert (home / "tracks.json").read_text() == before and backups(home) == []


def test_edit_reads_standard_input(home, monkeypatch, capsys):
    ops = [{"op": "unset", "album": "Best Of Live", "tag": "Genre"}]
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(ops)))
    assert main(["catalog", "edit", "-"]) == 0
    assert "ItemList:Genre" not in tracks(home)[2]["tags"]


def test_edit_validates_all_operations_before_writing(home, tmp_path, capsys):
    before = (home / "tracks.json").read_text()
    ops = [{"op": "set", "album": "Best Of", "tag": "Genre", "value": "Soul"},
           {"op": "set", "album": "Nope", "tag": "Genre", "value": "x"},
           {"op": "set", "album": "Best Of", "tag": "Comment", "value": "x"},
           {"op": "unset", "album": "Best Of", "tag": "Title"},
           {"op": "set", "album": "Best Of", "tag": "TrackNumber", "value": "three", "extra": 1},
           {"op": "set", "album": "Best Of", "track": 9, "tag": "Genre", "value": "x"}]
    code, out, err = run_json(capsys, "catalog", "edit", edit_file(tmp_path, ops), "--json")
    assert code == 1
    message = json.loads(err)["error"]["message"]
    for n in (2, 3, 4, 5, 6):
        assert f"operation {n}:" in message
    assert "operation 1:" not in message
    assert (home / "tracks.json").read_text() == before and backups(home) == []


def test_edit_rejects_a_result_with_duplicate_track_numbers(home, tmp_path, capsys):
    ops = [{"op": "set", "album": "Best Of", "track": 2, "tag": "TrackNumber", "value": "1 of 2"}]
    assert main(["catalog", "edit", edit_file(tmp_path, ops)]) == 1
    assert "same album, disc and track" in capsys.readouterr().err
    assert tracks(home)[1]["tags"]["ItemList:TrackNumber"] == "2 of 2"


def test_edit_rejects_bad_json_and_non_arrays(home, tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text("{oops")
    assert main(["catalog", "edit", str(bad)]) == 1
    bad.write_text('{"op": "set"}')
    assert main(["catalog", "edit", str(bad)]) == 1
    assert "JSON array" in capsys.readouterr().err


def test_edit_exact_flag_and_per_operation_exact(home, tmp_path, capsys):
    ops = [{"op": "set", "album": "Best Of Live", "tag": "Genre", "value": "Rock", "exact": True}]
    assert main(["catalog", "edit", edit_file(tmp_path, ops)]) == 0
    assert tracks(home)[2]["tags"]["ItemList:Genre"] == "Rock"
    ops = [{"op": "set", "album": "Best Of Liv", "tag": "Genre", "value": "Rock"}]
    assert main(["catalog", "edit", edit_file(tmp_path, ops), "--exact"]) == 1


def test_edit_retag_runs_retag_on_changed_album_folders(home, tmp_path, monkeypatch, capsys):
    library = tmp_path / "library"
    (library / "A" / "Best Of").mkdir(parents=True)
    (home / "config.toml").write_text(f'[paths]\nlibrary = "{library}"\n')
    calls = []
    monkeypatch.setattr(retag, "run", lambda *a: calls.append(a) or 0)
    ops = [{"op": "set", "album": "Best Of", "tag": "Genre", "value": "Soul"}]
    assert main(["catalog", "edit", edit_file(tmp_path, ops), "--retag"]) == 0
    [(cfg, roots, apply, fields, prune, verbose)] = calls
    assert roots == [library / "A" / "Best Of"] and apply is True and not fields and not prune
    assert main(["catalog", "edit", edit_file(tmp_path, ops), "--retag", "--json"]) == 2
    assert main(["catalog", "edit", edit_file(tmp_path, ops), "--retag", "--dry-run"]) == 2


# ------------------------------------------------------------------ cover

def test_cover_stores_the_image_by_hash_and_sets_it_on_the_album(home, tmp_path, capsys):
    png = b"\x89PNG\r\n\x1a\n" + b"data"
    path = tmp_path / "c.png"
    path.write_bytes(png)
    assert main(["catalog", "cover", "Best Of", str(path), "--exact"]) == 0
    digest = hashlib.sha256(png).hexdigest()
    one, two, live = tracks(home)
    assert one["blobs"] == two["blobs"] == {"ItemList:CoverArt": [digest]} and live["blobs"] == {}
    assert (home / "covers" / digest).read_bytes() == png
    assert backups(home)[0].endswith("-catalog-cover")
    assert main(["catalog", "cover", "Best Of", str(path), "--exact"]) == 0       # nothing to change
    assert len(backups(home)) == 1
    assert catalog.check(catalog_config(home)) == []
    path.write_bytes(b"text")
    assert main(["catalog", "cover", "Best Of", str(path), "--exact"]) == 1


def catalog_config(home):
    from hist import config
    return config.load(home)


# ------------------------------------------------------------------ export

def test_export_builds_a_spec_that_rebuilds_the_same_records(home, tmp_path, capsys):
    s = spec("Best Of", "A", "2000-01-01", ["One", "Two"])
    digest = hashlib.sha256(b"\xff\xd8\xff-cover").hexdigest()
    records = catalog.build_records(s, digest)
    records[1]["tags"]["ItemList:Copyright"] = "(P) Other"
    (home / "tracks.json").write_text(json.dumps({"format": 2, "tracks": records}))
    (home / "covers").mkdir(exist_ok=True)
    (home / "covers" / digest).write_bytes(b"\xff\xd8\xff-cover")
    out = tmp_path / "out" / "best.json"
    out.parent.mkdir()
    assert main(["catalog", "export", "Best Of", "-o", str(out)]) == 0
    assert capsys.readouterr().err == ""
    read = catalog.read_spec(out)
    assert catalog.build_records(read, digest) == records
    assert (tmp_path / "out" / "best-cover.jpg").read_bytes() == b"\xff\xd8\xff-cover"
    assert main(["catalog", "export", "Best Of"]) == 0
    assert json.loads(capsys.readouterr().out)["tracks"][1]["copyright"] == "(P) Other"


def test_export_warns_about_tags_a_spec_cannot_hold(home, capsys):
    data = tracks(home)
    data[0]["tags"]["ItemList:Lyrics"] = "la"
    (home / "tracks.json").write_text(json.dumps({"format": 2, "tracks": data}))
    assert main(["catalog", "export", "Best Of", "--exact"]) == 0
    assert "ItemList:Lyrics" in capsys.readouterr().err


@needs_tools
def test_export_then_add_into_a_fresh_home_gives_identical_tags(tmp_path):
    env = Env(tmp_path / "one")
    d = env.download("Store Name", "Store Name", "Band", ["Uno", "Dos", "Tres"])
    s = spec("First Album", "Band", "2001-02-03", ["One", "Two", "Three"], discs=2)
    s["tracks"][1]["composer"] = ""
    s["tracks"][2]["copyright"] = "(P) Other"
    env.add_album(s, d)
    out = tmp_path / "exported.json"
    assert main(["--home", str(env.home), "catalog", "export", "First Album", "-o", str(out)]) == 0
    fresh = tmp_path / "fresh"
    assert main(["--home", str(fresh), "init"]) == 0
    assert main(["--home", str(fresh), "catalog", "add", str(out), "--from", str(d)]) == 0
    assert catalog.read_records(env.config()) == json.loads((fresh / "tracks.json").read_text())["tracks"]


# ------------------------------------------------------------------- dates

def dates_doc(home):
    return json.loads((home / "dates.json").read_text())["entries"]


def test_dates_set_infers_the_kind_and_keeps_backups(home, capsys):
    assert main(["dates", "set", "A/Best Of", "2001-02-03"]) == 0
    assert main(["dates", "set", "A", "1990-01-01"]) == 0
    assert dates_doc(home) == [{"kind": "artist", "path": "A", "date": "1990-01-01"},
                               {"kind": "album", "path": "A/Best Of", "date": "2001-02-03"}]
    assert main(["dates", "set", "A/Best Of", "2002-02-03", "--kind", "album"]) == 0
    assert dates_doc(home)[1]["date"] == "2002-02-03"
    assert len([b for b in backups(home) if "-dates-set" in b]) == 3    # the repeat of a date writes nothing
    assert main(["dates", "set", "A/Best Of", "2002-02-03"]) == 0
    assert len([b for b in backups(home) if "-dates-set" in b]) == 3


def test_dates_set_validates_input(home, capsys):
    for argv in (["A", "2001-2-3"], ["A", "2001-13-01"], ["A", "1969-12-31"], ["A/B/C", "2001-01-01"],
                 ["../A", "2001-01-01"], ["A", "2001-01-01", "--kind", "album"], ["A/B", "2001-01-01", "--kind",
                                                                                   "artist"]):
        assert main(["dates", "set", *argv]) == 1, argv
    assert not (home / "dates.json").read_text().count("2001")
    assert main(["dates", "set", "A"]) == 2


def test_dates_unset(home, capsys):
    main(["dates", "set", "A", "1990-01-01"])
    assert main(["dates", "unset", "A"]) == 0
    assert dates_doc(home) == []
    assert main(["dates", "unset", "A"]) == 1
    capsys.readouterr()
    code, out, err = run_json(capsys, "dates", "set", "A", "1990-01-01", "--json")
    assert json.loads(out)["previous"] is None


# ------------------------------------------------------------------- lock

def test_writers_hold_the_catalog_lock(home, tmp_path, capsys):
    ops = edit_file(tmp_path, [{"op": "unset", "album": "Best Of", "tag": "Genre"}])
    held = state.Lock(home / "state", "catalog").acquire()
    try:
        for argv in (["catalog", "set", "Best Of", "Genre", "x"], ["catalog", "edit", ops],
                     ["catalog", "remove", "Best Of"], ["dates", "set", "A", "1990-01-01"]):
            code, out, err = run_json(capsys, *argv, "--json") if argv[0] == "dates" else run_json(capsys, *argv)
            assert code == 1 and "catalog is already running" in err
        assert main(["catalog", "edit", ops, "--dry-run"]) == 0                  # a dry run only reads
        assert main(["catalog", "list"]) == 0
    finally:
        held.release()
    assert main(["catalog", "edit", ops]) == 0


# ------------------------------------------------------------ discoverability and portability

def test_agent_help_matches_agents_md(capsys):
    from hist import agent
    assert main(["agent-help"]) == 0
    text = capsys.readouterr().out
    assert text == agent.agents_md()
    assert main(["agent-help", "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    blob = json.dumps(doc)
    for command in ("catalog edit", "catalog list", "dates set", "catalog cover", "catalog export", "--dry-run"):
        assert command in text and command in blob


def test_repo_guides_are_generated():
    from pathlib import Path
    from hist import agent
    root = Path(__file__).resolve().parent.parent
    assert (root / "AGENTS.md").read_text() == agent.agents_md(repository=True)
    assert (root / "CLAUDE.md").read_text() == "@AGENTS.md\n"


def test_init_writes_guides_without_overwriting(tmp_path):
    assert main(["init"]) == 0
    home = tmp_path / "home"
    assert (home / "CLAUDE.md").read_text() == "@AGENTS.md\n"
    assert "Editing Metadata with hist" in (home / "AGENTS.md").read_text()
    (home / "AGENTS.md").write_text("mine")
    assert main(["init"]) == 0
    assert (home / "AGENTS.md").read_text() == "mine"


def test_help_epilog_points_to_agents(capsys):
    with pytest.raises(SystemExit):
        main(["--help"])
    out = capsys.readouterr().out
    assert "--json" in out and "agent-help" in out and "--dry-run" in out


def test_no_prompts_in_source():
    from pathlib import Path
    import hist
    for path in Path(hist.__file__).parent.glob("*.py"):
        assert "input(" not in path.read_text().replace("stdin", ""), path


def test_edit_stdin_terminal_fails(home, monkeypatch, capsys):
    class Tty(io.StringIO):
        def isatty(self):
            return True
    monkeypatch.setattr("sys.stdin", Tty(""))
    code, out, err = run_json(capsys, "catalog", "edit", "--json")
    assert code == 2 and json.loads(err)["error"]["code"] == "usage"


def test_missing_home_says_init(tmp_path, capsys):
    code, out, err = run_json(capsys, "--home", str(tmp_path / "nowhere"), "catalog", "list")
    assert code == 2 and "hist init" in err and "HISTORY_HOME" in err


def test_ambiguous_album_lists_candidates_and_exact(home, capsys):
    code, out, err = run_json(capsys, "catalog", "show", "Best", "--json")
    assert code == 1
    msg = json.loads(err)["error"]["message"]
    assert "Best Of Live" in msg and "--exact" in msg


def test_edit_json_has_next(home, capsys, tmp_path):
    ops = tmp_path / "ops.json"
    ops.write_text(json.dumps([{"op": "set", "album": "Best Of Live", "tag": "Genre", "value": "Soul"}]))
    code, out, _ = run_json(capsys, "catalog", "edit", str(ops), "--json")
    doc = json.loads(out)
    assert code == 0 and doc["next"] and "retag" in doc["next"][0]


def test_catalog_check_and_doctor_json(home, capsys):
    code, out, _ = run_json(capsys, "catalog", "check", "--json")
    assert json.loads(out)["ok"] is True and code == 0
    code, out, _ = run_json(capsys, "doctor", "--json")
    doc = json.loads(out)
    assert set(doc) == {"ok", "checks", "info"}


def test_music_commands_fail_fast_off_macos(home, monkeypatch, capsys):
    monkeypatch.setattr("sys.platform", "linux")
    code, out, err = run_json(capsys, "refresh", "Best Of Live")
    assert code != 0 and "macOS" in err
    code, out, err = run_json(capsys, "catalog", "list", "--json")
    assert code == 0


def test_missing_tool_names_install_command(monkeypatch):
    from hist import proc
    monkeypatch.setattr("shutil.which", lambda name, *a, **k: None)
    with pytest.raises(proc.ToolError) as error:
        proc.which("ffmpeg")
    assert "ffmpeg" in str(error.value) and "brew install" in str(error.value)


def test_doctor_names_missing_tool(home, monkeypatch, capsys):
    monkeypatch.setattr("shutil.which", lambda name, *a, **k: None)
    code, out, _ = run_json(capsys, "doctor")
    assert code == 1 and "brew install ffmpeg" in out


def test_init_writes_commented_config(tmp_path):
    assert main(["init"]) == 0
    text = (tmp_path / "home" / "config.toml").read_text()
    assert text.count("#") > 5 and "downloads" in text
