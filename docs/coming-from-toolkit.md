---
title: Coming from iTunes Library Toolkit
nav_order: 9
---

# Coming from iTunes Library Toolkit

iTunes Library Keeper does the same job as klarita.net's *iTunes Library Toolkit*, with a
review-first workflow. It isn't affiliated with klarita.net and doesn't read the Toolkit's
settings, so set up your watch folders again.

| iTunes Library Toolkit | iTunes Library Keeper |
|:--|:--|
| Runs tasks blindly, shows a log afterwards | **Scan, then review**: every proposed change is listed, and nothing happens until you click Apply |
| Moved files: deletes the old entry, re-adds the file, copies some stats over | **Relinks in place**, keeping ratings, play counts, date added *and playlist membership* |
| Changes often only show in iTunes after restarting it | Moved tracks are re-read from the file, and iTunes' view is **refreshed automatically** |
| Matches moved files by artist/album/title (with a bug that ignores the digit 9) | Matches on file name + size. Ambiguous matches are never guessed; you pick from the candidates |
| A disconnected drive can make tracks look dead | Unavailable drives are reported separately and never treated as missing |
| Playlist template with cryptic `%AA1` codes, no preview | Readable `{albumartist:1}` fields, presets, and a **live preview** with counts |
| Re-running can duplicate playlists if the XML is stale | Reads the current tree from iTunes and only changes the differences |
| Automation can mass-delete | Automatic removal is off by default and refuses to remove more than 25 at once |
| Licence nags, telemetry ping, ban-list download | None. Nothing leaves your computer |
| No undo trail | **Activity** history with details; removed entries are saved to JSON first |

## Playlist templates

Toolkit templates don't carry over. Rewrite them with readable fields: for example, the first
letter of the album artist is `{albumartist:1}`. See [Playlists](playlists#fields) for all fields
and presets.

## Not available yet

The Toolkit's HTML catalog generator hasn't been ported.
