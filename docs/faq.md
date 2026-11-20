---
title: FAQ & troubleshooting
nav_order: 10
---

# FAQ & troubleshooting
{: .no_toc }

1. TOC
{:toc}

## "Can't read your iTunes library"

Turn on *Edit › Preferences › Advanced › Share iTunes Library XML with other applications* in
iTunes, then click **Open settings › Save & reload**. If you keep your library in an unusual
place, set the **Library XML location** in [Settings](settings#library-file).

## My new music isn't found

New files are only found inside **watch folders**. Check that the folder holding your new music
(or a folder above it) is listed in [Settings](settings#watch-folders), and that its file type is
in the **File types** list. Also check the folder isn't matched by **Skip folders containing**,
and that the files aren't on the ignore list.

## A track shows as missing, but I know where the file is

The file is probably outside your watch folders, or its name **and** size both changed (for
example you renamed it and edited its tags). Add its folder as a watch folder and scan again.
If several identical files match, double-click the track on the Missing tab to pick one.

## Tracks on my external drive show as Unavailable

That's expected while the drive isn't connected. They're left alone. Connect the drive and scan
again.

## Does it change or delete my music files?

No. It only changes iTunes' library entries. Removing a missing entry removes it from iTunes,
and a backup of its details is saved first.

## Does it work with the Microsoft Store version of iTunes?

Yes. It finds the library of both the apple.com and the Microsoft Store versions.

## Does it work with Apple Music for Windows?

No. The app needs iTunes' COM interface and library XML, which the Apple Music app doesn't offer.

## Is there a 32-bit version?

No. The app needs 64-bit Windows 10 or 11.

## iTunes is busy or shows a dialog

The app waits and tries again while iTunes is busy, for example while a dialog is open in iTunes.
Close the dialog and the task continues.

## A playlist I made disappeared

It was inside the root folder of the [Playlists](playlists) template. The app removes everything
in that folder the template doesn't produce. Keep your own playlists outside it.

## The app doesn't start any more (running from source)

Quit it and run `setup.cmd` again. If that fails, delete the `.venv` folder first.
The release builds don't have this problem.

## Reporting a bug

Please open an [issue on GitHub](https://github.com/faljanubi/itunes-library-keeper/issues) and
include:

- the app version (*Settings › About*) and your Windows version,
- what you did, what you expected and what happened,
- the relevant lines from `toolkit.log` in the [app data folder](activity#where-data-is-stored).
