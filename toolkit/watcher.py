"""Background automation: watches folders for changes (debounced) and runs on a schedule."""
import logging
import os
import threading
import time

import win32con
import win32event
import win32file

log = logging.getLogger("toolkit")
NOTIFY = (win32con.FILE_NOTIFY_CHANGE_FILE_NAME | win32con.FILE_NOTIFY_CHANGE_DIR_NAME
          | win32con.FILE_NOTIFY_CHANGE_LAST_WRITE | win32con.FILE_NOTIFY_CHANGE_SIZE)


class Automation:
    def __init__(self, toolkit):
        self.tk = toolkit
        self.handles = {}       # folder -> change-notification handle
        self.cfg_version = -1
        self.last_change = None  # time of the most recent unprocessed change
        self.next_run = None
        self.status = "off"
        threading.Thread(target=self._loop, name="automation", daemon=True).start()

    def _close_all(self):
        for h in self.handles.values():
            try:
                win32file.FindCloseChangeNotification(h)
            except Exception:
                pass
        self.handles = {}

    def _open_handle(self, folder):
        if folder in self.handles or not os.path.isdir(folder):
            return False
        try:
            self.handles[folder] = win32file.FindFirstChangeNotification(folder, True, NOTIFY)
            return True
        except Exception as e:
            log.warning("cannot watch %s: %s", folder, e)
            return False

    def _setup(self, cfg):
        self._close_all()
        a = cfg["automation"]
        if not a["enabled"]:
            self.status, self.next_run, self.last_change, self.schedule_hours = "off", None, None, None
            return
        if a["watch"]:
            for folder in cfg["watch_folders"]:
                self._open_handle(folder)
        self.last_retry = time.time()
        hours = float(a.get("interval_hours") or 0)
        # keep the countdown running unless automation was just turned on or the interval changed,
        # so saving an unrelated setting (theme, playlists...) doesn't push the scheduled run back
        if self.status != "on" or hours != getattr(self, "schedule_hours", None):
            self.next_run = time.time() + hours * 3600 if hours > 0 else None
        self.schedule_hours = hours
        self.status = "on"

    def _retry_unavailable(self, cfg):
        """Start watching folders that were unavailable before (e.g. a drive plugged in later)."""
        if not cfg["automation"]["watch"] or time.time() - getattr(self, "last_retry", 0) < 30:
            return
        self.last_retry = time.time()
        for folder in cfg["watch_folders"]:
            if self._open_handle(folder):
                log.info("watch folder available again: %s", folder)
                self.last_change = time.time()  # pick up whatever is there now

    def describe(self):
        cfg = self.tk.config.get()
        a = cfg["automation"]
        if not a["enabled"]:
            return {"status": "off", "text": "Automation is off"}
        bits = []
        if a["watch"]:
            missing = [f for f in cfg["watch_folders"] if f not in self.handles]
            bits.append(f"watching {len(self.handles)} folder(s)" + (f" ({len(missing)} unavailable)" if missing else ""))
        if self.next_run:
            bits.append("next scheduled run " + time.strftime("%H:%M", time.localtime(self.next_run)))
        pending = None
        if self.last_change:
            wait = max(0, int(self.last_change + a["debounce_seconds"] - time.time()))
            pending = f"changes detected - running in {wait}s"
        return {"status": "on", "text": ", ".join(bits) or "on", "pending": pending,
                "next_run": self.next_run}

    def _loop(self):
        while True:
            try:
                self._tick()
            except Exception:
                log.exception("automation loop")
                time.sleep(5)

    def _tick(self):
        cfg_obj = self.tk.config
        if cfg_obj.version != self.cfg_version:
            self.cfg_version = cfg_obj.version
            self._setup(cfg_obj.get())
        if self.status != "on":
            time.sleep(1)
            return
        cfg = cfg_obj.get()
        a = cfg["automation"]
        self._retry_unavailable(cfg)
        handles = list(self.handles.values())
        if handles:
            # wait up to 1s for any folder to signal (limit 64 handles per wait)
            r = win32event.WaitForMultipleObjects(handles[:64], False, 1000)
            if win32event.WAIT_OBJECT_0 <= r < win32event.WAIT_OBJECT_0 + len(handles[:64]):
                h = handles[r - win32event.WAIT_OBJECT_0]
                try:
                    win32file.FindNextChangeNotification(h)
                except Exception:  # folder went away (drive unplugged): drop it, retried later
                    gone = [f for f, x in self.handles.items() if x == h]
                    for f in gone:
                        del self.handles[f]
                        log.info("watch folder unavailable: %s", f)
                    try:
                        win32file.FindCloseChangeNotification(h)
                    except Exception:
                        pass
                # our own jobs don't write into music folders, so any change is the user's
                self.last_change = time.time()
        else:
            time.sleep(1)
        now = time.time()
        if self.last_change and now - self.last_change >= a["debounce_seconds"]:
            if not self.tk.runner.busy():
                self.last_change = None
                self.tk.run_automation("change")
        if self.next_run and now >= self.next_run:
            hours = float(a.get("interval_hours") or 0)
            self.next_run = now + hours * 3600 if hours > 0 else None
            self.tk.run_automation("schedule")
