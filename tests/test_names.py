import subprocess

import pytest

from hist import matching, music_app, proc, tags
from hist.tags import Track


def track(title, album="Album", artist="Artist", number="1 of 2", disc="1 of 1"):
    return Track(
        "/x/" + title,
        "/x",
        {
            "ItemList:Title": title,
            "ItemList:Album": album,
            "ItemList:AlbumArtist": artist,
            "ItemList:TrackNumber": number,
            "ItemList:DiskNumber": disc,
        },
        {},
    )


def test_norm_folds_case_width_accents_punctuation_and_article():
    assert tags.norm("The Café — ＡＢＣ!") == "cafe abc"
    assert tags.norm("") == ""


def test_similarity_substring_mode_accepts_a_contained_name():
    assert tags.similarity("hits", "best hits", "substring") >= 0.97
    assert tags.similarity("hits", "best hits", "similarity") < 0.9


def test_pairing_by_title_number_and_elimination():
    saved = [track("Song One", number="1 of 3"), track("Song Two", number="2 of 3"), track("Third", number="3 of 3")]
    current = [
        track("song one (remastered)", number="1 of 3"),
        track("Translated", number="2 of 3"),
        track("Other", number="9 of 3"),
    ]
    pairs, unmatched, number_only = matching.pair_tracks(saved, current, "substring", 0.9, 0.85)
    assert sorted(pairs) == [(0, 0), (1, 1), (2, 2)]
    assert not unmatched
    assert (2, 2) in number_only


def test_albums_are_sorted_by_release_then_name():
    a = track("x", album="B")
    a.tags["ItemList:ContentCreateDate"] = "2001:01:01 00:00:00Z"
    b = track("y", album="A")
    b.tags["ItemList:ContentCreateDate"] = "2001:01:01 00:00:00Z"
    c = track("z", album="C")
    c.tags["ItemList:ContentCreateDate"] = "1999:05:05 00:00:00Z"
    assert [x["name"] for x in matching.albums([a, b, c])] == ["C", "A", "B"]


def test_file_names_follow_disc_and_track(tmp_path):
    one = tmp_path / "download_123456.m4a"
    two = tmp_path / "other_654321.m4a"
    one.write_bytes(b"")
    two.write_bytes(b"")
    a = Track(
        str(one),
        str(tmp_path),
        {"ItemList:Title": "A/B: C?", "ItemList:TrackNumber": "3 of 9", "ItemList:DiskNumber": "1 of 1"},
        {},
    )
    b = Track(
        str(two),
        str(tmp_path),
        {"ItemList:Title": "Song", "ItemList:TrackNumber": "4 of 9", "ItemList:DiskNumber": "2 of 2"},
        {},
    )
    tags.clean_file_names([a, b])
    assert sorted(p.name for p in tmp_path.iterdir()) == ["03 A_B_ C_.m4a", "2-04 Song.m4a"]


def test_a_quit_music_app_gives_a_clear_error(monkeypatch):
    monkeypatch.undo()  # use the real osa, with osascript itself replaced
    monkeypatch.setattr(
        proc,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(
            a, 1, "", "114:172: execution error: Music got an error: Connection is invalid. (-609)"
        ),
    )
    with pytest.raises(music_app.MusicError, match="was quit"):
        music_app.MusicApp().tracks("Album")
