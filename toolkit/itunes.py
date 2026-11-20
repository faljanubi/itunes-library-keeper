"""Thin wrapper over the iTunes for Windows COM API.

Every method must be called from the thread that called connect() (COM objects
are apartment-bound); the JobRunner owns that thread.
"""
import time

import pythoncom
import pywintypes
import win32com.client
from win32com.client import gencache

# HRESULTs iTunes returns while a modal dialog is open or it is busy
BUSY = {-2147418111, -2147417846, -2147417848}  # RPC_E_CALL_REJECTED, RPC_E_SERVERCALL_RETRYLATER, RPC_E_DISCONNECTED
KIND_FILE = 1          # ITTrackKindFile
PL_KIND_USER = 2       # ITPlaylistKindUser
SPECIAL_FOLDER = 4     # ITUserPlaylistSpecialKindFolder


class ITunesError(Exception):
    pass


def split_pid(pid):
    pid = pid.rjust(16, "0")
    hi, lo = int(pid[:8], 16), int(pid[8:], 16)
    to_signed = lambda v: v - (1 << 32) if v >= (1 << 31) else v
    return to_signed(hi), to_signed(lo)


def join_pid(hi, lo):
    return f"{hi & 0xFFFFFFFF:08X}{lo & 0xFFFFFFFF:08X}"


class ITunes:
    def __init__(self, on_wait=None):
        self.app = None
        self.on_wait = on_wait  # callback(str) while iTunes is busy
        self.dirty = False      # something changed since the last refresh_view()

    # ---------- connection ----------
    def connect(self):
        if self.app is not None:
            try:
                self.app.Version
                return self
            except pywintypes.com_error:
                self.app = None
        pythoncom.CoInitialize()
        try:
            self.app = gencache.EnsureDispatch("iTunes.Application")
        except Exception:
            # stale/corrupt gen_py cache: rebuild once
            gencache.Rebuild()
            self.app = gencache.EnsureDispatch("iTunes.Application")
        return self

    @property
    def version(self):
        return self.call(lambda: self.app.Version)

    def call(self, fn, timeout=120):
        """Run fn(), retrying while iTunes reports it is busy (e.g. a dialog is open)."""
        start = time.time()
        warned = False
        while True:
            try:
                return fn()
            except pywintypes.com_error as e:
                if e.hresult not in BUSY or time.time() - start > timeout:
                    raise ITunesError(_describe(e)) from e
                if not warned and self.on_wait:
                    self.on_wait("Waiting for iTunes - close any open dialogs in iTunes")
                    warned = True
                time.sleep(0.5)

    # ---------- tracks ----------
    def _lib_tracks(self):
        return self.app.LibraryPlaylist.Tracks

    def track(self, pid):
        hi, lo = split_pid(pid)
        t = self.call(lambda: self._lib_tracks().ItemByPersistentID(hi, lo))
        if t is None:
            raise ITunesError(f"Track {pid} is no longer in iTunes")
        return t

    def file_track(self, pid):
        t = self.track(pid)
        return win32com.client.CastTo(t, "IITFileOrCDTrack")

    def pid_of(self, obj):
        hi = self.call(lambda: self.app.ITObjectPersistentIDHigh(obj))
        lo = self.call(lambda: self.app.ITObjectPersistentIDLow(obj))
        return join_pid(hi, lo)

    def add_file(self, path):
        """Add one file; returns the new track's IITFileOrCDTrack (or None if iTunes refused it)."""
        status = self.call(lambda: self.app.LibraryPlaylist.AddFile(path))
        if status is None:
            return None
        deadline = time.time() + 120
        while self.call(lambda: status.InProgress) and time.time() < deadline:
            time.sleep(0.05)
        tracks = self.call(lambda: status.Tracks)
        if tracks is None or tracks.Count == 0:
            return None
        self.dirty = True
        return win32com.client.CastTo(tracks.Item(1), "IITFileOrCDTrack")

    def relink(self, pid, new_path):
        ft = self.file_track(pid)
        self.call(lambda: setattr(ft, "Location", new_path))
        self.dirty = True
        # Setting Location alone leaves iTunes showing its cached details (and sometimes the
        # "file missing" mark) until it is restarted; make it read the file now.
        try:
            self.call(ft.UpdateInfoFromFile)
        except ITunesError:
            pass  # the relink itself succeeded; details will catch up when the track is played

    def refresh_tags(self, pid):
        ft = self.file_track(pid)
        self.call(ft.UpdateInfoFromFile)
        self.dirty = True

    def delete(self, pid):
        t = self.track(pid)
        self.call(t.Delete)
        self.dirty = True

    # ---------- view ----------
    def refresh_view(self):
        """Make the iTunes window show the current library without restarting iTunes.

        iTunes applies COM changes to its database immediately but often doesn't redraw the
        list that is open. Switching the window to another playlist and straight back makes
        it reload that view. Only the selection in the window is touched.
        """
        self.dirty = False
        bw = self.call(lambda: self.app.BrowserWindow)
        if bw is None:
            return False
        current = self.call(lambda: bw.SelectedPlaylist)
        if current is None:
            return False
        cur_pid = self.pid_of(current)
        # The internal "Library" playlist can't be selected in iTunes 12 (the window shows
        # "Music" etc.), so bounce through any other playlist that is visible in the sidebar.
        pls = self.call(lambda: self.app.LibrarySource.Playlists)
        for i in range(1, min(self.call(lambda: pls.Count), 200) + 1):
            p = self.call(lambda: pls.Item(i))
            try:
                if not self.call(lambda: p.Visible) or self.pid_of(p) == cur_pid:
                    continue
                self.call(lambda: setattr(bw, "SelectedPlaylist", p), timeout=5)
            except ITunesError:
                continue  # iTunes refused this one; try the next
            time.sleep(0.25)
            self.call(lambda: setattr(bw, "SelectedPlaylist", current))
            return True
        return False

    # ---------- playlists ----------
    def playlist(self, pid):
        hi, lo = split_pid(pid)
        p = self.call(lambda: self.app.LibrarySource.Playlists.ItemByPersistentID(hi, lo))
        if p is None:
            return None
        return win32com.client.CastTo(p, "IITUserPlaylist")

    def create(self, name, is_folder, parent=None):
        if parent is None:
            fn = self.app.CreateFolder if is_folder else self.app.CreatePlaylist
        else:
            fn = parent.CreateFolder if is_folder else parent.CreatePlaylist
        p = self.call(lambda: fn(name))
        self.dirty = True
        return win32com.client.CastTo(p, "IITUserPlaylist")

    def user_playlists(self):
        """All user playlists/folders as dicts: pid, name, parent (pid or ''), folder, obj."""
        pls = self.call(lambda: self.app.LibrarySource.Playlists)
        out = []
        for i in range(1, self.call(lambda: pls.Count) + 1):
            p = self.call(lambda: pls.Item(i))
            if self.call(lambda: p.Kind) != PL_KIND_USER:
                continue
            up = win32com.client.CastTo(p, "IITUserPlaylist")
            if self.call(lambda: up.SpecialKind) not in (0, SPECIAL_FOLDER):
                continue  # built-in lists like Purchased, Podcasts
            try:
                parent = self.call(lambda: up.Parent)
            except ITunesError:
                parent = None
            out.append({
                "pid": self.pid_of(up),
                "name": self.call(lambda: up.Name),
                "parent": self.pid_of(parent) if parent is not None else "",
                "folder": self.call(lambda: up.SpecialKind) == SPECIAL_FOLDER,
                "obj": up,
            })
        return out

    def playlist_track_pids(self, pl):
        tracks = self.call(lambda: pl.Tracks)
        return [self.pid_of(self.call(lambda: tracks.Item(i)))
                for i in range(1, self.call(lambda: tracks.Count) + 1)]

    def playlist_count(self, pl):
        return self.call(lambda: pl.Tracks.Count)

    def playlist_has(self, pl, pid):
        hi, lo = split_pid(pid)
        return self.call(lambda: pl.Tracks.ItemByPersistentID(hi, lo)) is not None

    def add_to_playlist(self, pl, pid):
        t = self.track(pid)
        self.call(lambda: pl.AddTrack(t))
        self.dirty = True

    def remove_from_playlist(self, pl, pids):
        """Remove the given tracks (by persistent ID) from a playlist."""
        pids = set(pids)
        tracks = self.call(lambda: pl.Tracks)
        # walk backwards so indexes stay valid while deleting
        for i in range(self.call(lambda: tracks.Count), 0, -1):
            t = self.call(lambda: tracks.Item(i))
            if self.pid_of(t) in pids:
                self.call(t.Delete)
                self.dirty = True

    def delete_playlist(self, pl):
        self.call(pl.Delete)
        self.dirty = True


def _describe(e):
    try:
        if e.excepinfo and e.excepinfo[2]:
            return e.excepinfo[2]
    except Exception:
        pass
    return f"{e.strerror} (0x{e.hresult & 0xFFFFFFFF:08X})"
