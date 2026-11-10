"""Talking to the Music app with AppleScript (osascript).

hist never adds albums to the Music app; you add them yourself. Reading may launch the Music app. The commands that
change it on request (refresh, evacuate, store-entries --delete) say so in their help.
"""
import datetime
import subprocess
import time

from hist import proc
from hist.errors import HistError

QUERY = """on run argv
	set albumName to item 1 of argv
	set tb to tab
	set out to {}
	tell application "Music"
		set ts to (every track of library playlist 1 whose album is albumName)
		repeat with t in ts
			set loc to ""
			try
				set a to (get location of t)
				set loc to POSIX path of (a as alias)
			end try
			set end of out to ((database ID of t) as text) & tb & (name of t) & tb & (album of t) & tb & (album artist of t) & tb & (artist of t) & tb & ((track number of t) as text) & tb & ((disc number of t) as text) & tb & loc
		end repeat
	end tell
	set AppleScript's text item delimiters to linefeed
	return out as text
end run"""
# 'location of t' must be fetched before 'POSIX path of': written inline it stays a reference and fails.

SUMMARY = """tell application "Music"
	set a to album of every track of library playlist 1
	set k to kind of every track of library playlist 1
	set d to date added of every track of library playlist 1
end tell
set out to {}
repeat with i from 1 to count of a
	set x to item i of d
	set end of out to (item i of a) & tab & (item i of k) & tab & ((year of x) as text) & " " & (((month of x) as integer) as text) & " " & ((day of x) as text) & " " & ((time of x) as text)
end repeat
set AppleScript's text item delimiters to linefeed
return out as text"""

REFRESH = """on run argv
	tell application "Music"
		activate
		repeat with i in argv
			refresh (first track of library playlist 1 whose database ID is ((contents of i) as integer))
		end repeat
	end tell
end run"""

DELETE_ALBUM = """on run argv
	tell application "Music"
		activate
		delete (every track of library playlist 1 whose album is (item 1 of argv))
	end tell
end run"""

DELETE_IDS = """on run argv
	tell application "Music"
		activate
		repeat with i in argv
			try
				delete (first track of library playlist 1 whose database ID is ((contents of i) as integer))
			end try
		end repeat
	end tell
end run"""


class MusicError(HistError):
    pass


class MusicApp:
    """The Music app, through osascript."""

    def osa(self, script: str, *argv: str, timeout: int = 900) -> str:
        try:
            done = proc.run(["osascript", "-e", script, *argv], text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            raise MusicError("the Music app did not answer in time (is a permission prompt waiting?)") from None
        if done.returncode != 0:
            if any(code in done.stderr for code in ("(-609)", "(-600)", "(-1712)")):
                # -609 connection invalid, -600 not running, -1712 timed out
                raise MusicError("the Music app was quit or stopped responding while hist was using it. "
                                 "Open the Music app and run the command again; finished work is kept")
            raise MusicError("osascript failed: " + done.stderr.strip())
        return done.stdout.strip("\n")

    def tracks(self, album: str) -> list[dict]:
        rows = []
        for line in self.osa(QUERY, album).splitlines():
            parts = line.split("\t")
            if len(parts) == 8:
                rows.append({"id": parts[0], "name": parts[1], "album": parts[2], "album_artist": parts[3],
                             "artist": parts[4], "track": int(parts[5] or 0), "disc": int(parts[6] or 0) or 1,
                             "location": parts[7]})
        return rows

    def summary(self) -> list[tuple]:
        """(album, kind, date added) of every track in the library."""
        out = []
        for line in self.osa(SUMMARY).splitlines():
            album, kind, when = line.split("\t")
            year, month, day, seconds = (int(x) for x in when.split())
            out.append((album, kind, datetime.datetime(year, month, day) + datetime.timedelta(seconds=seconds)))
        return out

    def refresh(self, ids: list[str]) -> None:
        self.osa(REFRESH, *ids)
        time.sleep(3)

    def delete_album(self, album: str) -> None:
        self.osa(DELETE_ALBUM, album)

    def delete_ids(self, ids: list[str]) -> None:
        self.osa(DELETE_IDS, *ids)
