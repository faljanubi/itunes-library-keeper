"""Playlists, Automation, Activity and Settings pages."""
import copy
import os
import re

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QFileDialog, QFormLayout, QFrame, QGroupBox,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QPlainTextEdit, QProgressBar, QPushButton, QRadioButton, QScrollArea, QSpinBox,
                               QSplitter, QToolButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from .. import playlists as pl
from .. import startup
from ..app import AUTO_REMOVE_LIMIT
from ..version import SOURCE_URL
from . import theme
from .pages import Page, grid
from .widgets import (Banner, Card, FlowLayout, ago, app_icon_pixmap, badge, button, clear_layout, confirm, fmt, icon,
                      isolate, label, page_header, path_text, plural, when)

# ================================================================ playlists

PRESETS = [
    ("Albums by artist", "Albums by Artist / {albumartist:1} / {albumartist} / {album} ({year})"),
    ("Artists (one list each)", "Artists / {albumartist:1} / {albumartist}"),
    ("Genre › artist", "By Genre / {genre} / {albumartist} / {album}"),
    ("Decade › year", "By Year / {decade} / {year} / {albumartist} - {album}"),
    ("Composers", "Composers / {composer:1} / {composer}"),
]


def bold(widget):
    f = widget.font()
    f.setBold(True)
    widget.setFont(f)
    return widget


class PlaylistsPage(Page):
    scroll = False

    def content(self):
        st = self.st
        opts = copy.deepcopy(st["config"]["playlists"])
        self.lay.addWidget(page_header("Playlists", "Build a folder tree of playlists from your tags, like a custom browser inside iTunes."))
        split = QSplitter(Qt.Horizontal)
        split.setChildrenCollapsible(False)

        # ---- left: settings (scrolls on its own)
        left_inner = QWidget()
        form = QVBoxLayout(left_inner)
        form.setContentsMargins(16, 16, 16, 16)
        form.setSpacing(8)
        form.addWidget(label("Folder structure", "H3"))
        self.tpl = QLineEdit(opts["template"])
        mono = QFont("Consolas")
        mono.setPointSizeF(self.font().pointSizeF() + 0.5)
        self.tpl.setFont(mono)
        self.tpl.setMinimumHeight(34)
        form.addWidget(self.tpl)
        form.addWidget(label("Levels are separated by \" / \". The first level is the root folder, the last is the playlist "
                             "name, and anything in between becomes folders.", muted=True, wrap=True))
        self.err = label("", "ErrorText", wrap=True)
        self.err.hide()
        form.addWidget(self.err)

        form.addWidget(label("Insert a field (add :1 to use just its first letter)", muted=True))
        chips = QWidget()
        flow = FlowLayout(chips)
        for f, desc in list(st["fields"].items()) + [("albumartist:1", "First letter of the album artist")]:
            b = QPushButton("{" + f + "}")
            b.setToolTip(desc)
            b.setCursor(Qt.PointingHandCursor)
            b.setAutoDefault(False)
            b.clicked.connect(lambda _=False, tok="{" + f + "}": self.insert(tok))
            flow.addWidget(b)
        form.addWidget(chips)
        form.addWidget(label("Or start from a preset", muted=True))
        presets = QWidget()
        pflow = FlowLayout(presets)
        for name, tpl in PRESETS:
            b = QPushButton(name)
            b.setCursor(Qt.PointingHandCursor)
            b.setAutoDefault(False)
            b.clicked.connect(lambda _=False, t=tpl: self.tpl.setText(t))
            pflow.addWidget(b)
        form.addWidget(presets)

        form.addSpacing(6)
        form.addWidget(label("Include tracks from", "H3"))
        self.src = QComboBox()
        self.src.addItem("Entire library", "")
        for n in st["source_playlists"]:
            self.src.addItem(n, n)
        self.src.setCurrentIndex(max(0, self.src.findData(opts.get("source", ""))))
        form.addWidget(self.src)
        form.addWidget(label("\"Music\" leaves out podcasts, audiobooks and videos.", muted=True, wrap=True))

        more = QToolButton()
        more.setText("More options")
        more.setCheckable(True)
        more.setArrowType(Qt.RightArrow)
        more.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        more.setAutoRaise(True)
        more.toggled.connect(lambda on: more.setArrowType(Qt.DownArrow if on else Qt.RightArrow))
        more_body = QWidget()
        mb = QVBoxLayout(more_body)
        mb.setContentsMargins(0, 0, 0, 0)
        self.ignore_the = QCheckBox("Ignore \"The\" for first letters  (\"The Beatles\" goes under B, not T)")
        self.ignore_the.setChecked(opts["ignore_the"])
        mb.addWidget(self.ignore_the)
        mb.addWidget(label("Name for compilations", "H3"))
        self.comp = QLineEdit(opts["compilation_artist"])
        mb.addWidget(self.comp)
        mb.addWidget(label("Used as album artist for compilation albums without one.", muted=True, wrap=True))
        mb.addWidget(label("When a field is empty, use", "H3"))
        fb = QFormLayout()
        self.fallbacks = {}
        for f in st["fields"]:
            e = QLineEdit(opts["fallbacks"].get(f, ""))
            e.setPlaceholderText("(leave out)")
            self.fallbacks[f] = e
            fb.addRow(QLabel("{" + f + "}"), e)
        mb.addLayout(fb)
        more_body.setVisible(False)
        more.toggled.connect(more_body.setVisible)
        form.addWidget(more, 0, Qt.AlignLeft)
        form.addWidget(more_body)

        row = QHBoxLayout()
        self.build_btn = button("Build in iTunes", self.build_playlists, primary=True, icon_name="playlist")
        row.addWidget(self.build_btn)
        row.addWidget(button("Save without building", self.save_only))
        row.addStretch(1)
        form.addLayout(row)
        form.addStretch(1)
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setWidget(left_inner)
        left_scroll.setFrameShape(QFrame.NoFrame)
        left_scroll.setStyleSheet("QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }")
        left = Card(pad=0)
        left.lay.addWidget(left_scroll)

        # ---- right: preview tree
        right = Card(pad=12)
        right.lay.addWidget(label("Preview", "H3"))
        self.stats = label(muted=True, wrap=True)
        right.lay.addWidget(self.stats)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Playlist", "Tracks"])
        self.tree.setUniformRowHeights(True)
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        right.lay.addWidget(self.tree, 1)

        split.addWidget(left)
        split.addWidget(right)
        split.setStretchFactor(0, 5)
        split.setStretchFactor(1, 4)
        self.lay.addWidget(split, 1)

        self.last_good = None
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self.refresh_preview)
        for w in [self.tpl, self.comp, *self.fallbacks.values()]:
            w.textChanged.connect(self.timer.start)
        self.src.currentIndexChanged.connect(self.timer.start)
        self.ignore_the.toggled.connect(self.timer.start)
        self.refresh_preview()

    def current(self):
        return {"template": self.tpl.text(), "source": self.src.currentData() or "", "ignore_the": self.ignore_the.isChecked(),
                "compilation_artist": self.comp.text(),
                "fallbacks": {k: e.text() for k, e in self.fallbacks.items()}}

    def insert(self, tok):
        self.tpl.insert(tok)
        self.tpl.setFocus()

    def refresh_preview(self):
        try:
            p = self.win.tk.playlist_preview(self.current())
        except (pl.TemplateError, ValueError) as e:
            self.err.setText(str(e))
            self.err.show()
            self.build_btn.setEnabled(False)
            return
        self.err.hide()
        self.build_btn.setEnabled(True)
        self.last_good = p
        self.stats.setText(f"{plural(p['playlists'], 'playlist')} in {plural(p['folders'], 'folder')} · "
                           f"{plural(p['tracks'], 'track')} · largest has {fmt(p['largest'])}")
        self.tree.setUpdatesEnabled(False)
        self.tree.clear()
        folder_icon, list_icon = icon("folder", theme.colors()["warn"], 16), icon("playlist", None, 16)

        def add(parent, nodes, depth):
            for n in nodes:
                it = QTreeWidgetItem([isolate(n["name"]), fmt(n["count"])])
                it.setIcon(0, list_icon if n["leaf"] else folder_icon)
                it.setTextAlignment(1, Qt.AlignRight | Qt.AlignVCenter)
                it.setToolTip(0, n["name"])
                if parent is None:
                    self.tree.addTopLevelItem(it)
                else:
                    parent.addChild(it)
                if n.get("children"):
                    add(it, n["children"], depth + 1)
                if n.get("truncated"):
                    it.addChild(QTreeWidgetItem([f"+{n['truncated']} more", ""]))
                it.setExpanded(depth < 1)
        add(None, p["tree"], 0)
        self.tree.setUpdatesEnabled(True)

    def save_only(self):
        self.win.save_config({"playlists": self.current()})
        self.win.toast("Saved", "Playlist settings saved.")

    def build_playlists(self):
        c = self.current()
        root = c["template"].split("/")[0].strip()
        n = plural(self.last_good["playlists"], "playlist") if self.last_good else "playlists"
        if not confirm(self, "Build these playlists in iTunes?",
                       f"iTunes Library Keeper will create and update {n} inside the folder “{root}”.",
                       "Build playlists",
                       detail="It owns that folder: playlists inside it that the template no longer produces are removed. "
                              "Nothing outside it is touched.\n\nThe first build of a large library can take a few minutes. "
                              "You can keep using iTunes, and cancel at any time."):
            return
        self.win.save_config({"playlists": c})
        self.win.start_job(lambda: self.win.tk.playlist_sync())

# ================================================================ automation


class AutomationPage(Page):
    def content(self):
        st, win = self.st, self.win
        a, cfg = st["config"]["automation"], st["config"]
        self.lay.addWidget(page_header("Automation", "Decide what iTunes Library Keeper may do on its own."))
        self.status_holder = QVBoxLayout()
        self.lay.addLayout(self.status_holder)
        self.status_sig = None
        self.soft()
        if not cfg["watch_folders"]:
            self.lay.addWidget(Banner("warn", "folder", "Add at least one watch folder first.", None,
                                      [button("Settings", lambda: win.go("settings"))]))

        def described(cb, desc, badge_w=None):
            box = QWidget()
            lay = QVBoxLayout(box)
            lay.setContentsMargins(0, 6, 0, 6)
            lay.setSpacing(2)
            head = QHBoxLayout()
            head.addWidget(bold(cb))
            if badge_w:
                head.addWidget(badge_w)
            head.addStretch(1)
            lay.addLayout(head)
            d = label(desc, muted=True, wrap=True)
            d.setContentsMargins(26, 0, 0, 0)
            lay.addWidget(d)
            return box

        def switch(key, title, desc, badge_w=None, confirm_on=None):
            cb = QCheckBox(title)
            cb.setChecked(bool(a[key]))

            def changed(on):
                if confirm_on and on and not confirm(self, confirm_on[0], confirm_on[1], "Turn on", danger=True):
                    cb.blockSignals(True)
                    cb.setChecked(False)
                    cb.blockSignals(False)
                    return
                win.save_config({"automation": {key: on}})
                if key == "enabled":
                    QTimer.singleShot(0, win.rebuild)
            cb.toggled.connect(changed)
            return described(cb, desc, badge_w)

        def number(key, title, suffix, lo, hi):
            row = QWidget()
            lay = QHBoxLayout(row)
            lay.setContentsMargins(0, 6, 0, 6)
            lay.addWidget(bold(label(title)), 1)
            sp = QSpinBox()
            sp.setRange(lo, hi)
            sp.setValue(int(a[key]))
            sp.setMinimumWidth(90)
            sp.setKeyboardTracking(False)
            sp.valueChanged.connect(lambda v: win.save_config({"automation": {key: v}}))
            lay.addWidget(sp)
            lay.addWidget(label(suffix, muted=True))
            return row

        when_card = Card()
        when_card.lay.addWidget(label("When to run", "H2"))
        when_card.lay.addWidget(switch("enabled", "Enable automation", "Master switch for everything on this page."))
        when_card.lay.addWidget(switch("watch", "Watch folders for changes",
                                       f"Runs shortly after files are added, moved or edited in your "
                                       f"{plural(len(cfg['watch_folders']), 'watch folder')}."))
        when_card.lay.addWidget(number("debounce_seconds", "Wait after the last change", "seconds", 5, 3600))
        when_card.lay.addWidget(number("interval_hours", "Also run every", "hours (0 = never)", 0, 168))
        cb = QCheckBox("Start with Windows")
        cb.setChecked(st["startup"])

        def startup_changed(on):
            try:
                startup.set_enabled(on)
                win.toast("Will start with Windows" if on else "Won't start with Windows")
            except Exception as e:
                win.toast("Couldn't change that", str(e), "bad")
                cb.blockSignals(True)
                cb.setChecked(not on)
                cb.blockSignals(False)
        cb.toggled.connect(startup_changed)
        when_card.lay.addWidget(described(cb, "Starts quietly in the notification area when you sign in, so automation keeps working."))
        when_card.lay.addStretch(1)

        what = Card()
        what.lay.addWidget(label("What it may do", "H2"))
        what.lay.addWidget(switch("relink_moved", "Relink moved files",
                                  "Only exact matches (same name and size). Keeps play counts and playlists.", badge("Safe", "good")))
        what.lay.addWidget(switch("add_new", "Add new files", "Adds new audio files from your watch folders."))
        what.lay.addWidget(switch("refresh_tags", "Refresh edited tags", "Tells iTunes to re-read tags you changed in other apps."))
        what.lay.addWidget(switch("rebuild_playlists", "Update playlists", "Keeps the playlist folder from the Playlists page up to date."))
        what.lay.addWidget(switch(
            "remove_missing", "Remove missing entries",
            f"Removes tracks whose files are gone. Skipped if more than {AUTO_REMOVE_LIMIT} are missing at once, which usually "
            "means a drive is disconnected or a folder was renamed.", badge("Careful", "warn"),
            ("Let automation remove tracks?", "Play counts, ratings and playlist memberships of removed tracks are lost. Moved files "
             "are relinked first, so only tracks whose file can't be found anywhere would be removed.")))
        what.lay.addStretch(1)
        if not a["enabled"]:
            what.setToolTip("Turn on \"Enable automation\" for these to take effect")
            what.setEnabled(False)
        self.lay.addWidget(grid([when_card, what], 2))
        self.lay.addStretch(1)

    def soft(self):
        st = self.st
        au = st["automation"]
        sig = (au["status"], au.get("pending"), au["text"], st["last_auto"]["time"], st["last_auto"]["summary"])
        if sig == self.status_sig:
            return
        self.status_sig = sig
        clear_layout(self.status_holder)
        on = au["status"] == "on"
        extra = QWidget()
        el = QVBoxLayout(extra)
        el.setContentsMargins(0, 2, 0, 0)
        el.setSpacing(2)
        el.addWidget(label("The app keeps running in the notification area after you close its window. Use Quit app to stop it."
                           if on else "While automation is off, closing the window quits the app.", muted=True, wrap=True))
        if st["last_auto"]["time"]:
            el.addWidget(label(f"Last run {ago(st['last_auto']['time'])}: {st['last_auto']['summary']}", muted=True, wrap=True))
        self.status_holder.addWidget(Banner(
            "good" if on else "orange", "bolt" if on else "info", "Automation is on" if on else "Automation is off",
            (au.get("pending") or au["text"]) if on else
            "When it's on, iTunes Library Keeper keeps iTunes in step with your folders in the background.",
            [button("Run now", lambda: self.win.start_job(lambda: self.win.tk.run_automation("manual", source="manual")))], extra))

# ================================================================ activity


class ActivityPage(Page):
    scroll = False

    def content(self):
        self.clear_btn = button("Clear log", self.clear_log, icon_name="trash",
                                tooltip="Remove every entry from the activity log")
        self.lay.addWidget(page_header("Activity", "Everything iTunes Library Keeper has done, newest first.",
                                       [self.clear_btn]))
        self.live = QVBoxLayout()
        self.live.setSpacing(8)
        self.lay.addLayout(self.live)
        split = QSplitter(Qt.Vertical)
        self.list = QTreeWidget()
        self.list.setHeaderLabels(["Status", "Task", "Result", "When"])
        self.list.setRootIsDecorated(False)
        self.list.setUniformRowHeights(True)
        self.list.setAlternatingRowColors(True)
        h = self.list.header()
        h.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.Interactive)
        h.setSectionResizeMode(2, QHeaderView.Stretch)
        h.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.list.setColumnWidth(1, 300)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setPlaceholderText("Select a task above to see what it did.")
        self.details.setFont(QFont("Consolas"))
        split.addWidget(self.list)
        split.addWidget(self.details)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        self.lay.addWidget(split, 1)
        self.list.currentItemChanged.connect(self.show_details)
        self.hist_sig = None
        self.live_sig = None
        self.soft()

    def soft(self):
        jobs = [j for j in self.st["jobs"] if j["status"] in ("running", "queued")]
        sig = [(j["id"], j["status"], j["message"], round(j["progress"] or 0, 2)) for j in jobs]
        if sig != self.live_sig:
            self.live_sig = sig
            clear_layout(self.live)
            for j in jobs:
                c = Card(pad=12)
                row = QHBoxLayout()
                col = QVBoxLayout()
                col.addWidget(label(j["title"], "H3"))
                col.addWidget(label("Queued" if j["status"] == "queued" else isolate(j["message"]), muted=True))
                if j["status"] == "running":
                    bar = QProgressBar()
                    bar.setTextVisible(False)
                    bar.setFixedHeight(6)
                    if j["progress"] is None:
                        bar.setRange(0, 0)
                    else:
                        bar.setRange(0, 1000)
                        bar.setValue(int(j["progress"] * 1000))
                    col.addWidget(bar)
                row.addLayout(col, 1)
                row.addWidget(button("Cancel", lambda jid=j["id"]: self.win.cancel_job(jid)))
                c.lay.addLayout(row)
                self.live.addWidget(c)
        hist = self.win.tk.history
        sig = (len(hist), hist[0]["time"] if hist else None)
        if sig != self.hist_sig:
            self.hist_sig = sig
            self.list.clear()
            self.details.clear()
            self.clear_btn.setEnabled(bool(hist))
            for e in hist:
                status = {"done": "Done", "failed": "Failed", "cancelled": "Cancelled"}.get(e["status"], e["status"])
                title = e["title"] + ("  (automatic)" if e.get("source") == "auto" else "")
                it = QTreeWidgetItem([status, title, isolate(e.get("summary") or ""), ago(e["time"])])
                it.setToolTip(3, when(e["time"]))
                it.setToolTip(2, e.get("summary") or "")
                it.setForeground(0, theme.qcolor({"done": "good", "failed": "bad", "cancelled": "warn"}.get(e["status"], "muted")))
                it.setData(0, Qt.UserRole, e)
                self.list.addTopLevelItem(it)
            if not hist:
                self.details.setPlainText("Nothing yet. Changes you apply, and automatic runs, show up here.")

    def clear_log(self):
        n = len(self.win.tk.history)
        if n and confirm(self, "Clear activity log", f"Remove all {plural(n, 'entry', 'entries')} from the activity log?",
                         "Clear log", danger=True, detail="This only clears the list. Nothing in iTunes changes."):
            self.win.tk.clear_history()
            self.soft()

    def show_details(self, cur, _prev):
        if not cur:
            return
        e = cur.data(0, Qt.UserRole)
        head = f"{e['title']}\n{when(e['time'])} · {e['status']}\n{e.get('summary') or ''}\n\n"
        self.details.setPlainText(head + ("\n".join(e.get("details") or []) or "No details recorded."))

# ================================================================ settings


class SettingsPage(Page):
    def content(self):
        st, win = self.st, self.win
        cfg = st["config"]
        self.lay.addWidget(page_header("Settings"))

        # ---- watch folders
        c = Card()
        c.lay.addWidget(label("Watch folders", "H2"))
        c.lay.addWidget(label("Where your music files live. Scans look here for new and moved files.", muted=True, wrap=True))
        self.folders = QListWidget()
        self.folders.setMinimumHeight(110)
        self.folders.setMaximumHeight(200)
        self.fill_folders()
        c.lay.addWidget(self.folders)
        row = QHBoxLayout()
        row.addWidget(button("Add folder...", self.add_folder, icon_name="plus"))
        rm = button("Remove", self.remove_folder)
        rm.setEnabled(False)
        self.folders.itemSelectionChanged.connect(lambda: rm.setEnabled(bool(self.folders.selectedItems())))
        row.addWidget(rm)
        row.addStretch(1)
        c.lay.addLayout(row)
        sugg = self.win.suggested_folders()
        if sugg:
            hint = QHBoxLayout()
            lead = "Your library also has music in " if cfg["watch_folders"] else "Your library's music is in "
            hint.addWidget(label(lead + ", ".join(path_text(f) for f in sugg) + ".",
                                 muted=True, wrap=True), 1)
            hint.addWidget(button("Add " + ("it" if len(sugg) == 1 else "them"), lambda: self.win.watch_folders(sugg)))
            c.lay.addLayout(hint)
        self.lay.addWidget(c)

        # ---- scanning
        c = Card()
        c.lay.addWidget(label("Scanning", "H2"))
        form = QFormLayout()
        self.ext = QLineEdit(" ".join(cfg["extensions"]))
        form.addRow("File types", self.ext)
        form.addRow("", label("Separated by spaces.", muted=True))
        self.excl = QPlainTextEdit("\n".join(cfg["exclude_folders"]))
        self.excl.setPlaceholderText("One per line, e.g. \\Voice Memos\\")
        self.excl.setFixedHeight(72)
        form.addRow("Skip folders containing", self.excl)
        c.lay.addLayout(form)
        hidden = QCheckBox("Skip hidden and system files")
        hidden.setChecked(cfg["skip_hidden"])
        hidden.toggled.connect(lambda on: win.save_config({"skip_hidden": on}))
        c.lay.addWidget(hidden)
        row = QHBoxLayout()
        row.addWidget(label(f"{plural(st['ignored_count'], 'file')} on the ignore list", muted=True))
        if st["ignored_count"]:
            row.addWidget(button("Clear", self.clear_ignored))
        row.addStretch(1)
        c.lay.addLayout(row)
        c.lay.addWidget(button("Save", self.save_scanning, primary=True), 0, Qt.AlignLeft)
        self.lay.addWidget(c)

        # ---- iTunes library
        c = Card()
        c.lay.addWidget(label("iTunes library", "H2"))
        kv = QFormLayout()
        kv.addRow("Library file", label(st["library"]["xml_path"] or "not found", selectable=True, wrap=True))
        kv.addRow("Last read", label(when(st["library"]["loaded_at"])))
        kv.addRow("iTunes", label(st["itunes"]))
        data = label(f'<a href="file:///{st["data_dir"]}">{st["data_dir"]}</a>')
        data.setOpenExternalLinks(True)
        kv.addRow("App data (portable)" if st.get("portable") else "App data", data)
        c.lay.addLayout(kv)
        c.lay.addWidget(label("Library XML location", "H3"))
        row = QHBoxLayout()
        self.xml = QLineEdit(cfg["library_xml"])
        self.xml.setPlaceholderText(st["library"]["xml_path"] or "Auto-detect")
        row.addWidget(self.xml, 1)
        row.addWidget(button("Browse...", self.browse_xml))
        c.lay.addLayout(row)
        c.lay.addWidget(label("Leave empty to find it automatically. iTunes must have \"Share iTunes Library XML with other "
                              "applications\" turned on (Preferences > Advanced).", muted=True, wrap=True))
        c.lay.addWidget(button("Save && reload", self.save_xml), 0, Qt.AlignLeft)
        self.lay.addWidget(c)

        # ---- appearance
        c = Card()
        c.lay.addWidget(label("Appearance", "H2"))
        c.lay.addWidget(label("Auto follows the Windows light/dark setting.", muted=True))
        row = QHBoxLayout()
        grp = QButtonGroup(c)
        cur = cfg.get("theme", "system")
        for value, text in (("system", "Auto"), ("light", "Light"), ("dark", "Dark")):
            r = QRadioButton(text)
            r.setChecked(cur == value)
            r.toggled.connect(lambda on, v=value: on and win.set_theme(v))
            grp.addButton(r)
            row.addWidget(r)
        row.addStretch(1)
        c.lay.addLayout(row)
        self.lay.addWidget(c)

        # ---- about
        app = st["app"]
        c = Card()
        c.lay.addWidget(label("About", "H2"))
        row = QHBoxLayout()
        logo = QLabel()
        pm = app_icon_pixmap(96)
        pm.setDevicePixelRatio(2)
        logo.setPixmap(pm)
        row.addWidget(logo)
        col = QVBoxLayout()
        col.addWidget(label(app["name"], "H2"))
        col.addWidget(label(f"Version {app['version']}", muted=True))
        row.addLayout(col, 1)
        c.lay.addLayout(row)
        kv = QFormLayout()
        kv.addRow("Created by", label(app["author"]))
        kv.addRow("Copyright", label(f"© 2026 {app['author']}"))
        kv.addRow("Licence", label("GNU GPL version 3 or later. Free software, with no warranty.", wrap=True))
        src = QLabel(f'<a href="{SOURCE_URL}">{SOURCE_URL.split("://", 1)[1]}</a>')
        src.setOpenExternalLinks(True)
        src.setTextInteractionFlags(Qt.TextBrowserInteraction)
        kv.addRow("Source code", src)
        c.lay.addLayout(kv)
        c.lay.addWidget(label("Not affiliated with Apple. iTunes is a trademark of Apple Inc. Nothing leaves your computer.",
                              muted=True, wrap=True))
        self.lay.addWidget(c)
        self.lay.addStretch(1)

    def fill_folders(self):
        self.folders.clear()
        for f in self.win.state["config"]["watch_folders"]:
            it = QListWidgetItem(icon("folder", theme.colors()["warn"], 16), path_text(f))
            it.setData(Qt.UserRole, f)
            it.setToolTip(f)
            self.folders.addItem(it)
        if not self.folders.count():
            it = QListWidgetItem("No watch folders yet.")
            it.setFlags(Qt.NoItemFlags)
            self.folders.addItem(it)

    def add_folder(self):
        p = QFileDialog.getExistingDirectory(self, "Add a watch folder")
        if not p:
            return
        p = os.path.normpath(p)
        cur = self.win.state["config"]["watch_folders"]
        if p not in cur:
            self.win.save_config({"watch_folders": cur + [p]})
            self.fill_folders()

    def remove_folder(self):
        gone = {it.data(Qt.UserRole) for it in self.folders.selectedItems()}
        self.win.save_config({"watch_folders": [f for f in self.win.state["config"]["watch_folders"] if f not in gone]})
        self.fill_folders()

    def clear_ignored(self):
        if confirm(self, "Clear the ignore list?", "Ignored files will be offered again on the next scan.", "Clear"):
            self.win.tk.ignore(list(self.win.tk.ignored), on=False)
            self.win.toast("Ignore list cleared")
            self.win.refresh_state()
            QTimer.singleShot(0, self.build)

    def save_scanning(self):
        self.win.save_config({"extensions": [e for e in re.split(r"[\s,;]+", self.ext.text()) if e],
                              "exclude_folders": [s.strip() for s in self.excl.toPlainText().split("\n") if s.strip()]})
        self.win.toast("Saved", "Rescan to apply the new settings.", "good", ("Rescan", self.win.start_scan))

    def browse_xml(self):
        start = self.xml.text() or self.st["library"]["xml_path"] or ""
        p, _ = QFileDialog.getOpenFileName(self, "Find iTunes Library XML", os.path.dirname(start) if start else "",
                                           "iTunes library (*.xml);;All files (*)")
        if p:
            self.xml.setText(os.path.normpath(p))

    def save_xml(self):
        path = self.xml.text().strip().strip('"')
        if path and not os.path.isfile(path):
            self.win.toast("File not found", f"There's no file at {path}. Check the path, or leave it empty to "
                                             "find the library automatically.", "bad")
            return
        self.win.save_config({"library_xml": path})
        ok = self.win.tk.reload_library()
        lib = self.win.tk.lib.stats()
        self.win.toast("Library reloaded" if ok else "Couldn't read the library",
                       f"{fmt(lib['tracks'])} tracks" if ok else lib["error"], "good" if ok else "bad")
        self.win.refresh_state()
        QTimer.singleShot(0, self.build)
