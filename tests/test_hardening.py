"""Validation of the catalog commands: set/unset, malformed files, specs and tag names."""

import json

import pytest
from conftest import spec
from test_agent import record

from hist import catalog
from hist.cli import main


def write_catalog(env, records):
    env.home.joinpath("tracks.json").write_text(json.dumps({"format": 2, "tracks": records}))


@pytest.fixture
def two(env):
    write_catalog(env, [record("Best Of", "One", 1), record("Best Of", "Two", 2)])
    return env.config()


# -- set and unset use the rules of 'catalog edit'


def test_set_refuses_a_track_number_that_is_not_a_number(two):
    with pytest.raises(catalog.CatalogError, match="3 of 12"):
        catalog.set_tag(two, "best", "TrackNumber", "abc")
    assert catalog.check(two) == []
    assert not (two.state / "backups").exists()


def test_set_refuses_a_bad_release_date_and_a_duplicate_track(two):
    with pytest.raises(catalog.CatalogError, match="2001:02:03"):
        catalog.set_tag(two, "best", "ContentCreateDate", "2001-02-03")
    with pytest.raises(catalog.CatalogError, match="same album, disc and track"):
        catalog.set_tag(two, "best", "TrackNumber", "2 of 2", track=1)
    with pytest.raises(catalog.CatalogError, match="required"):
        catalog.set_tag(two, "best", "Title", None)


def test_set_and_unset_still_change_tags(two):
    assert catalog.set_tag(two, "best", "genre", "Soul") == ("Best Of", 2, 2)
    assert catalog.set_tag(two, "best", "Genre", "Soul")[1] == 0
    assert catalog.set_tag(two, "best", "Genre", None, track=1)[1:] == (1, 1)
    tags = [r["tags"].get("ItemList:Genre") for r in catalog.read_records(two)]
    assert tags == [None, "Soul"]


# -- tag names


def test_short_tag_uses_the_stored_spelling_of_known_names():
    assert catalog.short_tag("genre") == "ItemList:Genre"
    assert catalog.short_tag("ITEMLIST:albumartist") == "ItemList:AlbumArtist"
    assert catalog.short_tag("itemlist:Genre") == "ItemList:Genre"
    assert catalog.short_tag("MyTag") == "ItemList:MyTag"
    assert catalog.short_tag("XMP:Rights") == "XMP:Rights"


def test_set_with_a_lowercase_name_does_not_create_a_second_tag(two):
    catalog.set_tag(two, "best", "genre", "Soul")
    for r in catalog.read_records(two):
        assert r["tags"]["ItemList:Genre"] == "Soul"
        assert "ItemList:genre" not in r["tags"]


# -- malformed files


def raw(env, text):
    env.home.joinpath("tracks.json").write_text(text)


@pytest.mark.parametrize(
    "text",
    [
        "{not json",
        "[]",
        '{"format": 2}',
        '{"format": 2, "tracks": [1]}',
        '{"format": 2, "tracks": [{"file": "a"}]}',
        '{"format": 2, "tracks": [{"file": "a", "tags": {"ItemList:Album": 3}, "blobs": {}}]}',
        '{"format": 2, "tracks": [{"file": "a", "tags": {}, "blobs": []}]}',
    ],
)
def test_malformed_tracks_json_raises_a_catalog_error(env, text):
    raw(env, text)
    with pytest.raises(catalog.CatalogError):
        catalog.read_records(env.config())
    [problem] = catalog.check(env.config())
    assert problem.startswith("tracks.json")


def test_a_record_without_an_album_does_not_crash_selection(env):
    bad = record("Best Of", "One", 1)
    del bad["tags"]["ItemList:Album"]
    write_catalog(env, [bad, record("Best Of", "Two", 2)])
    cfg = env.config()
    records = catalog.read_records(cfg)
    assert catalog.select_album(records, "best") == "Best Of"
    assert catalog.pick_records(records, "Best Of", None, None)
    assert any("Album is missing" in p for p in catalog.check(cfg))


def test_check_reports_a_track_number_that_is_not_a_number(env):
    bad = record("Best Of", "One", 1)
    bad["tags"]["ItemList:TrackNumber"] = "abc"
    write_catalog(env, [bad, record("Best Of", "Two", 2)])
    assert any("is not a number" in p for p in catalog.check(env.config()))


def test_remove_album_reports_a_malformed_dates_file(env):
    write_catalog(env, [record("Best Of", "One", 1)])
    env.home.joinpath("dates.json").write_text("{oops")
    with pytest.raises(catalog.CatalogError, match="dates.json"):
        catalog.remove_album(env.config(), "best")


def test_the_cli_checks_a_broken_catalog_without_a_traceback(env, capsys):
    raw(env, "{not json")
    assert main(["--home", str(env.home), "catalog", "check"]) == 1
    assert "tracks.json" in capsys.readouterr().out


# -- specs


def good_spec():
    return spec("First Album", "Band", "2001-02-03", ["One", "Two"])


def test_a_good_spec_passes_the_check():
    catalog.check_spec(good_spec())


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda s: s["tracks"][1].update(track=1), "listed twice"),
        (lambda s: s["tracks"][1].update(disc=2), "more than the 1 discs"),
        (lambda s: s.update(release="2001-13-01"), "release"),
        (lambda s: s.update(release="2001-2-3"), "release"),
        (lambda s: s.update(discs=0), "discs"),
        (lambda s: s["tracks"][0].update(track=0), "at least 1"),
        (lambda s: s["tracks"][0].pop("title"), "title missing"),
        (lambda s: s.update(album=""), "album"),
    ],
)
def test_a_bad_spec_is_rejected(change, message, env, tmp_path):
    s = good_spec()
    change(s)
    with pytest.raises(catalog.CatalogError, match=message):
        catalog.add_spec(env.config(), s, tmp_path, dry_run=True)


def test_an_album_of_another_artist_is_not_replaced(env, tmp_path):
    write_catalog(env, [record("First Album", "One", 1, artist="Someone Else")])
    before = env.home.joinpath("tracks.json").read_text()
    with pytest.raises(catalog.CatalogError, match="Someone Else"):
        catalog.add_spec(env.config(), good_spec(), tmp_path)
    assert env.home.joinpath("tracks.json").read_text() == before
