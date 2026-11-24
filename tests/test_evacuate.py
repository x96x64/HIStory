from hist import evacuate, music_app


class Music(music_app.MusicApp):
    def __init__(self):
        self.deleted = []

    def tracks(self, album):
        return [] if self.deleted else [{"album_artist": "Band", "location": "/x/Al/01.m4a"}]

    def delete_album(self, album, album_artist):
        self.deleted.append((album, album_artist))


def test_evacuate_moves_with_shutil_and_passes_the_artist(tmp_path, monkeypatch):
    moved = []
    monkeypatch.setattr(evacuate.shutil, "move", lambda a, b: moved.append((a, b)))
    item = {"order": 1, "album": "Al", "tracks": 1, "album_artist": "Band", "folders": ["/x/Al"]}
    monkeypatch.setattr(evacuate, "plan", lambda *a: [item])
    cfg = type("C", (), {"evacuation": tmp_path / "ev", "state": tmp_path / "state"})()
    monkeypatch.setattr(evacuate.state, "added", lambda p: type("A", (), {"remove": lambda self, a: None})())
    music = Music()
    assert evacuate.run(cfg, music, "", False) == 0
    assert str(moved[0][0]) == "/x/Al" and moved[0][1].name == "01 Al"
    assert music.deleted == [("Al", "Band")]


def fake_osa(monkeypatch, stdout):
    """Replace the guarded osa method (conftest makes it fail) by one that records its call."""
    seen = []
    monkeypatch.setattr(
        music_app.MusicApp, "osa", lambda self, script, *argv, **k: seen.append((script, argv)) or stdout
    )
    return seen


def test_tab_in_a_name_does_not_break_parsing(monkeypatch):
    s = music_app.SEP
    fake_osa(monkeypatch, s.join(["7", "Tab\tTitle", "Al\tbum", "Band", "Band", "3", "0", "/m/a.m4a"]) + "\n")
    row = music_app.MusicApp().tracks("Album")[0]
    assert row["name"] == "Tab\tTitle" and row["album"] == "Al\tbum" and row["track"] == 3


def test_summary_with_a_tab_in_the_album(monkeypatch):
    s = music_app.SEP
    fake_osa(monkeypatch, f"A\tB{s}AAC{s}2020 1 2 60\n")
    assert music_app.MusicApp().summary()[0][0] == "A\tB"


def test_delete_album_restricts_by_artist(monkeypatch):
    seen = fake_osa(monkeypatch, "")
    music_app.MusicApp().delete_album("Al", "Band")
    assert seen[0][1] == ("Al", "Band") and "album artist is (item 2 of argv)" in seen[0][0]
