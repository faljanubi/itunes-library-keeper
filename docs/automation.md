---
title: Automation
nav_order: 6
---

# Automation
{: .no_toc }

Automation lets the app scan and apply safe changes on its own, so iTunes stays in step with your
folders without you opening the app. It's **off** by default.

1. TOC
{:toc}

## Before you start

Add at least one [watch folder](settings#watch-folders). Automation only works with watch folders.

## When to run

| Setting | Default | Meaning |
|:--|:--|:--|
| **Enable automation** | Off | Master switch for everything on this page |
| **Watch folders for changes** | On | Runs shortly after files are added, moved or edited in your watch folders |
| **Wait after the last change** | 20 seconds | Waits until you've finished copying or tagging before it runs |
| **Also run every** | 6 hours | A regular check as well, to catch anything the watcher missed |
| **Start with Windows** | Off | Starts the app quietly in the notification area when you sign in |

Click **Run now** to start a run straight away.

## What it may do

| Action | Default | Notes |
|:--|:--|:--|
| **Relink moved files** | On | Only exact matches (same name and size). Keeps play counts and playlists |
| **Add new files** | On | Adds new audio files from your watch folders |
| **Refresh edited tags** | On | Makes iTunes re-read tags you changed in other apps |
| **Update playlists** | Off | Keeps the playlist folder from the [Playlists](playlists) page up to date |
| **Remove missing entries** | Off | See below |

Automation is more careful than you are on the Review page: it only relinks *high-confidence*
matches, and never picks between several identical files. Those wait on the Review page for you.

### Remove missing entries

{: .warning }
Play counts, ratings and playlist membership of removed tracks are lost. The app asks you to
confirm before turning this on.

Even when it's on, automation **skips removal if more than 25 tracks are missing at once**.
That usually means a drive or folder is temporarily gone rather than files being deleted. Tracks
on unavailable drives are never removed.

## Running in the background

While automation is on, closing the window keeps the app running in the **notification area**
(system tray). Click the tray icon to open the window, or use **Quit app** in the sidebar or the
tray icon's menu to stop it.

With **Start with Windows**, the app starts in the notification area when you sign in, without
opening its window.

Unavailable watch folders (for example an unplugged USB drive) are retried every 30 seconds, and
watched again once they're back.

## Checking what it did

The Automation and Overview pages show the last run and its summary. Every run is listed on the
[Activity](activity) page with full details.
