"""Persistent settings stored as JSON in %APPDATA%\\iTunesLibraryKeeper, or in a "data" folder next to
the app when it's the portable version (the compiled .exe run from anywhere Setup didn't install it)."""
import copy
import json
import os
import shutil
import sys
import threading
import time

_BASE = os.environ.get("APPDATA", os.path.expanduser("~"))
USER_APP_DIR = os.path.join(_BASE, "iTunesLibraryKeeper")
OLD_APP_DIR = os.path.join(_BASE, "LibraryToolkit")  # folder name used before the rename

# the folder holding the .exe (compiled) or iTunesLibraryKeeper.pyw (from source)
APP_ROOT = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) \
    else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INSTALLER_APP_ID = "{C2C90B91-802A-4133-B2E6-31E34AE68333}_is1"  # = AppId in installer\iTunesLibraryKeeper.iss


def _installed_by_setup():
    """True if Setup installed the app in APP_ROOT: its uninstaller sits beside the .exe, or an
    uninstall entry (per-user or all-users) points at this folder."""
    try:
        if any(n.lower().startswith("unins") and n.lower().endswith(".exe") for n in os.listdir(APP_ROOT)):
            return True
    except OSError:
        pass
    try:
        import winreg
    except ImportError:
        return False
    here = os.path.normcase(os.path.normpath(APP_ROOT))
    key = r"Software\Microsoft\Windows\CurrentVersion\Uninstall" + "\\" + INSTALLER_APP_ID
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(hive, key) as k:
                loc = winreg.QueryValueEx(k, "InstallLocation")[0]
            if os.path.normcase(os.path.normpath(loc)) == here:
                return True
        except OSError:
            continue
    return False


def _portable_dir():
    """The portable data folder, or None when not portable or the folder can't be written
    (e.g. the portable folder was copied into Program Files) - then %APPDATA% is used.
    Portable = the compiled .exe not installed by Setup; running from source never is."""
    if not getattr(sys, "frozen", False) or _installed_by_setup():
        return None
    path = os.path.join(APP_ROOT, "data")
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, ".write-test")
        with open(probe, "w") as f:
            f.write("ok")
        os.remove(probe)
        return path
    except OSError:
        return None


def _seed_portable(path):
    """First start of the portable version on a PC that already has the installed version's
    settings: start from a copy of them (the originals stay where they are)."""
    if os.listdir(path) or not os.path.isfile(os.path.join(USER_APP_DIR, "config.json")):
        return False
    try:
        shutil.copytree(USER_APP_DIR, path, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("toolkit.log", "*.broken-*"))
        return True
    except OSError:
        return False


def _migrate_old_data():
    """Carry settings and history over from the app's previous name (once)."""
    if os.path.isdir(USER_APP_DIR) or not os.path.isdir(OLD_APP_DIR):
        return
    try:
        os.rename(OLD_APP_DIR, USER_APP_DIR)
    except OSError:  # e.g. an old copy still running holds a file open: copy instead
        try:
            shutil.copytree(OLD_APP_DIR, USER_APP_DIR)
        except OSError:
            pass


_migrate_old_data()
_portable = _portable_dir()
PORTABLE = _portable is not None
APP_DIR = _portable or USER_APP_DIR
SEEDED_FROM_USER_DIR = PORTABLE and _seed_portable(APP_DIR)
CONFIG_PATH = os.path.join(APP_DIR, "config.json")


def window_settings():
    """QSettings for window size/position: the registry normally, an .ini in the data folder
    when portable (so nothing is left behind on the PC)."""
    from PySide6.QtCore import QSettings
    if PORTABLE:
        return QSettings(os.path.join(APP_DIR, "window.ini"), QSettings.Format.IniFormat)
    return QSettings("Faris Aljanubi", "iTunes Library Keeper")

DEFAULTS = {
    "library_xml": "",  # empty = auto-detect
    "watch_folders": [],
    "extensions": [".mp3", ".m4a", ".m4b", ".aac", ".mp4", ".wav", ".aif", ".aiff"],
    "skip_hidden": True,
    "exclude_folders": [],  # substrings; any path containing one is ignored
    "playlists": {
        "template": "Albums by Artist / {albumartist:1} / {albumartist} / {album} ({year})",
        "source": "Music",  # name of the source playlist, "" = whole library
        "ignore_the": True,  # "The Beatles" files under B for the :1 initial
        "compilation_artist": "Various Artists",
        "fallbacks": {
            "artist": "Unknown Artist",
            "albumartist": "Unknown Artist",
            "album": "(singles)",
            "year": "",
            "decade": "",
            "genre": "(no genre)",
            "composer": "(no composer)",
            "grouping": "",
            "disc": "",
        },
    },
    "automation": {
        "enabled": False,
        "watch": True,
        "interval_hours": 6,
        "debounce_seconds": 20,
        "add_new": True,
        "relink_moved": True,
        "refresh_tags": True,
        "remove_missing": False,
        "rebuild_playlists": False,
    },
    "theme": "system",  # system | light | dark
}


def _merge(base, override):
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


class Config:
    def __init__(self, path=CONFIG_PATH):
        self.path = path
        self._lock = threading.Lock()
        self.data = copy.deepcopy(DEFAULTS)
        self.version = 0
        self.load_error = ""  # set when config.json couldn't be read; the UI tells the user
        try:
            with open(path, encoding="utf-8-sig") as f:  # -sig: tolerate a BOM from hand-editing in Notepad
                loaded = json.load(f)
            if not isinstance(loaded, dict):
                raise ValueError("not a settings object")
            self.data = _merge(DEFAULTS, loaded)
            if not isinstance(self.data["watch_folders"], list) or not isinstance(self.data["extensions"], list):
                raise ValueError("watch_folders and extensions must be lists")
        except FileNotFoundError:
            pass
        except Exception as e:  # corrupt file: keep a copy, carry on with defaults, don't crash the app
            self.data = copy.deepcopy(DEFAULTS)
            backup = path + time.strftime(".broken-%Y%m%d-%H%M%S")
            try:
                shutil.copy2(path, backup)
                self.load_error = f"Your settings file couldn't be read ({e}), so defaults are in use. The old file was kept as {backup}."
            except OSError:
                self.load_error = f"Your settings file couldn't be read ({e}), so defaults are in use."
        self.data["watch_folders"] = [os.path.normpath(p) for p in self.data["watch_folders"]
                                      if isinstance(p, str) and p.strip()]

    def get(self):
        with self._lock:
            return copy.deepcopy(self.data)

    def update(self, patch):
        with self._lock:
            self.data = _merge(self.data, patch)
            self.data["extensions"] = sorted({
                (e if e.startswith(".") else "." + e).lower().strip()
                for e in self.data["extensions"] if e.strip()
            })
            self.data["watch_folders"] = [os.path.normpath(p) for p in self.data["watch_folders"] if p.strip()]
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
            os.replace(tmp, self.path)
            self.version += 1
            return copy.deepcopy(self.data)
