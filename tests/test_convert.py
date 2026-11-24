import logging
import os

import pytest
from conftest import needs_tools, spec

from hist import catalog, convert, media, state, tags
from hist.log import log

pytestmark = needs_tools


def setup_album(
    env, album="Hits", folder="Hits (Remastered)", titles=("Uno", "Dos", "Tres"), catalog_titles=("One", "Two", "Three")
):
    d = env.download(folder, folder, "Band", list(titles))
    env.add_album(spec(album, "Band", "2001-01-01", list(catalog_titles)), d)
    return d


def test_convert_writes_exact_tags_and_removes_flac(env):
    d = setup_album(env)
    flac_md5 = {p.name: media.pcm_md5(p) for p in d.glob("*.flac")}
    result = convert.run_once(env.config(), convert.Options())
    assert result.converted == 1
    assert not list(d.glob("*.flac"))
    names = sorted(p.name for p in d.glob("*.m4a"))
    assert names == ["01 One.m4a", "02 Two.m4a", "03 Three.m4a"]
    saved = {tags.pick(t.tags, "title"): t for t in catalog.load(env.config())}
    for t in tags.read_tracks(tags.find_tracks([d], "m4a")):
        ref = saved[tags.pick(t.tags, "title")]
        assert t.tags == ref.tags and t.blobs == ref.blobs
        assert "ItemList:Encoder" not in t.tags and "ItemList:Comment" not in t.tags
    assert sorted(flac_md5.values()) == sorted(media.pcm_md5(p) for p in d.glob("*.m4a"))
    assert "Hits" in state.converted(env.config().state).names()


def test_keep_flac_and_dry_run(env, caplog, monkeypatch):
    d = setup_album(env)
    monkeypatch.setattr(log, "handlers", [caplog.handler])  # the console handler exists only after main() ran
    with caplog.at_level(logging.INFO, logger="hist"):
        convert.run_once(env.config(), convert.Options(dry_run=True))
    assert len(list(d.glob("*.flac"))) == 3 and not list(d.glob("*.m4a"))
    assert "->  One" in caplog.text
    convert.run_once(env.config(), convert.Options(keep_flac=True))
    assert len(list(d.glob("*.flac"))) == 3 and len(list(d.glob("*.m4a"))) == 3


def test_stale_outputs_of_an_interrupted_run_are_replaced(env):
    d = setup_album(env)
    (d / "garbage.m4a").write_bytes(b"not audio")
    convert.run_once(env.config(), convert.Options())
    assert sorted(p.name for p in d.glob("*.m4a")) == ["01 One.m4a", "02 Two.m4a", "03 Three.m4a"]


def test_an_interrupted_album_is_resumed(env, monkeypatch):
    d = setup_album(env)
    real, calls = convert.process_file, []

    def stop_after_first(*args):
        if calls:
            raise convert.ConvertError("interrupted")
        calls.append(real(*args))

    monkeypatch.setattr(convert, "process_file", stop_after_first)
    with pytest.raises(convert.ConvertError):
        convert.run_once(env.config(), convert.Options())
    assert len(list(d.glob("*.flac"))) == 2 and len(list(d.glob("*.m4a"))) == 1
    monkeypatch.setattr(convert, "process_file", real)
    assert convert.run_once(env.config(), convert.Options()).converted == 1
    assert sorted(p.name for p in d.glob("*.m4a")) == ["01 One.m4a", "02 Two.m4a", "03 Three.m4a"]
    assert not list(d.glob("*.flac"))


def test_alias_and_renumber(env):
    d = env.download("Big Box", "Big Box", "Band", ["Live A", "Live B"], numbers=[89, 90], discs=[8, 8])
    env.add_album(spec("Live Night", "Band", "2012-09-18", ["Song A (Live)", "Song B (Live)"]), d)
    cfg = env.config(aliases={"Live Night": "Big Box"}, renumber={"Live Night": {"disc": 1, "offset": 88}})
    assert convert.run_once(cfg, convert.Options()).converted == 1
    assert sorted(p.name for p in d.glob("*.m4a")) == ["01 Song A (Live).m4a", "02 Song B (Live).m4a"]


def test_a_folder_of_a_longer_album_name_is_not_taken(env):
    short = env.download("Hits", "Hits", "Band", ["A", "B"], base_freq=500)
    env.add_album(spec("Hits", "Band", "2000-01-01", ["A", "B"]), short)
    longer = env.download("The Best Hits", "The Best Hits", "Band", ["C", "D"], base_freq=700)
    env.add_album(spec("The Best Hits", "Band", "2005-01-01", ["C", "D"]), longer)
    for p in short.glob("*.flac"):
        p.unlink()  # only the longer album's download is present
    result = convert.run_once(env.config(), convert.Options(only="Hits"))
    assert state.converted(env.config().state).names() == {"The Best Hits"}
    assert result.converted == 1


def test_low_disk_space_skips_the_album(env):
    d = setup_album(env)
    result = convert.run_once(env.config(min_free_gb=10**9), convert.Options())
    assert result.converted == 0 and result.low_disk
    assert len(list(d.glob("*.flac"))) == 3


def test_pending_lists_albums_not_yet_converted(env):
    setup_album(env)
    assert convert.pending(env.config()) == ["Hits"]
    convert.run_once(env.config(), convert.Options())
    assert convert.pending(env.config()) == []


def test_upper_case_flac_files_are_converted_and_stale_outputs_removed(env):
    d = setup_album(env)
    for p in list(d.glob("*.flac")):
        p.rename(p.with_suffix(".FLAC"))
    (d / "garbage.M4A").write_bytes(b"not audio")
    assert convert.run_once(env.config(), convert.Options()).converted == 1
    assert not [p for p in d.iterdir() if p.suffix.lower() == ".flac"]
    names = sorted(p.name for p in d.iterdir() if p.suffix.lower() == ".m4a")
    assert names == ["01 One.m4a", "02 Two.m4a", "03 Three.m4a"]


def test_a_folder_with_only_hidden_flac_files_does_not_fail_the_stale_check(env):
    d = env.downloads / "Band" / "Odd"
    d.mkdir(parents=True)
    (d / "a.m4a").write_bytes(b"x")
    (d / ".hidden.flac").write_bytes(b"x")
    assert convert.remove_stale_outputs(env.config(), [], set(), "") == 0


def test_conversion_writes_a_hidden_temporary_file_that_scans_ignore(env, monkeypatch):
    d = setup_album(env)
    seen = []
    real = media.alac_command

    def spy(source, out):
        seen.append(out)
        return real(source, out)

    monkeypatch.setattr(media, "alac_command", spy)
    convert.process_file(sorted(d.glob("*.flac"))[0], catalog.load(env.config())[0], env.config().covers, True)
    assert seen and seen[0].name.startswith(".")
    assert not [p for p in d.iterdir() if p.name.startswith(".")]


def test_stage_store_file_leaves_no_partial_copy(env):
    cfg = env.config(store_album="Hits", store_file="song.m4a")
    cfg.library.mkdir(parents=True, exist_ok=True)
    src = cfg.store_library_copy
    src.write_bytes(b"data")
    os.utime(src, (1, 1))
    assert convert.stage_store_file(cfg, set())
    assert cfg.store_staged.read_bytes() == b"data"
    assert [p.name for p in cfg.store_staged.parent.iterdir()] == ["song.m4a"]


def test_the_cleaned_store_copy_is_found_whatever_the_suffix_case(env):
    from hist import store

    cfg = env.config(store_album="Hits", store_file="song.m4a")
    cfg.store_staged.parent.mkdir(parents=True, exist_ok=True)
    (cfg.store_staged.parent / "song.M4A").write_bytes(b"x")
    (cfg.store_staged.parent / ".song.converting.m4a").write_bytes(b"x")
    assert store.cleaned_copy(cfg).name == "song.M4A"
