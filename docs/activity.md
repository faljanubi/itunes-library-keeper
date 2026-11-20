---
title: Activity & safety
nav_order: 7
---

# Activity & safety
{: .no_toc }

1. TOC
{:toc}

## Activity page

The Activity page lists everything the app has done, newest first: adding, relinking, removing,
tag refreshes, playlist builds and automatic runs. Scans aren't listed, because they don't change
anything.

Select an entry to see its details: when it ran, whether it finished or was cancelled, and a line
for every file it handled, such as `ADDED: ...`, `SKIP (file no longer there): ...` or
`ERROR: ...`.

The 300 most recent entries are kept. **Clear log** empties the list; it doesn't change anything
in iTunes.

## Safety rules

The app is built to make mistakes hard:

- **Scans only read.** Nothing in iTunes changes until you apply, or until automation does.
- **Your music files are never changed, moved or deleted.** Only iTunes' library entries are.
- **Relinking changes the track in place**, so ratings, play counts, date added and playlists
  are kept.
- **Ambiguous matches are never guessed.** You pick from the candidates.
- **Disconnected drives are never treated as missing.**
- **Automatic removal is off by default** and refuses to remove more than 25 tracks at once.
- **Playlists are only changed inside the app's own root folder.**
- **Nothing leaves your computer.** No telemetry, no account, no web server.

## Removal backups

Before any entries are removed, their details (name, artist, album, location and so on) are
saved to a file named like `removed-20261121-153000.json` in the `removed` folder of the app's
data folder. The Activity entry shows the exact path.

Use it to see what was removed, or to find files and add them back.

## Undo

There's no one-click undo, but:

- **Added a file by mistake?** Delete it from iTunes as usual, and use **Ignore selected** on the
  Review page next time.
- **Removed a track by mistake?** Add the file back to iTunes. Its play count and rating are
  lost, but the removal backup shows what they were.
- **Ignored a file by mistake?** Clear the ignore list in [Settings](settings#scanning).

## Where data is stored

| Version | Folder |
|:--|:--|
| Installed | `%APPDATA%\iTunesLibraryKeeper` |
| Portable | `data` next to `iTunes Library Keeper.exe` |

| File | Contents |
|:--|:--|
| `config.json` | Your settings |
| `history.json` | The Activity list |
| `ignored.json` | The ignore list |
| `removed\` | Removal backups |
| `toolkit.log` | The log file, useful for bug reports |

*Settings › App data* shows the folder in use. Click it to open the folder.
