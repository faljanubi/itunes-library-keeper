"""Template-driven playlist folders ("custom browse").

A template like  "Albums by Artist / {albumartist:1} / {albumartist} / {album} ({year})"
puts every track in the playlist named by the last segment, inside the folders named
by the earlier ones. The first segment is the root folder this app manages; anything
inside it that the template no longer produces is removed on sync.
"""
import re
import unicodedata

FIELDS = {
    "artist": "Artist",
    "albumartist": "Album artist (falls back to artist; compilations use the compilation name)",
    "album": "Album",
    "year": "Year",
    "decade": "Decade, e.g. 1990s",
    "genre": "Genre",
    "composer": "Composer",
    "grouping": "Grouping",
    "disc": "Disc number",
}
TOKEN = re.compile(r"\{(\w+)(?::(1))?\}")
EMPTY_BRACKETS = re.compile(r"\(\s*\)|\[\s*\]")


class TemplateError(ValueError):
    pass


def parse(template):
    segs = [s.strip() for s in template.replace("\\", "/").split("/")]
    segs = [s for s in segs if s]
    if len(segs) < 2:
        raise TemplateError("Use at least two levels: a root folder, then the playlist name (e.g. \"By Genre / {genre}\").")
    if TOKEN.search(segs[0]):
        raise TemplateError("The first level is the root folder and must be plain text, e.g. \"Albums by Artist\".")
    for s in segs:
        for m in TOKEN.finditer(s):
            if m.group(1) not in FIELDS:
                raise TemplateError(f"Unknown field {{{m.group(1)}}}. Available: " + ", ".join("{%s}" % f for f in FIELDS))
    if not TOKEN.search(segs[-1]):
        raise TemplateError("The last level (the playlist name) should contain at least one field, e.g. {album}.")
    return segs


def _initial(value, ignore_the):
    v = value.strip()
    if ignore_the and v.lower().startswith("the ") and len(v) > 4:
        v = v[4:]
    if not v:
        return "#"
    c = unicodedata.normalize("NFD", v[0])[0].upper()
    return c if c.isalpha() else "#"


def field_value(t, name, opts):
    if name == "artist":
        return t.artist or t.album_artist
    if name == "albumartist":
        if t.album_artist:
            return t.album_artist
        if t.compilation:
            return opts.get("compilation_artist") or "Various Artists"
        return t.artist
    if name == "album":
        return t.album
    if name == "year":
        return str(t.year) if t.year else ""
    if name == "decade":
        return f"{t.year // 10 * 10}s" if t.year else ""
    if name == "genre":
        return t.genre
    if name == "composer":
        return t.composer
    if name == "grouping":
        return t.grouping
    if name == "disc":
        return f"Disc {t.disc}" if t.disc else ""
    return ""


def render_segment(seg, t, opts):
    fallbacks = opts.get("fallbacks", {})

    def sub(m):
        name, first = m.group(1), m.group(2)
        v = (field_value(t, name, opts) or "").strip()
        if not v:
            v = fallbacks.get(name, "")
        if first:
            return _initial(v, opts.get("ignore_the", True)) if v else "#"
        return v

    out = TOKEN.sub(sub, seg)
    out = EMPTY_BRACKETS.sub("", out)
    out = re.sub(r"\s{2,}", " ", out).strip(" -")
    return out or "(blank)"


def build(tracks, opts):
    """Return {path_tuple: [pids in play order]} for every playlist the template produces."""
    segs = parse(opts["template"])
    out = {}
    for t in tracks:
        path = (segs[0],) + tuple(render_segment(s, t, opts) for s in segs[1:])
        out.setdefault(path, []).append(t)
    for path, ts in out.items():
        ts.sort(key=lambda t: (t.disc or 0, t.track_no or 0, t.name.lower()))
        out[path] = [t.pid for t in ts]
    return out


def preview(tracks, opts, max_nodes=4000):
    """Nested tree for the UI: [{name, count, children}] plus totals."""
    desired = build(tracks, opts)
    root = {"name": "", "children": {}, "count": 0, "leaf": False}
    for path, pids in desired.items():
        node = root
        for i, part in enumerate(path):
            node = node["children"].setdefault(part, {"name": part, "children": {}, "count": 0, "leaf": False})
            node["count"] += len(pids)
        node["leaf"] = True
    budget = [max_nodes]

    def conv(n):
        budget[0] -= 1
        kids = sorted(n["children"].values(), key=lambda c: c["name"].lower())
        out = {"name": n["name"], "count": n["count"], "leaf": n["leaf"]}
        if kids:
            if budget[0] <= 0:
                out["truncated"] = len(kids)
                out["children"] = []
            else:
                out["children"] = [conv(k) for k in kids]
        return out

    folders = {p[:i] for p in desired for i in range(1, len(p))}
    tree = [conv(c) for c in sorted(root["children"].values(), key=lambda c: c["name"])]
    return {
        "tree": tree,
        "playlists": len(desired),
        "folders": len(folders),
        "tracks": sum(len(v) for v in desired.values()),
        "largest": max((len(v) for v in desired.values()), default=0),
    }


def existing_tree(records, root_name):
    """From itunes.user_playlists() records, map path_tuple -> record for everything
    inside the top-level folder named root_name (the root itself included)."""
    by_pid = {r["pid"]: r for r in records}
    roots = [r for r in records if r["folder"] and not r["parent"] and r["name"] == root_name]
    if not roots:
        return {}
    root_pids = {r["pid"] for r in roots}
    out = {}
    for r in records:
        parts, q, inside = [], r, False
        while q:
            parts.append(q["name"])
            if q["pid"] in root_pids:
                inside = True
                break
            q = by_pid.get(q["parent"])
        if inside:
            out.setdefault(tuple(reversed(parts)), r)
    return out


def sync(itunes, opts, tracks, ctx):
    """Make iTunes match the template. Reads the current tree from iTunes itself (not the
    possibly-stale XML) so repeated runs never create duplicates. ctx provides progress()/log()/check()."""
    desired = build(tracks, opts)
    root_name = parse(opts["template"])[0]
    ctx.progress(0, 1, "Reading existing playlists from iTunes...")
    existing = existing_tree(itunes.user_playlists(), root_name)
    stats = {"created": 0, "updated": 0, "deleted": 0, "added": 0, "removed": 0, "errors": 0}

    def get_obj(path, is_folder):
        cur = existing.get(path)
        if cur and cur["folder"] == is_folder:
            return cur["obj"]
        parent = get_obj(path[:-1], True) if len(path) > 1 else None
        obj = itunes.create(path[-1], is_folder, parent)
        existing[path] = {"pid": itunes.pid_of(obj), "folder": is_folder, "obj": obj, "new": True}
        stats["created"] += 1
        ctx.log(f"Created {'folder' if is_folder else 'playlist'}: {' / '.join(path)}")
        return obj

    items = sorted(desired.items())
    total = len(items)
    for i, (path, pids) in enumerate(items):
        ctx.check()
        ctx.progress(i, total, " / ".join(path[1:]))
        try:
            had = existing.get(path)
            is_new = not had or had["folder"] or had.get("new")
            pl = get_obj(path, False)
            if is_new:
                to_add, present = pids, 0
            else:
                to_add = [p for p in pids if not itunes.playlist_has(pl, p)]
                present = len(pids) - len(to_add)
            extra = []
            if not is_new and itunes.playlist_count(pl) > present:
                # it holds tracks the template no longer puts here: find and drop them
                want = set(pids)
                extra = [p for p in itunes.playlist_track_pids(pl) if p not in want]
                if extra:
                    itunes.remove_from_playlist(pl, extra)
                    stats["removed"] += len(extra)
            for pid in to_add:
                try:
                    itunes.add_to_playlist(pl, pid)
                    stats["added"] += 1
                except Exception as e:
                    stats["errors"] += 1
                    ctx.log(f"  could not add track {pid}: {e}")
            if not is_new and (to_add or extra):
                stats["updated"] += 1
        except Exception as e:
            stats["errors"] += 1
            ctx.log(f"Error on {' / '.join(path)}: {e}")

    # remove playlists/folders the template no longer produces (deepest first)
    wanted_paths = set(desired) | {p[:i] for p in desired for i in range(1, len(p))}
    for path in sorted(existing, key=len, reverse=True):
        if path in wanted_paths or len(path) == 1:
            continue
        ctx.check()
        try:
            itunes.delete_playlist(existing[path]["obj"])
            stats["deleted"] += 1
            ctx.log(f"Removed: {' / '.join(path)}")
        except Exception as e:
            stats["errors"] += 1
            ctx.log(f"Could not remove {' / '.join(path)}: {e}")
    ctx.progress(total, total, "Done")
    return stats
