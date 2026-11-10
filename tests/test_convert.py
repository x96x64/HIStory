from conftest import needs_tools, spec
from history_music import catalog, convert, media, state, tags

pytestmark = needs_tools


def setup_album(env, album="Hits", folder="Hits (Remastered)", titles=("Uno", "Dos", "Tres"),
                catalog_titles=("One", "Two", "Three")):
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


def test_keep_flac_and_dry_run(env, capsys):
    d = setup_album(env)
    convert.run_once(env.config(), convert.Options(dry_run=True))
    assert len(list(d.glob("*.flac"))) == 3 and not list(d.glob("*.m4a"))
    assert "->  One" in capsys.readouterr().out
    convert.run_once(env.config(), convert.Options(keep_flac=True))
    assert len(list(d.glob("*.flac"))) == 3 and len(list(d.glob("*.m4a"))) == 3


def test_stale_outputs_of_an_interrupted_run_are_replaced(env):
    d = setup_album(env)
    (d / "garbage.m4a").write_bytes(b"not audio")
    convert.run_once(env.config(), convert.Options())
    assert sorted(p.name for p in d.glob("*.m4a")) == ["01 One.m4a", "02 Two.m4a", "03 Three.m4a"]


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
        p.unlink()                               # only the longer album's download is present
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
