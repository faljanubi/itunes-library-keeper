"""Read-only model of the iTunes library, loaded from the shared library XML.

iTunes rewrites the XML some time after changes are made over COM, so changes
this app makes are kept in an overlay and re-applied on reload until the XML
catches up. Without that, a rescan right after "Add" would offer the same files
again.
"""
import os
import plistlib
import threading
import time
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import unquote

XML_NAMES = ("iTunes Music Library.xml", "iTunes Library.xml")


def default_xml_candidates():
    music = os.path.join(os.path.expanduser("~"), "Music")
    for base in (os.path.join(music, "iTunes"), music):
        for n in XML_NAMES:
            yield os.path.join(base, n)


_PREFS_TAIL = os.path.join("Apple Computer", "Preferences", "com.apple.iTunes.plist")
# Apple-installer iTunes writes its preferences to the real %APPDATA%.
ITUNES_PREFS = os.path.join(os.environ.get("APPDATA", ""), _PREFS_TAIL)


def itunes_prefs_path():
    """The iTunes preferences file to read, or '' if there is none.

    The Microsoft Store version runs packaged, so Windows redirects its %APPDATA% writes into
    %LOCALAPPDATA%\\Packages\\AppleInc.iTunes_<id>\\LocalCache\\Roaming. If both editions have
    left a file behind, the one written most recently belongs to the iTunes in use.
    """
    found = []
    candidates = [ITUNES_PREFS]
    packages = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Packages")
    try:
        for name in os.listdir(packages):
            if name.lower().startswith("appleinc.itunes_"):
                candidates.append(os.path.join(packages, name, "LocalCache", "Roaming", _PREFS_TAIL))
    except OSError:
        pass
    for p in candidates:
        try:
            found.append((os.path.getmtime(p), p))
        except OSError:
            pass
    return max(found)[1] if found else ""
SHARING_HELP = ("In iTunes open Edit > Preferences > Advanced, tick \"Share iTunes Library XML with other "
                "applications\" and click OK. iTunes Library Keeper picks it up automatically.")
STALE_AFTER = 300  # seconds the XML may trail the .itl before we call it stale


_loc_cache = [None, ("", "")]  # (prefs path, mtime), result


def itunes_locations():
    """(library .itl path, XML path) as recorded in iTunes' own preferences; either may be ''."""
    prefs = itunes_prefs_path()
    try:
        mtime = os.path.getmtime(prefs)
    except OSError:
        return "", ""
    if _loc_cache[0] == (prefs, mtime):
        return _loc_cache[1]
    itl = xml = ""
    try:
        with open(prefs, "rb") as f:
            d = plistlib.load(f)
        loc = d.get("Database Location") or ""
        if loc:
            itl = url_to_path(loc) if loc.startswith("file:") else loc
        raw = d.get("LXML:1:iTunes Library XML Location")
        if isinstance(raw, bytes):
            xml = raw.decode("utf-16-le", "ignore").rstrip("\0")
        elif isinstance(raw, str):
            xml = raw
    except Exception:
        pass
    _loc_cache[:] = [(prefs, mtime), (itl, xml)]
    return itl, xml


def find_library_xml(configured=""):
    if configured and os.path.isfile(configured):
        return configured
    _, xml = itunes_locations()
    if xml and os.path.isfile(xml):
        return xml
    for p in default_xml_candidates():
        if os.path.isfile(p):
            return p
    return ""


def find_library_itl(xml_path):
    """The .itl that belongs to this XML: the one iTunes paired it with, or the one next to it."""
    itl, xml = itunes_locations()
    if itl and xml and os.path.normcase(os.path.abspath(xml)) == os.path.normcase(os.path.abspath(xml_path)) \
            and os.path.isfile(itl):
        return itl
    p = os.path.join(os.path.dirname(xml_path), "iTunes Library.itl")
    return p if os.path.isfile(p) else ""


def check_xml_sharing(xml_path):
    """Return a problem description if iTunes doesn't seem to be sharing its library XML, else ''.

    The setting itself is stored inside the binary .itl, so we judge by behaviour: with sharing on,
    iTunes rewrites the XML right after it saves the .itl. A missing XML, or one that trails the
    .itl by more than a few minutes, means sharing is off.
    """
    if not xml_path or not os.path.isfile(xml_path):
        return "iTunes isn't sharing its library XML, so iTunes Library Keeper can't see your library."
    itl = find_library_itl(xml_path)
    if not itl:
        return ""
    try:
        lag = os.path.getmtime(itl) - os.path.getmtime(xml_path)
    except OSError:
        return ""
    if lag > STALE_AFTER:
        return ("iTunes has stopped updating its library XML (last written "
                + time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(xml_path)))
                + "), so what iTunes Library Keeper sees is out of date and scan results can be wrong.")
    return ""


def url_to_path(url):
    if not url or not url.startswith("file://"):
        return ""
    rest = url[len("file://localhost"):] if url.startswith("file://localhost") else url[len("file://"):]
    rest = unquote(rest)
    if rest.startswith("//"):  # UNC: file://localhost//server/share/...
        return "\\\\" + rest[2:].replace("/", "\\")
    if rest.startswith("/"):
        rest = rest[1:]
    return rest.replace("/", "\\")


def norm_path(p):
    """Key for comparing paths: case-insensitive, NFC, normalised separators."""
    return unicodedata.normalize("NFC", os.path.normcase(os.path.normpath(p)))


def _ts(dt):
    if not dt:
        return 0.0
    return dt.replace(tzinfo=timezone.utc).timestamp()


@dataclass(slots=True)
class Track:
    pid: str
    name: str = ""
    artist: str = ""
    album_artist: str = ""
    album: str = ""
    composer: str = ""
    genre: str = ""
    grouping: str = ""
    year: int = 0
    disc: int = 0
    track_no: int = 0
    size: int = 0
    total_time: int = 0
    location: str = ""
    modified: float = 0.0  # UTC epoch seconds
    added: float = 0.0
    play_count: int = 0
    rating: int = 0
    compilation: bool = False
    kind: str = ""

    def brief(self):
        return {
            "pid": self.pid, "name": self.name, "artist": self.artist or self.album_artist,
            "album": self.album, "location": self.location, "plays": self.play_count,
            "rating": self.rating, "size": self.size,
        }


@dataclass(slots=True)
class Playlist:
    pid: str
    name: str
    parent: str = ""
    folder: bool = False
    smart: bool = False
    distinguished: int = 0
    tracks: list = field(default_factory=list)


class Library:
    def __init__(self):
        self.lock = threading.RLock()
        self.xml_path = ""
        self.xml_mtime = 0.0
        self.loaded_at = 0.0
        self.library_pid = ""
        self.music_folder = ""
        self.tracks = {}      # pid -> Track
        self.by_path = {}     # norm_path -> pid
        self.playlists = {}   # pid -> Playlist
        self.error = ""
        # overlay of changes made through COM that the XML may not show yet
        self._added = {}      # norm_path -> (time, real path)
        self._removed = {}    # pid -> time
        self._relinked = {}   # pid -> (time, path)

    # ---------- loading ----------
    def load(self, xml_path):
        t0 = time.time()
        with open(xml_path, "rb") as f:
            d = plistlib.load(f)
        tracks, by_path = {}, {}
        for raw in d.get("Tracks", {}).values():
            pid = raw.get("Persistent ID")
            if not pid:
                continue
            t = Track(
                pid=pid,
                name=raw.get("Name", ""),
                artist=raw.get("Artist", ""),
                album_artist=raw.get("Album Artist", ""),
                album=raw.get("Album", ""),
                composer=raw.get("Composer", ""),
                genre=raw.get("Genre", ""),
                grouping=raw.get("Grouping", ""),
                year=raw.get("Year", 0) or 0,
                disc=raw.get("Disc Number", 0) or 0,
                track_no=raw.get("Track Number", 0) or 0,
                size=raw.get("Size", 0) or 0,
                total_time=raw.get("Total Time", 0) or 0,
                location=url_to_path(raw.get("Location", "")) if raw.get("Track Type", "File") == "File" else "",
                modified=_ts(raw.get("Date Modified")),
                added=_ts(raw.get("Date Added")),
                play_count=raw.get("Play Count", 0) or 0,
                rating=raw.get("Rating", 0) or 0,
                compilation=bool(raw.get("Compilation")),
                kind=raw.get("Kind", ""),
            )
            tracks[pid] = t
            if t.location:
                by_path[norm_path(t.location)] = pid
        id_to_pid = {str(raw.get("Track ID")): raw.get("Persistent ID") for raw in d.get("Tracks", {}).values()}
        playlists = {}
        for p in d.get("Playlists", []):
            pid = p.get("Playlist Persistent ID")
            if not pid:
                continue
            playlists[pid] = Playlist(
                pid=pid,
                name=p.get("Name", ""),
                parent=p.get("Parent Persistent ID", ""),
                folder=bool(p.get("Folder")),
                smart="Smart Info" in p,
                distinguished=p.get("Distinguished Kind", 0) or 0,
                tracks=[id_to_pid[str(i["Track ID"])] for i in p.get("Playlist Items", [])
                        if str(i.get("Track ID")) in id_to_pid],
            )
        with self.lock:
            self.xml_path = xml_path
            self.xml_mtime = os.path.getmtime(xml_path)
            self.loaded_at = time.time()
            self.library_pid = d.get("Library Persistent ID", "")
            self.music_folder = url_to_path(d.get("Music Folder", ""))
            self.tracks, self.by_path, self.playlists = tracks, by_path, playlists
            self.error = ""
            self._reapply_overlay()
        return time.time() - t0

    def xml_changed(self):
        try:
            return os.path.getmtime(self.xml_path) != self.xml_mtime
        except OSError:
            return False

    def _reapply_overlay(self):
        now = time.time()
        expiry = 6 * 3600  # give up on the overlay after a while; the XML wins
        for key, (ts, _) in list(self._added.items()):
            if key in self.by_path or now - ts > expiry:
                del self._added[key]
        for pid, ts in list(self._removed.items()):
            if pid not in self.tracks or now - ts > expiry:
                self._removed.pop(pid, None)
            else:
                self._drop(pid)
        for pid, (ts, path) in list(self._relinked.items()):
            t = self.tracks.get(pid)
            if not t or norm_path(t.location) == norm_path(path) or now - ts > expiry:
                del self._relinked[pid]
            else:
                self._set_location(t, path)

    def _drop(self, pid):
        t = self.tracks.pop(pid, None)
        if t and t.location:
            self.by_path.pop(norm_path(t.location), None)

    def _set_location(self, t, path):
        if t.location:
            self.by_path.pop(norm_path(t.location), None)
        t.location = path
        self.by_path[norm_path(path)] = t.pid

    # ---------- overlay mutations (called after successful COM operations) ----------
    def note_added(self, path, track=None):
        with self.lock:
            self._added[norm_path(path)] = (time.time(), path)
            if track is not None:
                self.tracks[track.pid] = track
                self.by_path[norm_path(path)] = track.pid

    def note_removed(self, pid):
        with self.lock:
            self._removed[pid] = time.time()
            self._drop(pid)

    def note_relinked(self, pid, path):
        with self.lock:
            self._relinked[pid] = (time.time(), path)
            t = self.tracks.get(pid)
            if t:
                self._set_location(t, path)

    def note_refreshed(self, pid):
        with self.lock:
            t = self.tracks.get(pid)
            if t:
                t.modified = time.time()

    def is_tracked(self, path):
        k = norm_path(path)
        with self.lock:
            return k in self.by_path or k in self._added

    # ---------- queries ----------
    def source_tracks(self, source_name):
        """Tracks of the named playlist (e.g. "Music"); whole library if blank or unknown."""
        with self.lock:
            if source_name:
                for p in self.playlists.values():
                    if p.name == source_name and not p.folder:
                        return [self.tracks[pid] for pid in p.tracks if pid in self.tracks]
            return list(self.tracks.values())

    def playlist_names(self):
        with self.lock:
            return sorted({p.name for p in self.playlists.values() if not p.folder and p.tracks})

    def suggest_watch_folders(self, limit=4):
        """Folders that hold the library's files, for a one-click watch-folder setup.

        Per drive, the deepest folder containing all of that drive's tracks; when that is the
        drive root itself, its biggest top-level folders instead. Tiny outliers are ignored."""
        with self.lock:
            dirs = [os.path.dirname(t.location) for t in self.tracks.values() if t.location]
        total = len(dirs)
        if not total:
            return []
        by_drive = defaultdict(list)
        for d in dirs:
            drive = os.path.splitdrive(d)[0]
            if drive:
                by_drive[drive.upper()].append(d)
        found = []  # (track count, folder)
        for group in by_drive.values():
            if len(group) < max(3, total * 0.02):
                continue
            try:
                common = os.path.commonpath(group)
            except ValueError:
                continue
            if os.path.splitdrive(common)[1].strip("\\"):
                found.append((len(group), common))
                continue
            top = defaultdict(list)
            for d in group:
                parts = os.path.splitdrive(d)[1].strip("\\").split("\\")
                if parts[0]:
                    top[parts[0]].append(d)
            for sub in top.values():
                if len(sub) >= max(3, total * 0.02):
                    found.append((len(sub), os.path.commonpath(sub)))
        found.sort(reverse=True)
        return [f for _, f in found if os.path.isdir(f)][:limit]

    def stats(self):
        with self.lock:
            ts = self.tracks.values()
            return {
                "xml_path": self.xml_path,
                "loaded_at": self.loaded_at,
                "xml_mtime": self.xml_mtime,
                "tracks": len(self.tracks),
                "albums": len({(t.album_artist or t.artist, t.album) for t in ts if t.album}),
                "artists": len({t.album_artist or t.artist for t in ts if (t.album_artist or t.artist)}),
                "playlists": sum(1 for p in self.playlists.values() if not p.folder and not p.distinguished),
                "size_bytes": sum(t.size for t in ts),
                "music_folder": self.music_folder,
                "error": self.error,
                "sharing_problem": check_xml_sharing(self.xml_path),
                "pending_changes": len(self._added) + len(self._removed) + len(self._relinked),
            }
