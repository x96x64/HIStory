# Troubleshooting

**A synced device shows an album with store artwork, the store's track list or another release's year.**
The files are not the cause when `hist verify --music` passes. Remove the album from the Music app
(`hist evacuate --album "Album Name"`), add it again yourself from the evacuation folder while `hist watch`
runs, and sync the device after each album, one album at a time in release order.

**The Music app shows a dialog while entries are deleted.**
Deleting an entry whose file still exists can ask whether to keep the file. `hist evacuate` moves the files away
first so that no dialog appears. If a dialog does appear, answer it yourself; `hist` never clicks it.

**"The Music app was quit or stopped responding while hist was using it."**
Commands that read or change the Music app need it running for their whole run. Open the Music app with the usual
library and run the command again; work already done is kept.

**The Music app refuses to switch libraries ("the current library is in use by a device").**
Eject the device in the Finder and disconnect it; if the device is shown in the Finder over Wi-Fi, turn that off
first. Then hold the Option key while opening the Music app to choose another library. Do not sync a device
while another library is open.

**A download does not start converting.**
Run `hist status`. A folder is used only when it holds as many FLAC files as the album has tracks, no
unfinished download files, and nothing changed in the last 10 seconds. If the album name of the download differs
from the catalog's, add it to `[match.aliases]`.

**Re-downloading an album.**
Delete the album's old download folder first, so that old and new files do not mix, and remove the album from
`state/converted.json` if it was converted before.

**A track was paired with the wrong title.**
Titles that contain one another (versions of one song) can be confused. Check the pairing and the durations with
`hist convert --dry-run --only "Album Name"` before converting.

**File dates changed after editing tags.**
Writing tags changes the modification date. Run `hist dates apply` (or `--only "Album Name"`) afterwards.

**A store purchase still counts as purchased.**
Store files carry purchase data in the audio track's description, which no tag editor removes. `hist convert`
rebuilds the container without re-encoding; then `hist store-entries --delete` removes the store version.

**The disk filled up.**
Moving files to the Trash does not free space until the Trash is emptied, and system caches can hold many
gigabytes until a restart. `hist convert` skips an album while free space would fall below `min_free_gb`.
