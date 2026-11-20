---
title: Installation
nav_order: 2
---

# Installation
{: .no_toc }

1. TOC
{:toc}

## Requirements

- **Windows 10 or 11, 64-bit**
- **iTunes for Windows**, from [apple.com](https://www.apple.com/itunes/) or the Microsoft Store.
  Both work. The app controls iTunes through its official COM interface.

You don't need Python or anything else.

## Choose a version

Both are on the [Releases page](https://github.com/faljanubi/itunes-library-keeper/releases/latest).

| | Installer | Portable |
|:--|:--|:--|
| File | `iTunesLibraryKeeper-<version>-setup.exe` | `iTunesLibraryKeeper-<version>-portable-win64.zip` |
| Install | Run it; no admin rights needed | Unzip anywhere, run `iTunes Library Keeper.exe` |
| Shortcuts | Start menu, optional desktop | None |
| Settings stored in | `%APPDATA%\iTunesLibraryKeeper` | A `data` folder next to the .exe |
| Uninstall | *Settings › Apps* in Windows | Delete the folder |

Pick the **installer** if you aren't sure. Pick **portable** to run it from a USB drive or keep it
in one self-contained folder.

{: .note }
The files aren't code-signed, so Windows SmartScreen may say *"Windows protected your PC"* the
first time. Click **More info › Run anyway**.

### Installer details

- It installs for your user account by default. You can choose all users instead (that one asks
  for admin rights).
- If the app is running, Setup closes it first. Running a newer Setup updates the app and keeps
  your settings.
- When you uninstall, you're asked whether to delete your settings too.

### Portable details

- Keep the whole folder together. The .exe needs the `_internal` folder next to it.
- If this PC already has settings from the installed version, the portable version starts with
  a copy of them the first time. After that, the two keep separate settings.
- If the folder can't be written to (for example inside *Program Files*), it uses
  `%APPDATA%\iTunesLibraryKeeper` like the installed version.
- To update, replace everything except the `data` folder.

## Set up iTunes

The app reads your library from the XML file iTunes can share with other apps. Turn it on once:

1. Open iTunes.
2. Go to *Edit › Preferences › Advanced*.
3. Tick **Share iTunes Library XML with other applications** and click **OK**.

If this is off, the app shows a red warning with these steps.

{: .warning }
Back up your iTunes library folder (usually `Music\iTunes`) before your first big clean-up.

## Next step

Go to [Getting started](getting-started) for your first scan.
