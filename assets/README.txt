iTunes Library Keeper (portable)
================================
Version 1.0.1 - created by Faris Aljanubi

This is the portable version: nothing to install, and it keeps its settings
inside this folder, so the folder can be moved to another place, PC or USB
drive. (Prefer a normal install with a Start menu shortcut and uninstaller?
Use iTunesLibraryKeeper-<version>-setup.exe instead.)

Start:  double-click "iTunes Library Keeper.exe". The app opens in its own
        window (a native Windows app; no browser needed).
Stop:   close the window. If automation is turned on, the app keeps running
        in the notification area (system tray) instead - open it again from
        the tray icon, or use "Quit app" at the bottom of the sidebar (or the
        tray icon's menu) to stop it.

Before first use, in iTunes open Edit > Preferences > Advanced and tick
"Share iTunes Library XML with other applications". The app shows a red
warning with these steps if it is off.

Keep this whole folder together: the .exe needs the _internal folder next to it.
No Python installation is needed.

Settings, history and backups of removed entries are stored in the "data"
folder next to the .exe. On first start, if this PC already has settings from
the installed version (%APPDATA%\iTunesLibraryKeeper), the portable version
starts from a copy of them; after that the two keep separate settings.
If this folder can't be written to (e.g. inside Program Files), the app uses
%APPDATA%\iTunesLibraryKeeper instead, like the installed version.

Updating: replace everything except the "data" folder with the new version.

Source code, updates and issue reports:
https://github.com/faljanubi/itunes-library-keeper

Copyright (C) 2026 Faris Aljanubi. Free software under the GNU General Public
License version 3 or later (see LICENSE.txt); it comes with NO WARRANTY.

Not affiliated with Apple or klarita.net. iTunes is a trademark of Apple Inc.
