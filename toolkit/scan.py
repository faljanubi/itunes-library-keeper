"""Library health scan: computes proposed changes without touching iTunes.

Categories:
  new      - audio files in watch folders that iTunes doesn't know about
  moved    - library entries whose file is gone but which match an untracked file
             (fixed by relinking in place, which keeps ratings, play counts and playlists)
  missing  - library entries whose file is gone with no match found
  offline  - entries on a drive/share that is currently unavailable (never treated as missing)
  stale    - files edited outside iTunes since iTunes last read their tags
"""
import os
import stat
import time
from collections import defaultdict

from .library import norm_path

STALE_TOLERANCE = 2.0  # seconds


class Cancelled(Exception):
    pass


def _root_of(path):
    drive, rest = os.path.splitdrive(path)
    return drive + "\\" if drive else ""


def walk_audio(roots, extensions, skip_hidden, exclude, progress=None, cancelled=lambda: False):
    """Yield (path, size, mtime) for audio files below roots."""
    exts = tuple(e.lower() for e in extensions)
    excl = [e.strip().replace("/", "\\").lower() for e in exclude if e.strip()]
    stack = list(roots)
    seen_dirs = 0
    while stack:
        d = stack.pop()
        if cancelled():
            raise Cancelled()
        # trailing backslash so "\Voice Memos\" also matches the folder itself, not just its subfolders
        if excl and any(x in d.lower().rstrip("\\") + "\\" for x in excl):
            continue
        seen_dirs += 1
        if progress and seen_dirs % 50 == 0:
            progress(f"Scanning folders... ({seen_dirs} so far)")
        try:
            with os.scandir(d) as it:
                for e in it:
                    try:
                        st = e.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    if skip_hidden and (st.st_file_attributes & (stat.FILE_ATTRIBUTE_HIDDEN | stat.FILE_ATTRIBUTE_SYSTEM)):
                        continue
                    if e.is_dir(follow_symlinks=False):
                        stack.append(e.path)
                    elif e.name.lower().endswith(exts) and not e.name.startswith("._"):
                        yield e.path, st.st_size, st.st_mtime
        except OSError:
            continue


def run_scan(lib, cfg, progress=lambda msg, frac=None: None, cancelled=lambda: False):
    t0 = time.time()
    roots = [r for r in cfg["watch_folders"]]
    unavailable_roots = [r for r in roots if not os.path.isdir(r)]
    roots = [r for r in roots if os.path.isdir(r)]

    # 1. untracked files in watch folders
    progress("Scanning watch folders...", 0.0)
    untracked = []
    for path, size, mtime in walk_audio(roots, cfg["extensions"], cfg["skip_hidden"], cfg["exclude_folders"],
                                        progress=lambda m: progress(m, None), cancelled=cancelled):
        if not lib.is_tracked(path):
            untracked.append({"path": path, "size": size, "mtime": mtime})

    # 2. check every library file
    with lib.lock:
        tracks = [t for t in lib.tracks.values() if t.location]
    root_ok = {}
    gone, offline, stale = [], [], []
    for i, t in enumerate(tracks):
        if cancelled():
            raise Cancelled()
        if i % 500 == 0:
            progress(f"Checking library files ({i:,} of {len(tracks):,})", 0.3 + 0.6 * i / max(1, len(tracks)))
        root = _root_of(t.location)
        if root not in root_ok:
            root_ok[root] = os.path.isdir(root) if root else True
        if not root_ok[root]:
            offline.append(t)
            continue
        try:
            st = os.stat(t.location)
        except FileNotFoundError:
            gone.append(t)
            continue
        except OSError:
            offline.append(t)
            continue
        if t.modified and st.st_mtime > t.modified + STALE_TOLERANCE:
            stale.append((t, st.st_mtime))

    # 3. match missing entries to untracked files
    progress("Matching moved files...", 0.92)
    by_name_size = defaultdict(list)
    by_size = defaultdict(list)
    for f in untracked:
        by_name_size[(os.path.basename(f["path"]).lower(), f["size"])].append(f)
        by_size[f["size"]].append(f)
    claimed = set()
    moved, missing = [], []
    for t in gone:
        name = os.path.basename(t.location).lower()
        ext = os.path.splitext(name)[1]
        cands = [f for f in by_name_size.get((name, t.size), []) if f["path"] not in claimed]
        exact = list(cands)
        confidence = "high"
        if len(cands) != 1:
            # same size and type, different name (renamed file): only trust a unique match
            cands = [f for f in by_size.get(t.size, []) if f["path"] not in claimed
                     and f["path"].lower().endswith(ext)] if t.size else []
            confidence = "medium"
        if len(cands) == 1:
            f = cands[0]
            claimed.add(f["path"])
            moved.append({**t.brief(), "new_path": f["path"], "confidence": confidence})
        else:
            # several identical candidates: let the user choose rather than guess
            options = exact if len(exact) > 1 else cands
            missing.append({**t.brief(), "candidates": [f["path"] for f in options][:10]})

    new = [f for f in untracked if f["path"] not in claimed]
    elapsed = time.time() - t0
    progress("Scan complete", 1.0)
    return {
        "finished_at": time.time(),
        "elapsed": round(elapsed, 1),
        "roots": roots,
        "unavailable_roots": unavailable_roots,
        "checked": len(tracks),
        "new": sorted(new, key=lambda f: f["path"].lower()),
        "moved": sorted(moved, key=lambda m: m["location"].lower()),
        "missing": sorted(missing, key=lambda m: m["location"].lower()),
        "offline": [t.brief() for t in offline],
        "stale": sorted(({**t.brief(), "file_mtime": m} for t, m in stale), key=lambda s: s["location"].lower()),
    }


def summarize(result):
    if not result:
        return None
    return {k: len(result[k]) for k in ("new", "moved", "missing", "offline", "stale")} | {
        "finished_at": result["finished_at"], "elapsed": result["elapsed"], "checked": result["checked"],
        "roots": result["roots"], "unavailable_roots": result["unavailable_roots"],
    }


def remove_items(result, kind, keys):
    """Drop applied items from a scan result so the UI updates without a rescan."""
    if not result:
        return
    keys = set(keys)
    field = "path" if kind == "new" else "pid"
    result[kind] = [x for x in result[kind] if x[field] not in keys]
