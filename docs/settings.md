---
title: Settings
nav_order: 8
---

# Settings
{: .no_toc }

1. TOC
{:toc}

## Watch folders

Where your music files live. Scans look here for new and moved files.

- **Add folder...** adds a folder. To stop watching one, select it and click **Remove**.
- If your library has music in folders you aren't watching, the app suggests them. Click
  **Add it** to watch them.
- Folders on a drive that isn't connected are skipped and reported on the Overview.

{: .note }
Without a watch folder, the app can still find missing and stale tracks, but it can't find new
or moved files.

## Scanning

| Setting | Default | Meaning |
|:--|:--|:--|
| **File types** | `.mp3 .m4a .m4b .aac .mp4 .wav .aif .aiff` | Extensions to look for, separated by spaces |
| **Skip folders containing** | (empty) | One per line. Any path containing the text is skipped, e.g. `\Voice Memos\` |
| **Skip hidden and system files** | On | Ignores hidden and system files and folders |

The ignore list is shown here too, with a button to clear it. Ignored files are offered again on
the next scan.

After changing these, run a new scan to use them.

{: .tip }
The file types are the ones iTunes for Windows can play. FLAC and other formats iTunes doesn't
support would be refused, so they aren't in the list.

## Library file

| Item | Meaning |
|:--|:--|
| **Library file** | The `iTunes Library.xml` (or `iTunes Music Library.xml`) the app reads |
| **Last read** | When it was last loaded |
| **iTunes** | Whether the app can reach iTunes |
| **App data** | Where settings and history are stored; click it to open the folder (see [Activity & safety](activity#where-data-is-stored)) |
| **Library XML location** | Leave empty (**Auto-detect**) to find it from iTunes' own settings, or **Browse...** to pick it |

**Save & reload** reads the library again.

Auto-detect works with both the apple.com and Microsoft Store versions of iTunes. iTunes must
have *Share iTunes Library XML with other applications* turned on, see
[Installation](installation#set-up-itunes).

## Appearance

**Auto** follows the Windows light/dark setting. You can also pick **Light** or **Dark**.

## About

Shows the version, licence and a link to the source code. Include the version in bug reports.

## Command line

| Option | Effect |
|:--|:--|
| `--background` | Start in the notification area only, without opening the window |
| `--quit` | Ask a running copy to quit (it finishes any running task first) |
