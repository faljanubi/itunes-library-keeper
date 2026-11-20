"""Main window, notification-area icon and application start-up."""
import logging
import os
import sys

from PySide6.QtCore import QByteArray, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QGuiApplication, QIcon
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel, QMainWindow, QMenu, QMessageBox,
                               QProgressBar, QPushButton, QSizePolicy, QStackedWidget, QStyleFactory, QSystemTrayIcon, QVBoxLayout,
                               QWidget)

from .. import startup
from ..config import APP_DIR, PORTABLE, SEEDED_FROM_USER_DIR, window_settings
from ..version import APP_NAME, VERSION
from . import theme
from .pages import KINDS, ApplyAllDialog, OverviewPage, ReviewPage
from .pages_more import ActivityPage, AutomationPage, PlaylistsPage, SettingsPage
from .widgets import (Banner, ToastHost, app_icon_pixmap, button, clear_layout, fmt, icon, isolate, label, plural,
                      tile_pixmap)

log = logging.getLogger("toolkit")
INSTANCE_KEY = "iTunesLibraryKeeper-" + os.environ.get("USERNAME", "user")

NAV = [
    ("overview", "Overview", "home", "info"),
    ("review", "Review changes", "check", "violet"),
    ("playlists", "Playlists", "playlist", "pink"),
    ("automation", "Automation", "bolt", "orange"),
    ("activity", "Activity", "clock", "teal"),
    ("settings", "Settings", "gear", "slate"),
]


class NavButton(QPushButton):
    def __init__(self, text, icon_name, hue):
        super().__init__()
        self.hue = hue
        self.setObjectName("Nav")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setAutoDefault(False)
        self.icon_name = icon_name
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 0, 10, 0)
        lay.setSpacing(10)
        self.ic = QLabel()
        self.ic.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.txt = QLabel(text)
        self.txt.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.count = QLabel()
        self.count.setObjectName("Badge")
        self.count.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.count.hide()
        lay.addWidget(self.ic)
        lay.addWidget(self.txt, 1)
        self.count.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        lay.addWidget(self.count, 0, Qt.AlignVCenter)
        self.setMinimumHeight(40)
        self.setAccessibleName(text)
        self.toggled.connect(lambda _: self.recolor())
        self.recolor()

    def recolor(self):
        c = theme.colors()
        on = self.isChecked()
        # each page has its own colour: a solid tile for the icon, and its tint when selected
        self.ic.setPixmap(tile_pixmap(self.icon_name, self.hue, 26))
        self.txt.setStyleSheet(f"color: {c['text']}; font-weight: {600 if on else 400};")
        self.setStyleSheet(f"QPushButton#Nav:checked {{ background: {c[self.hue + '_soft']}; }}")

    def set_count(self, n, hot=False, text=None):
        if n is None and not text:
            self.count.hide()
            return
        self.count.setText(text or fmt(n))
        self.count.setProperty("tone", self.hue if hot else None)
        self.count.style().unpolish(self.count)
        self.count.style().polish(self.count)
        self.count.show()


class MainWindow(QMainWindow):
    def __init__(self, tk, automation, start_hidden=False):
        super().__init__()
        self.tk, self.automation = tk, automation
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QIcon(app_icon_pixmap(256)))
        self.setMinimumSize(QSize(980, 640))
        self.review_kind = None
        self.review_filter = ""
        self.selection = {}
        self.watched = set()
        self.seen_done = set()
        self.scan_stamp = None
        self.quit_when_idle = False
        self.really_quit = False
        self.tray_hint_shown = False
        self.page_id = "overview"
        self.state = None
        self.refresh_state()
        for j in self.state["jobs"]:
            if j["status"] in ("done", "failed", "cancelled"):
                self.seen_done.add(j["id"])
        self.scan_stamp = self.state["scan"]["finished_at"] if self.state["scan"] else None
        self.init_selection()

        # ---- layout
        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self.build_sidebar())
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)
        self.banner_holder = QVBoxLayout()
        self.banner_holder.setContentsMargins(28, 16, 28, 0)
        self.banner_sig = None
        rl.addLayout(self.banner_holder)
        self.stack = QStackedWidget()
        self.pages = {"overview": OverviewPage(self), "review": ReviewPage(self), "playlists": PlaylistsPage(self),
                      "automation": AutomationPage(self), "activity": ActivityPage(self), "settings": SettingsPage(self)}
        for p in self.pages.values():
            self.stack.addWidget(p)
        rl.addWidget(self.stack, 1)
        rl.addWidget(self.build_dock())
        root.addWidget(right, 1)
        self.setCentralWidget(central)
        self.toasts = ToastHost(self, lambda: self.dock.height() if self.dock.isVisible() else 0)

        self.build_tray()
        self.apply_look()
        QGuiApplication.styleHints().colorSchemeChanged.connect(lambda *_: self.apply_look(rebuild=True))

        settings = window_settings()
        geo = settings.value("geometry")
        if isinstance(geo, QByteArray):
            self.restoreGeometry(geo)
        else:
            self.resize(1240, 820)

        self.go("overview")
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.timer.start(1000)
        if not start_hidden:
            self.show()
        if self.tk.config.load_error:
            log.warning(self.tk.config.load_error)
            QTimer.singleShot(800, lambda: self.toast("Settings reset", self.tk.config.load_error, "bad"))

    # ------------------------------------------------------------ chrome
    def build_sidebar(self):
        side = QWidget()
        side.setObjectName("Sidebar")
        side.setFixedWidth(232)
        lay = QVBoxLayout(side)
        lay.setContentsMargins(12, 16, 12, 14)
        lay.setSpacing(4)
        brand = QHBoxLayout()
        logo = QLabel()
        pm = app_icon_pixmap(72)
        pm.setDevicePixelRatio(2)
        logo.setPixmap(pm)
        brand.addWidget(logo)
        bcol = QVBoxLayout()
        bcol.setSpacing(0)
        bcol.addWidget(label(APP_NAME, "BrandName"))
        bcol.addWidget(label(f"Version {VERSION}", muted=True))
        brand.addLayout(bcol, 1)
        lay.addLayout(brand)
        lay.addSpacing(14)
        self.nav = {}
        for pid, text, ic, hue in NAV:
            b = NavButton(text, ic, hue)
            b.clicked.connect(lambda _=False, p=pid: self.go(p))
            self.nav[pid] = b
            lay.addWidget(b)
        lay.addStretch(1)
        self.auto_status = label(muted=True, wrap=True)
        self.itunes_status = label(muted=True, wrap=True)
        lay.addWidget(self.auto_status)
        lay.addWidget(self.itunes_status)
        lay.addSpacing(6)
        self.quit_btn = button("Quit app", self.quit_app, icon_name="power")
        lay.addWidget(self.quit_btn)
        return side

    def build_dock(self):
        self.dock = QFrame()
        self.dock.setObjectName("Dock")
        lay = QHBoxLayout(self.dock)
        lay.setContentsMargins(28, 10, 28, 10)
        col = QVBoxLayout()
        col.setSpacing(3)
        top = QHBoxLayout()
        self.dock_title = label("", "H3")
        self.dock_queue = label("", muted=True)
        top.addWidget(self.dock_title)
        top.addWidget(self.dock_queue)
        top.addStretch(1)
        col.addLayout(top)
        self.dock_msg = label("", muted=True)
        col.addWidget(self.dock_msg)
        self.dock_bar = QProgressBar()
        self.dock_bar.setTextVisible(False)
        self.dock_bar.setFixedHeight(6)
        col.addWidget(self.dock_bar)
        lay.addLayout(col, 1)
        self.dock_cancel = button("Cancel", lambda: self.cancel_job(self.dock_job))
        lay.addWidget(self.dock_cancel)
        self.dock_job = None
        self.dock.hide()
        return self.dock

    def build_tray(self):
        self.tray = QSystemTrayIcon(QIcon(app_icon_pixmap(64)), self)
        self.tray.setToolTip(APP_NAME)
        m = QMenu()
        m.addAction("Open " + APP_NAME, self.show_window)
        m.addSeparator()
        m.addAction("Scan now", self.start_scan)
        m.addAction("Run automation now",
                    lambda: self.start_job(lambda: self.tk.run_automation("manual", source="manual")))
        m.addSeparator()
        m.addAction("Quit", self.quit_app)
        self.tray_menu = m
        self.tray.setContextMenu(m)
        self.tray.activated.connect(lambda reason: self.show_window()
                                    if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick) else None)
        self.tray.messageClicked.connect(self.show_window)
        self.tray.show()

    def apply_look(self, rebuild=False):
        theme.apply_palette(QApplication.instance())
        QApplication.instance().setStyleSheet(theme.stylesheet() + self.nav_stylesheet())
        theme.set_titlebar_dark(self.winId(), theme.is_dark())
        for b in self.nav.values():
            b.recolor()
        self.quit_btn.setIcon(icon("power", None, 16))
        if rebuild:
            self.banner_sig = None
            self.update_chrome()
            self.rebuild()

    @staticmethod
    def nav_stylesheet():
        c = theme.colors()
        return f"""
        QPushButton#Nav {{ border: none; border-radius: 6px; background: transparent; text-align: left; }}
        QPushButton#Nav:hover {{ background: {c['card2']}; }}
        QPushButton#Nav:checked {{ background: {c['accent_soft']}; }}
        QPushButton[primary="true"] {{ background: {c['accent']}; color: {c['on_accent']}; border: 1px solid {c['accent']};
                                       border-radius: 5px; padding: 5px 14px; min-height: 20px; }}
        QPushButton[primary="true"]:hover {{ background: {c['accent_hover']}; border-color: {c['accent_hover']}; }}
        QPushButton[primary="true"]:pressed {{ background: {c['accent_soft']}; color: {c['accent_text']}; }}
        QPushButton[primary="true"]:disabled {{ background: {c['card2']}; color: {c['muted']}; border-color: {c['border']}; }}
        """

    def show_window(self):
        self.show()
        if self.isMinimized():
            self.showNormal()
        self.raise_()
        self.activateWindow()
        theme.set_titlebar_dark(self.winId(), theme.is_dark())

    # ------------------------------------------------------------ state
    def refresh_state(self):
        st = self.tk.state()
        st["automation"] = self.automation.describe()
        st["startup"] = startup.is_enabled()
        st["data_dir"] = APP_DIR
        st["portable"] = PORTABLE
        self.state = st
        return st

    @property
    def scan(self):
        return self.tk.scan_result

    def pending_count(self):
        s = self.state["scan"]
        return (s["new"] + s["moved"] + s["missing"] + s["stale"]) if s else 0

    def init_selection(self):
        self.selection = {}
        scan = self.scan
        if not scan:
            return
        for kind, k in KINDS.items():
            self.selection[kind] = {x[k["key"]] for x in scan.get(kind) or [] if k["preselect"](x)}

    def poll(self):
        try:
            st = self.refresh_state()
        except Exception:
            log.exception("state")
            return
        stamp = st["scan"]["finished_at"] if st["scan"] else None
        scan_changed = stamp != self.scan_stamp
        if scan_changed:
            self.scan_stamp = stamp
            self.init_selection()
        finished_any = self.handle_jobs(st["jobs"])
        self.update_chrome()
        page = self.pages[self.page_id]
        if (scan_changed or finished_any) and self.page_id in ("overview", "review"):
            self.rebuild()
        else:
            page.soft()
        self.timer.setInterval(700 if st["busy"] else 2000)
        if self.quit_when_idle and not st["busy"]:
            log.info("window closed earlier and the last task has finished - quitting")
            self.really_quit = True
            QApplication.instance().quit()

    def handle_jobs(self, jobs):
        finished_any = False
        for j in jobs:
            if j["status"] not in ("done", "failed", "cancelled") or j["id"] in self.seen_done:
                continue
            self.seen_done.add(j["id"])
            finished_any = True
            if j["id"] not in self.watched and j["source"] != "auto":
                continue
            self.watched.discard(j["id"])
            full = self.tk.runner.get(j["id"])
            msg = (full.result or {}).get("summary") if full and isinstance(full.result, dict) else None
            msg = msg or j["message"]
            tone = {"done": "good", "failed": "bad"}.get(j["status"], "warn")
            if self.isVisible() and not self.isMinimized():
                self.toast(j["title"], msg, tone, ("Details", lambda: self.go("activity")))
            else:
                self.tray.showMessage(j["title"], msg or "", QSystemTrayIcon.Warning if tone == "bad" else QSystemTrayIcon.Information, 6000)
        return finished_any

    def update_chrome(self):
        st = self.state
        n = self.pending_count()
        self.nav["review"].set_count(n if st["scan"] else None, hot=bool(n))
        self.nav["activity"].set_count(None, text="working" if st["busy"] else None, hot=True)
        a = st["automation"]
        self.auto_status.setText(("● " if a["status"] == "on" else "○ ") + ("Automation on" if a["status"] == "on" else "Automation off"))
        it = st["itunes"] or ""
        if it.startswith("connected"):
            txt = "● " + it.replace("connected ", "").strip("()")
        elif it.startswith("cannot"):
            txt = "● iTunes unreachable"
        else:
            txt = "○ iTunes: connects when needed"
        self.itunes_status.setText(txt)
        self.itunes_status.setToolTip(it)
        self.quit_btn.setToolTip("Stop iTunes Library Keeper. Automation is on, so closing the window alone keeps it running "
                                 "in the notification area." if a["status"] == "on"
                                 else "Stop iTunes Library Keeper now. Closing the window also quits it.")
        self.tray.setToolTip(f"{APP_NAME}\n" + ("Automation on" if a["status"] == "on" else "Automation off")
                             + (" · working..." if st["busy"] else ""))
        # sharing banner (shown above every page)
        problem = st["library"].get("sharing_problem")
        if problem != self.banner_sig:
            self.banner_sig = problem
            clear_layout(self.banner_holder)
            if problem:
                steps = label("1. Open iTunes and choose <b>Edit &gt; Preferences</b>.<br>"
                              "2. Click the <b>Advanced</b> tab.<br>"
                              "3. Tick <b>“Share iTunes Library XML with other applications”</b> and click <b>OK</b>.<br>"
                              "<span>This message goes away by itself once iTunes writes the file.</span>", wrap=True)
                steps.setTextFormat(Qt.RichText)
                self.banner_holder.addWidget(Banner("bad", "alert", "Turn on library sharing in iTunes", problem, extra=steps))
        # progress dock
        job = next((j for j in st["jobs"] if j["status"] == "running"), None)
        queued = sum(1 for j in st["jobs"] if j["status"] == "queued")
        if not job:
            if self.dock.isVisible():
                self.dock.hide()
                self.toasts.relayout()
        else:
            self.dock_job = job["id"]
            pct = None if job["progress"] is None else round(job["progress"] * 100)
            self.dock_title.setText(job["title"] + (f"   {pct}%" if pct is not None else ""))
            self.dock_queue.setText(f"· {queued} queued" if queued else "")
            self.dock_msg.setText(isolate(job["message"] or ""))
            if pct is None:
                self.dock_bar.setRange(0, 0)
            else:
                self.dock_bar.setRange(0, 1000)
                self.dock_bar.setValue(int(job["progress"] * 1000))
            if not self.dock.isVisible():
                self.dock.show()
                QTimer.singleShot(0, self.toasts.relayout)

    # ------------------------------------------------------------ navigation
    def go(self, page_id, sub=None):
        if page_id == "review" and sub:
            if sub != self.review_kind:
                self.review_filter = ""
            self.review_kind = sub
        self.page_id = page_id
        for pid, b in self.nav.items():
            b.setChecked(pid == page_id)
        self.stack.setCurrentWidget(self.pages[page_id])
        self.rebuild()

    def rebuild(self):
        self.pages[self.page_id].build()

    # ------------------------------------------------------------ actions
    def toast(self, title, msg="", tone="", action=None):
        self.toasts.show(title, msg, tone, action)

    def start_job(self, fn):
        try:
            job = fn()
        except Exception as e:
            self.toast("Couldn't start", str(e), "bad")
            return None
        if job is None:
            self.toast("Already running", "That task is already queued.", "warn")
            return None
        self.watched.add(job.id)
        QTimer.singleShot(150, self.poll)
        return job

    def start_scan(self):
        return self.start_job(lambda: self.tk.start_scan())

    def cancel_job(self, job_id):
        if job_id and self.tk.runner.cancel(job_id):
            self.toast("Cancelling", "Stopping after the current item. Work done so far is kept.", "warn")

    def save_config(self, patch):
        try:
            self.state["config"] = self.tk.config.update(patch)
        except Exception as e:
            self.toast("Couldn't save", str(e), "bad")
            raise

    def suggested_folders(self):
        """Folders holding the library's files (cached per library load)."""
        key = self.tk.lib.loaded_at
        if getattr(self, "_suggest_key", None) != key:
            try:
                self._suggest = self.tk.lib.suggest_watch_folders()
            except Exception:
                self._suggest = []
            self._suggest_key = key
        cur = [os.path.normcase(w).rstrip("\\") + "\\" for w in self.state["config"]["watch_folders"]]
        return [f for f in self._suggest
                if not any((os.path.normcase(f).rstrip("\\") + "\\").startswith(w) for w in cur)]

    def watch_folders(self, folders, scan=True):
        cur = self.state["config"]["watch_folders"]
        new = [f for f in (os.path.normpath(p) for p in folders) if f not in cur]
        if not new:
            return
        self.save_config({"watch_folders": cur + new})
        if scan:
            self.toast("Watch folder added" if len(new) == 1 else f"{len(new)} watch folders added", "Scanning now...")
            self.start_scan()
        self.refresh_state()
        QTimer.singleShot(0, self.rebuild)  # not mid-click: the clicked button gets rebuilt

    def set_theme(self, choice):
        self.save_config({"theme": choice})
        theme.apply_scheme(choice)
        QTimer.singleShot(0, lambda: self.apply_look(rebuild=True))

    def apply_selection(self, kind):
        k = KINDS[kind]
        sel = self.selection.get(kind) or set()
        ids = list(sel)
        if not ids:
            return
        items = [x for x in self.scan.get(kind) or [] if x[k["key"]] in sel]
        if kind == "missing":
            plays = sum(x.get("plays") or 0 for x in items)
            rated = sum(1 for x in items if x.get("rating"))
            detail = ""
            if plays or rated:
                detail = (f"They have {plural(plays, 'play')} and {plural(rated, 'rating')} between them, which will be lost. "
                          "If the files were moved, add their folder as a watch folder and rescan, so they can be relinked instead.\n\n")
            detail += "Your files aren't touched. A list of the removed entries is saved in the app's data folder."
            if not self.confirm(f"Remove {plural(len(ids), 'entry', 'entries')} from iTunes?",
                                "These entries point to files that no longer exist. Removing them also removes them from your playlists.",
                                "Remove", True, detail):
                return
        if kind == "moved" and any(x.get("confidence") != "high" for x in items):
            if not self.confirm("Relink likely matches?", "Some selected matches are based only on file size and type "
                                "(the file name changed). Make sure they're the right files.", "Relink"):
                return
        action = {"new": "add", "moved": "relink", "missing": "remove", "stale": "refresh"}[kind]
        self.start_job(lambda: self.tk.apply(action, ids))

    def confirm(self, title, text, ok_label, danger=False, detail=None):
        from .widgets import confirm
        return confirm(self, title, text, ok_label, danger, detail)

    def apply_all(self):
        sc = self.scan or {}
        allk = lambda k: sc.get(k) or []
        moved = allk("moved")
        likely = [x for x in moved if x.get("confidence") != "high"]
        ambiguous = [x for x in allk("missing") if x.get("candidates")]
        removable = [x for x in allk("missing") if not x.get("candidates")]
        plays = sum(x.get("plays") or 0 for x in removable)
        groups = [
            ("moved", "relink", moved, f"Relink {plural(len(moved), 'moved track')}",
             f"{fmt(len(likely))} matched only by size and type" if likely else ""),
            ("new", "add", allk("new"), f"Add {plural(len(allk('new')), 'new file')} to iTunes", ""),
            ("stale", "refresh", allk("stale"), f"Refresh tags for {plural(len(allk('stale')), 'track')}", ""),
            ("missing", "remove", removable, f"Remove {plural(len(removable), 'missing entry', 'missing entries')}",
             "; ".join(x for x in [f"{plural(plays, 'play')} will be lost" if plays else "", "also removes them from playlists"] if x)),
        ]
        groups = [g for g in groups if g[2]]
        if not groups:
            self.toast("Nothing to apply", "Missing tracks with several matching files need you to pick one."
                       if ambiguous else "Your library is in sync.")
            return
        dlg = ApplyAllDialog(self, groups, len(ambiguous))
        if dlg.exec() != ApplyAllDialog.Accepted:
            return
        queued = 0
        for kind, action, items, _t, _n in groups:
            if not dlg.boxes[kind].isChecked():
                continue
            key = KINDS[kind]["key"]
            ids = [x[key] for x in items]
            if self.start_job(lambda a=action, i=ids: self.tk.apply(a, i)):
                queued += 1
        if queued:
            self.toast("Applying changes", f"{plural(queued, 'task')} queued. Progress shows at the bottom of the window.")

    # ------------------------------------------------------------ closing
    def quit_app(self):
        st = self.state
        busy = any(j["status"] == "running" for j in st["jobs"])
        auto = st["config"]["automation"]["enabled"]
        msg = " ".join(x for x in ["A task is running; it will be stopped." if busy else "",
                                   "Automation stops until you start the app again." if auto else ""] if x) \
            or "You can start it again from the iTunes Library Keeper shortcut."
        if not self.isVisible():
            self.show_window()
        if not self.confirm("Quit iTunes Library Keeper?", msg, "Quit"):
            return
        self.really_quit = True
        self.close()
        QApplication.instance().quit()

    def quit_on_request(self):
        """Quit without asking (Setup/Uninstall sent --quit); a running task finishes first."""
        log.info("asked to quit by another process (Setup/Uninstall)")
        window_settings().setValue("geometry", self.saveGeometry())
        if self.refresh_state()["busy"]:
            self.hide()
            self.quit_when_idle = True
            return
        self.really_quit = True
        self.tray.hide()
        self.close()
        QApplication.instance().quit()

    def closeEvent(self, e):
        window_settings().setValue("geometry", self.saveGeometry())
        if self.really_quit:
            self.tray.hide()
            e.accept()
            return
        st = self.refresh_state()
        if st["config"]["automation"]["enabled"]:
            e.ignore()
            self.hide()
            if not self.tray_hint_shown:
                self.tray_hint_shown = True
                self.tray.showMessage(APP_NAME, "Still running in the notification area because automation is on. "
                                      "Right-click this icon and choose Quit to stop it.", QSystemTrayIcon.Information, 6000)
            return
        if st["busy"]:
            # let the current task finish, then quit by itself
            e.ignore()
            self.hide()
            self.quit_when_idle = True
            self.tray.showMessage(APP_NAME, "Finishing the current task, then closing.", QSystemTrayIcon.Information, 5000)
            return
        self.tray.hide()
        e.accept()
        QApplication.instance().quit()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.toasts.relayout()


def run(background=False, quit_running=False):
    """Start the GUI. If another copy is running, bring that one to the front instead.
    With quit_running, only ask a running copy to quit (Setup/Uninstall use this) and exit."""
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(VERSION)
    app.setOrganizationName("Faris Aljanubi")
    app.setQuitOnLastWindowClosed(False)
    if "windows11" in [k.lower() for k in QStyleFactory.keys()]:
        app.setStyle("windows11")  # Qt's native Windows 11 look
    if sys.platform == "win32":
        try:  # own taskbar button/icon instead of python.exe's
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("FarisAljanubi.iTunesLibraryKeeper")
        except Exception:
            pass

    sock = QLocalSocket()
    sock.connectToServer(INSTANCE_KEY)
    if sock.waitForConnected(500):
        if quit_running or not background:
            sock.write(b"quit" if quit_running else b"show")
            sock.flush()
            sock.waitForBytesWritten(500)
        sock.disconnectFromServer()
        return 0
    if quit_running:
        return 0  # nothing running

    from ..app import Toolkit
    from ..watcher import Automation

    tk = Toolkit()
    theme.apply_scheme(tk.config.get().get("theme", "system"))
    automation = Automation(tk)
    startup.migrate()
    win = MainWindow(tk, automation, start_hidden=background)

    server = QLocalServer()
    QLocalServer.removeServer(INSTANCE_KEY)
    server.listen(INSTANCE_KEY)

    def incoming():
        c = server.nextPendingConnection()
        if c is None:
            return
        c.waitForReadyRead(300)
        msg = bytes(c.readAll())
        if msg.startswith(b"show"):
            win.show_window()
        elif msg.startswith(b"quit"):
            win.quit_on_request()
        c.disconnectFromServer()
    server.newConnection.connect(incoming)
    log.info("%s %s started%s%s", APP_NAME, VERSION, " (portable, data in %s)" % APP_DIR if PORTABLE else "",
             " in the background" if background else "")
    if SEEDED_FROM_USER_DIR:
        log.info("portable data folder started from a copy of the settings in %APPDATA%")
    return app.exec()
