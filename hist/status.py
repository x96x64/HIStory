"""One line per album, oldest release first: how far it has come (reads only)."""
import collections
from pathlib import Path

from hist import catalog, convert, matching, state
from hist.config import Config
from hist.log import emit_json
from hist.music_app import MusicApp


def run(config: Config, music: MusicApp | None, as_json: bool = False) -> int:
    all_albums = catalog.albums(config)
    converted = state.converted(config.state).names()
    added = state.added(config.state).load()
    folders = matching.scan(config.sources)
    listed = collections.Counter(a for a, _, _ in music.summary()) if music else None
    counts = collections.Counter()
    rows = []
    for order, album in enumerate(all_albums, 1):
        name = album["name"]
        if name in added:
            label = "in the library" + (f", {added[name].get('dates')}" if added[name].get("dates") else "")
        elif name in converted:
            label = "converted"
        elif all(Path(t.path).exists() for t in album["tracks"]):
            label = "in the library, not checked yet (run hist watch)"
        else:
            folder, why = convert.album_state(config, album, folders, all_albums)
            if folder is not None and not why:
                label = "downloaded, ready to convert" if folder.has_flac else "converted, ready to add"
            else:
                label = why
        counts[label.split(",")[0]] += 1
        in_music = listed.get(name, 0) if listed is not None else None
        rows.append({"order": order, "release": album["release"], "name": name, "status": label,
                     "tracks": len(album["tracks"]), "music_tracks": in_music})
    if as_json:
        emit_json({"albums": rows, "summary": dict(counts.most_common()), "total": len(all_albums)})
        return 0
    for row in rows:
        extra = f"  [Music: {row['music_tracks']}/{row['tracks']}]" if listed is not None else ""
        print(f"{row['order']:3d}  {row['release']}  {row['name'][:52]:52s}  {row['status']}{extra}")
    print(", ".join(f"{n} {k}" for k, n in counts.most_common()) + f" ({len(all_albums)} albums)")
    return 0
