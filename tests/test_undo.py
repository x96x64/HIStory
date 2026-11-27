import hashlib
import json

import pytest
from test_agent import record

from hist import catalog, state
from hist import config as config_mod
from hist.cli import main


@pytest.fixture
def home(tmp_path):
    assert main(["init"]) == 0
    path = tmp_path / "home" / "tracks.json"
    path.write_text(json.dumps({"format": 2, "tracks": [record("Best Of", "One", 1), record("Best Of", "Two", 2)]}))
    return tmp_path / "home"


def genres(home):
    return [t["tags"].get("ItemList:Genre") for t in json.loads((home / "tracks.json").read_text())["tracks"]]


def test_undo_restores_the_newest_backup_and_a_second_undo_redoes_it(home, capsys):
    assert main(["catalog", "set", "best", "Genre", "Soul"]) == 0
    assert genres(home) == ["Soul", "Soul"]
    assert main(["catalog", "undo"]) == 0
    assert genres(home) == ["Pop", "Pop"]
    assert main(["catalog", "undo"]) == 0
    assert genres(home) == ["Soul", "Soul"]
    names = sorted(p.name for p in (home / "state" / "backups").iterdir())
    assert sum(n.endswith("-catalog-undo") or "-catalog-undo-" in n for n in names) == 2
    assert main(["catalog", "check"]) == 0


def test_undo_dry_run_changes_nothing_and_json_reports_the_files(home, capsys):
    main(["catalog", "set", "best", "Genre", "Soul"])
    capsys.readouterr()
    assert main(["catalog", "undo", "--dry-run", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["restored"] == ["tracks.json"] and report["dry_run"] is True and report["backup"] is None
    assert genres(home) == ["Soul", "Soul"]


def test_undo_without_a_backup_fails(home, capsys):
    assert main(["catalog", "undo"]) == 1
    assert "no backup" in capsys.readouterr().err


def test_undo_puts_back_covers_and_dates_of_a_removed_album(home):
    cover = b"picture"
    digest = hashlib.sha256(cover).hexdigest()
    records = json.loads((home / "tracks.json").read_text())["tracks"]
    records[0]["blobs"] = {"ItemList:CoverArt": [digest]}
    state.write_json(home / "tracks.json", {"format": 2, "tracks": records})
    (home / "covers").mkdir(exist_ok=True)
    (home / "covers" / digest).write_bytes(cover)
    state.write_json(home / "dates.json", {"entries": [{"kind": "album", "path": "A/Best Of", "date": "2000-01-01"}]})
    assert main(["catalog", "remove", "best of"]) == 0
    assert not (home / "covers" / digest).exists()
    assert main(["catalog", "undo"]) == 0
    assert (home / "covers" / digest).read_bytes() == cover
    assert len(json.loads((home / "dates.json").read_text())["entries"]) == 1
    assert len(catalog.read_records(config_mod.load(home))) == 2


def test_undo_refuses_a_damaged_backup_and_ignores_retag_backups(home):
    main(["catalog", "set", "best", "Genre", "Soul"])
    [backup] = (home / "state" / "backups").iterdir()
    (home / "state" / "backups" / "29990101-000000-retag").mkdir()
    (backup / "tracks.json").write_text("{broken")
    with pytest.raises(catalog.CatalogError, match="not valid JSON"):
        catalog.undo(config_mod.load(home))
    assert genres(home) == ["Soul", "Soul"]


def test_undo_refuses_a_backup_with_malformed_dates(home):
    main(["catalog", "set", "best", "Genre", "Soul"])
    [backup] = (home / "state" / "backups").iterdir()
    before = (home / "dates.json").read_bytes() if (home / "dates.json").exists() else None
    (backup / "dates.json").write_text(json.dumps({"entries": [{"kind": "album", "path": "A/B", "date": "bad"}]}))
    assert main(["catalog", "undo"]) == 1
    assert ((home / "dates.json").read_bytes() if (home / "dates.json").exists() else None) == before
    assert genres(home) == ["Soul", "Soul"]


def test_undo_removes_a_file_that_the_change_created_and_a_second_undo_brings_it_back(home, capsys):
    main(["catalog", "set", "best", "Genre", "Soul"])
    (home / "dates.json").unlink(missing_ok=True)
    assert main(["dates", "set", "A/Best Of", "2000-01-01"]) == 0
    assert (home / "dates.json").exists()
    capsys.readouterr()
    assert main(["catalog", "undo", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["removed"] == ["dates.json"] and report["restored"] == []
    assert not (home / "dates.json").exists()
    assert genres(home) == ["Soul", "Soul"]
    assert main(["catalog", "undo"]) == 0
    assert (home / "dates.json").exists()
    assert genres(home) == ["Soul", "Soul"]


def test_a_missing_file_is_kept_as_an_absent_marker(tmp_path):
    backup = state.Backup(tmp_path, "catalog")
    assert backup.keep(tmp_path / "dates.json") is None
    assert (backup.path / "dates.json.absent").is_file()
