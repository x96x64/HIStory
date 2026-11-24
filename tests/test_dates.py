import datetime
import json
import os

import pytest
from conftest import needs_setfile

from hist import dates


def entry(kind, path, day):
    return {"kind": kind, "path": path, "date": datetime.datetime.strptime(day, "%Y-%m-%d")}


def test_shell_line_quotes_apostrophes():
    line = dates.shell_line(entry("album", "Band/It's Here", "1977-10-18"), __import__("pathlib").Path("/lib"))
    assert line.startswith("find '/lib/Band/It'\\''s Here' \\( -type d -o -name \"*.m4a\" -o -name \"*.m4v\" \\)")
    assert "touch -t 197710180000.00" in line and 'SetFile -d "10/18/1977 00:00:00"' in line
    artist = dates.shell_line(entry("artist", "Band", "1976-11-05"), __import__("pathlib").Path("/lib"))
    assert artist == (
        "[ -d '/lib/Band' ] && touch -t 197611050000.00 '/lib/Band' && "
        'SetFile -d "11/05/1976 00:00:00" -m "11/05/1976 00:00:00" \'/lib/Band\''
    )


def test_select_brings_the_artist_entry_along():
    all_entries = [
        entry("artist", "Band", "1976-11-05"),
        entry("album", "Band/One", "1977-01-01"),
        entry("album", "Band/Two", "1978-01-01"),
        entry("artist", "Other", "1990-01-01"),
    ]
    assert [e["path"] for e in dates.select(all_entries, "two")] == ["Band", "Band/Two"]


def test_dates_before_1970_are_refused(tmp_path):
    (tmp_path / "A").mkdir()
    with pytest.raises(dates.DatesError):
        dates.apply(entry("artist", "A", "1969-12-18"), tmp_path)


@needs_setfile
def test_apply_sets_folders_and_media_files_only(tmp_path):
    album = tmp_path / "Band" / "It's Here"
    (album / "sub").mkdir(parents=True)
    for name in ("01 a.m4a", "02 b.M4A", "notes.txt", "sub/03 c.m4v"):
        (album / name).write_bytes(b"x")
    doc = {
        "entries": [
            {"kind": "artist", "path": "Band", "date": "1976-11-05"},
            {"kind": "album", "path": "Band/It's Here", "date": "1977-10-18"},
        ]
    }
    (tmp_path / "dates.json").write_text(json.dumps(doc))
    all_entries = dates.entries(tmp_path / "dates.json")
    assert dates.apply_album("Band/It's Here", all_entries, tmp_path) == "dates set"
    when = datetime.datetime(1977, 10, 18).timestamp()
    for name in ("", "01 a.m4a", "sub", "sub/03 c.m4v"):
        st = os.stat(album / name)
        assert st.st_mtime == when and st.st_birthtime == when
    for name in ("02 b.M4A", "notes.txt"):
        assert os.stat(album / name).st_mtime != when
    assert os.stat(tmp_path / "Band").st_mtime == datetime.datetime(1976, 11, 5).timestamp()


@pytest.mark.parametrize(
    "text",
    [
        "{not json",
        "[]",
        '{"entries": 3}',
        '{"entries": [3]}',
        '{"entries": [{"kind": "album", "path": "A/B"}]}',
        '{"entries": [{"kind": "album", "path": "A/B", "date": "1977-13-45"}]}',
        '{"entries": [{"kind": "album", "path": "A/B", "date": "1969-01-01"}]}',
        '{"entries": [{"kind": "album", "path": "A/B", "date": 1977}]}',
    ],
)
def test_malformed_dates_json_is_a_dates_error(tmp_path, text):
    path = tmp_path / "dates.json"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(dates.DatesError):
        dates.entries(path)


def test_entries_reads_valid_file(tmp_path):
    path = tmp_path / "dates.json"
    path.write_text('{"entries": [{"kind": "artist", "path": "A", "date": "1977-01-02"}]}', encoding="utf-8")
    assert dates.entries(path)[0]["date"] == datetime.datetime(1977, 1, 2)


def test_commands_touch_each_item_once(tmp_path):
    (tmp_path / "A" / "B").mkdir(parents=True)
    (tmp_path / "A" / "B" / "1.m4a").write_text("x")
    cmds = dates.commands(entry("album", "A/B", "1977-01-02"), tmp_path)
    assert [c[0] for c in cmds] == ["touch", "SetFile"]
    assert cmds[0][3:] == [str(tmp_path / "A" / "B"), str(tmp_path / "A" / "B" / "1.m4a")]
    assert dates.commands(entry("artist", "A", "1977-01-02"), tmp_path)[0][3:] == [str(tmp_path / "A")]
