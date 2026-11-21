# Changelog

## 1.0.1 (2026-11-21)

- Fixed: applying changes failed with "has no attribute 'MinorVersion'" (or 'CLSIDToClassMap') after a temp-file cleaner emptied the COM cache in %TEMP%\gen_py. The app now rebuilds that cache by itself.

## 1.0.0 (2026-11-20)

First public release.

- Scan-then-review workflow: new, moved, missing, unavailable and stale-tag tracks are listed before anything changes in iTunes
- Moved files are relinked in place, keeping ratings, play counts, date added and playlist membership
- Playlist builder with templates, presets and a live preview tree; incremental sync
- Automation: watch folders, schedule, start with Windows, notification-area icon
- Activity history with per-run logs; removed entries are backed up to JSON first
- Native Windows 11-style window (Qt) with light and dark mode
- Works with iTunes from Apple's installer and from the Microsoft Store
- Installer (per-user, no admin prompt) and portable zip
