"""Application core: holds state and turns user/automation requests into jobs."""
import json
import logging
import os
import threading
import time

from . import playlists as pl
from .config import APP_DIR, Config
from .jobs import JobRunner
from .library import SHARING_HELP, Library, Track, find_library_xml, norm_path
from .scan import remove_items, run_scan, summarize
from .version import APP_NAME, AUTHOR, VERSION

log = logging.getLogger("toolkit")
HISTORY_PATH = os.path.join(APP_DIR, "history.json")
IGNORED_PATH = os.path.join(APP_DIR, "ignored.json")
BACKUP_DIR = os.path.join(APP_DIR, "removed")
# automation refuses to remove more than this many tracks in one go: a mass "missing" result
# usually means a folder was renamed or a share is half-mounted, which a person should look at
AUTO_REMOVE_LIMIT = 25


def _load_json(path, default):
    try:
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return default


def _save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


class Toolkit:
    def __init__(self):
        os.makedirs(APP_DIR, exist_ok=True)
        self.config = Config()
        self.lib = Library()
        self.scan_result = None
        self.history = _load_json(HISTORY_PATH, [])
        self.ignored = set(_load_json(IGNORED_PATH, []))
        self._hist_lock = threading.Lock()
        self.runner = JobRunner(on_finished=self._job_finished)
        self.last_auto = {"time": None, "reason": "", "summary": ""}
        self.reload_library(initial=True)

    # ---------- library ----------
    def reload_library(self, initial=False):
        configured = self.config.get()["library_xml"]
        if configured and not os.path.isfile(configured):
            log.warning("configured library XML %s not found - auto-detecting instead", configured)
        path = find_library_xml(configured)
        if not path:
            self.lib.error = "Couldn't find your iTunes library XML. " + SHARING_HELP
            return False
        try:
            secs = self.lib.load(path)
            log.info("loaded %s tracks from %s in %.2fs", len(self.lib.tracks), path, secs)
            return True
        except Exception as e:
            self.lib.error = f"Couldn't read {path}: {e}"
            log.exception("library load")
            return False

    def _fresh_library(self, ctx):
        if self.lib.xml_changed():
            ctx.say("Re-reading iTunes library...")
            self.reload_library()

    # ---------- ignore list ----------
    def ignore(self, paths, on=True):
        keys = {norm_path(p) for p in paths}
        self.ignored = (self.ignored | keys) if on else (self.ignored - keys)
        _save_json(IGNORED_PATH, sorted(self.ignored))
        if on:
            remove_items(self.scan_result, "new", paths)

    def _filter_ignored(self, result):
        result["new"] = [f for f in result["new"] if norm_path(f["path"]) not in self.ignored]
        return result

    # ---------- history ----------
    def add_history(self, title, source, status, summary, details=None):
        entry = {"time": time.time(), "title": title, "source": source, "status": status,
                 "summary": summary, "details": (details or [])[:500]}
        with self._hist_lock:
            self.history.insert(0, entry)
            del self.history[300:]
            _save_json(HISTORY_PATH, self.history)

    def clear_history(self):
        with self._hist_lock:
            self.history.clear()
            _save_json(HISTORY_PATH, self.history)

    def _job_finished(self, job):
        if job.kind in ("scan",) and job.status == "done":
            return  # scans aren't interesting history
        summary = job.result.get("summary") if isinstance(job.result, dict) else ""
        if job.status == "failed":
            summary = job.error
        elif job.status == "cancelled":
            summary = (summary + " " if summary else "") + "(cancelled)"
        self.add_history(job.title, job.source, job.status, summary or job.message, job.log)

    # ---------- scan ----------
    def start_scan(self, source="manual"):
        if self.runner.has_pending("scan"):
            return None

        def fn(ctx):
            self._fresh_library(ctx)
            res = run_scan(self.lib, self.config.get(), progress=ctx.say, cancelled=ctx.cancelled)
            self.scan_result = self._filter_ignored(res)
            s = summarize(self.scan_result)
            return {"summary": f"{s['new']} new, {s['moved']} moved, {s['missing']} missing, {s['stale']} need tag refresh"}

        return self.runner.submit("Scan library", fn, kind="scan", source=source)

    # ---------- actions (each runs on the job thread) ----------
    def _do_add(self, ctx, paths):
        it = ctx.itunes
        added, failed, copied = 0, 0, []
        for i, path in enumerate(paths):
            ctx.check()
            ctx.progress(i, len(paths), f"Adding {os.path.basename(path)}")
            if not os.path.isfile(path):
                ctx.log(f"SKIP (file no longer there): {path}")
                failed += 1
                continue
            try:
                ft = it.add_file(path)
                if ft is None:
                    ctx.log(f"REFUSED by iTunes: {path}")
                    failed += 1
                    continue
                loc = it.call(lambda: ft.Location) or path
                pid = it.pid_of(ft)
                t = it.call(lambda: Track(
                    pid=pid, name=ft.Name or "", artist=ft.Artist or "",
                    album_artist=ft.AlbumArtist or "", album=ft.Album or "", genre=ft.Genre or "",
                    composer=ft.Composer or "", year=ft.Year or 0, disc=ft.DiscNumber or 0,
                    track_no=ft.TrackNumber or 0, size=ft.Size or 0, location=loc,
                    modified=time.time(), compilation=bool(ft.Compilation)))
                self.lib.note_added(loc, t)
                if norm_path(loc) != norm_path(path):
                    # iTunes copied it into its media folder; don't offer the original again
                    copied.append(path)
                    self.lib.note_added(path)
                added += 1
                ctx.log(f"ADDED: {path}")
            except Exception as e:
                failed += 1
                ctx.log(f"ERROR: {path}: {e}")
        if copied:
            self.ignore(copied)
            ctx.log(f"Note: iTunes copied {len(copied)} file(s) into its media folder, so the originals were added to the ignore list.")
        remove_items(self.scan_result, "new", paths)
        return {"summary": f"Added {added} file(s)" + (f", {failed} failed" if failed else "")}

    def _do_relink(self, ctx, pairs):
        it = ctx.itunes
        ok = bad = 0
        done = []
        for i, (pid, new_path) in enumerate(pairs):
            ctx.check()
            ctx.progress(i, len(pairs), f"Relinking {os.path.basename(new_path)}")
            try:
                it.relink(pid, new_path)
                self.lib.note_relinked(pid, new_path)
                done.append(pid)
                ok += 1
                ctx.log(f"RELINKED: {pid} -> {new_path}")
            except Exception as e:
                bad += 1
                ctx.log(f"ERROR relinking {pid} -> {new_path}: {e}")
        remove_items(self.scan_result, "moved", done)
        return {"summary": f"Relinked {ok} track(s)" + (f", {bad} failed" if bad else "")}

    def _do_refresh(self, ctx, pids):
        it = ctx.itunes
        ok = bad = 0
        done = []
        for i, pid in enumerate(pids):
            ctx.check()
            t = self.lib.tracks.get(pid)
            ctx.progress(i, len(pids), f"Refreshing {t.name if t else pid}")
            try:
                it.refresh_tags(pid)
                self.lib.note_refreshed(pid)
                done.append(pid)
                ok += 1
            except Exception as e:
                bad += 1
                ctx.log(f"ERROR refreshing {t.location if t else pid}: {e}")
        remove_items(self.scan_result, "stale", done)
        return {"summary": f"Refreshed tags for {ok} track(s)" + (f", {bad} failed" if bad else "")}

    def _do_remove(self, ctx, pids):
        it = ctx.itunes
        backup = [self.lib.tracks[p].brief() | {"genre": self.lib.tracks[p].genre, "year": self.lib.tracks[p].year}
                  for p in pids if p in self.lib.tracks]
        os.makedirs(BACKUP_DIR, exist_ok=True)
        backup_path = os.path.join(BACKUP_DIR, time.strftime("removed-%Y%m%d-%H%M%S.json"))
        _save_json(backup_path, backup)
        ctx.log(f"Saved details of the removed entries to {backup_path}")
        ok = bad = 0
        done = []
        for i, pid in enumerate(pids):
            ctx.check()
            t = self.lib.tracks.get(pid)
            ctx.progress(i, len(pids), f"Removing {t.name if t else pid}")
            try:
                it.delete(pid)
                self.lib.note_removed(pid)
                done.append(pid)
                ok += 1
                ctx.log(f"REMOVED: {t.location if t else pid}")
            except Exception as e:
                bad += 1
                ctx.log(f"ERROR removing {pid}: {e}")
        remove_items(self.scan_result, "missing", done)
        return {"summary": f"Removed {ok} missing entr{'y' if ok == 1 else 'ies'}" + (f", {bad} failed" if bad else "")}

    def apply(self, action, ids, pairs=None):
        if action == "relink_to":
            # user picked the new file for a missing entry: [[pid, path], ...]
            pairs = [(p, path) for p, path in (pairs or []) if os.path.isfile(path)]
            if not pairs:
                raise ValueError("That file no longer exists")

            def fn(c):
                res = self._do_relink(c, pairs)
                remove_items(self.scan_result, "missing", [p for p, _ in pairs])
                remove_items(self.scan_result, "new", [path for _, path in pairs])
                return res
            return self.runner.submit(f"Relink {len(pairs)} track(s)", fn, kind="relink")
        ids = list(dict.fromkeys(ids))
        if not ids:
            raise ValueError("Nothing selected")
        if action == "add":
            return self.runner.submit(f"Add {len(ids)} new file(s)", lambda c: self._do_add(c, ids), kind="add")
        if action == "relink":
            moved = {m["pid"]: m["new_path"] for m in (self.scan_result or {}).get("moved", [])}
            pairs = [(p, moved[p]) for p in ids if p in moved]
            return self.runner.submit(f"Relink {len(pairs)} moved file(s)", lambda c: self._do_relink(c, pairs), kind="relink")
        if action == "refresh":
            return self.runner.submit(f"Refresh tags for {len(ids)} track(s)", lambda c: self._do_refresh(c, ids), kind="refresh")
        if action == "remove":
            return self.runner.submit(f"Remove {len(ids)} missing entr{'y' if len(ids) == 1 else 'ies'}",
                                      lambda c: self._do_remove(c, ids), kind="remove")
        raise ValueError(f"Unknown action {action}")

    # ---------- playlists ----------
    def playlist_opts(self, override=None):
        opts = self.config.get()["playlists"]
        if override:
            opts = {**opts, **override, "fallbacks": {**opts["fallbacks"], **(override.get("fallbacks") or {})}}
        return opts

    def playlist_preview(self, override=None):
        opts = self.playlist_opts(override)
        return pl.preview(self.lib.source_tracks(opts.get("source", "")), opts)

    def playlist_sync(self, source="manual"):
        opts = self.playlist_opts()
        pl.parse(opts["template"])  # validate before queueing

        def fn(ctx):
            self._fresh_library(ctx)
            stats = pl.sync(ctx.itunes, opts, self.lib.source_tracks(opts.get("source", "")), ctx)
            return {"summary": "Playlists: {created} created, {updated} updated, {deleted} removed, "
                               "{added} tracks added, {removed} tracks taken out".format(**stats)
                               + (f", {stats['errors']} errors" if stats["errors"] else ""),
                    "stats": stats}

        root = pl.parse(opts["template"])[0]
        return self.runner.submit(f"Build playlists in \"{root}\"", fn, kind="playlists", source=source)

    # ---------- automation ----------
    def run_automation(self, reason="manual", source="auto"):
        if self.runner.has_pending("auto"):
            return None
        cfg = self.config.get()
        a = cfg["automation"]

        def fn(ctx):
            self._fresh_library(ctx)
            ctx.say("Scanning...")
            res = self._filter_ignored(run_scan(self.lib, cfg, progress=lambda m, f=None: ctx.say(m), cancelled=ctx.cancelled))
            self.scan_result = res
            parts = []
            if a["relink_moved"]:
                pairs = [(m["pid"], m["new_path"]) for m in res["moved"] if m["confidence"] == "high"]
                if pairs:
                    parts.append(self._do_relink(ctx, pairs)["summary"])
            if a["add_new"] and res["new"]:
                parts.append(self._do_add(ctx, [f["path"] for f in res["new"]])["summary"])
            if a["refresh_tags"] and res["stale"]:
                parts.append(self._do_refresh(ctx, [s["pid"] for s in res["stale"]])["summary"])
            if a["remove_missing"] and res["missing"]:
                if len(res["missing"]) > AUTO_REMOVE_LIMIT:
                    msg = (f"Skipped removing {len(res['missing'])} missing entries - that's more than "
                           f"{AUTO_REMOVE_LIMIT}, so please review them yourself")
                    ctx.log(msg)
                    parts.append(msg)
                else:
                    parts.append(self._do_remove(ctx, [m["pid"] for m in res["missing"]])["summary"])
            if a["rebuild_playlists"]:
                try:
                    opts = self.playlist_opts()
                    stats = pl.sync(ctx.itunes, opts, self.lib.source_tracks(opts.get("source", "")), ctx)
                    parts.append(f"playlists: {stats['added']} added, {stats['removed']} taken out, {stats['created']} created")
                except pl.TemplateError as e:
                    parts.append(f"playlists skipped: {e}")
            summary = "; ".join(parts) or "Everything already up to date"
            self.last_auto = {"time": time.time(), "reason": reason, "summary": summary}
            return {"summary": summary}

        label = {"change": "files changed", "schedule": "scheduled", "manual": "run now"}.get(reason, reason)
        return self.runner.submit(f"Automatic tidy-up ({label})", fn, kind="auto", source=source)

    # ---------- state for the UI ----------
    def state(self):
        cfg = self.config.get()
        # no XML yet (sharing was off): keep looking, so turning it on in iTunes is picked up by itself
        if not self.lib.xml_path and time.time() - getattr(self, "_xml_retry", 0) > 5:
            self._xml_retry = time.time()
            if self.reload_library():
                log.info("library XML appeared - loaded")
        return {
            "app": {"name": APP_NAME, "version": VERSION, "author": AUTHOR},
            "library": self.lib.stats(),
            "scan": summarize(self.scan_result),
            "itunes": self.runner.itunes_status,
            "busy": self.runner.busy(),
            "jobs": [j.to_dict() for j in reversed(self.runner.jobs[-15:])],
            "config": cfg,
            "ignored_count": len(self.ignored),
            "last_auto": self.last_auto,
            "fields": pl.FIELDS,
            "source_playlists": self.lib.playlist_names(),
        }
