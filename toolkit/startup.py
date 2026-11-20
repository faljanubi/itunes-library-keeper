"""The "Start with Windows" shortcut in the user's Startup folder."""
import logging
import os
import sys

log = logging.getLogger("toolkit")
STARTUP_DIR = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup")
STARTUP_LNK = os.path.join(STARTUP_DIR, "iTunes Library Keeper.lnk")
OLD_STARTUP_LNK = os.path.join(STARTUP_DIR, "Library Toolkit.lnk")  # pre-rename name


def is_enabled():
    return os.path.exists(STARTUP_LNK)


def migrate():
    """Replace a Startup shortcut made under the old app name, and refresh an existing one
    so it points at this version (the web version passed different arguments)."""
    try:
        if os.path.exists(OLD_STARTUP_LNK):
            os.remove(OLD_STARTUP_LNK)
            set_enabled(True)
            log.info("startup shortcut renamed")
        elif os.path.exists(STARTUP_LNK):
            set_enabled(True)
    except Exception as e:
        log.warning("could not update the startup shortcut: %s", e)


def set_enabled(enabled):
    if not enabled:
        for p in (STARTUP_LNK, OLD_STARTUP_LNK):
            if os.path.exists(p):
                os.remove(p)
        return
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()
    sh = win32com.client.Dispatch("WScript.Shell")
    lnk = sh.CreateShortCut(STARTUP_LNK)
    if getattr(sys, "frozen", False):
        # compiled build: launch the .exe itself
        lnk.TargetPath = sys.executable
        lnk.Arguments = "--background"
        lnk.WorkingDirectory = os.path.dirname(sys.executable)
        lnk.IconLocation = sys.executable
    else:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        lnk.TargetPath = pythonw if os.path.exists(pythonw) else sys.executable
        lnk.Arguments = f'"{os.path.join(root, "iTunesLibraryKeeper.pyw")}" --background'
        lnk.WorkingDirectory = root
        icon = os.path.join(root, "assets", "icon.ico")
        if os.path.exists(icon):
            lnk.IconLocation = icon
    lnk.Description = "iTunes Library Keeper"
    lnk.save()
