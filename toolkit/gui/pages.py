"""The six pages of the main window."""
import copy
import os

from PySide6.QtCore import (QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt, QTimer)
from PySide6.QtGui import QAction, QFont
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QFileDialog, QFormLayout, QFrame, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView,
                               QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu, QPlainTextEdit,
                               QProgressBar, QPushButton, QRadioButton, QScrollArea, QSizePolicy, QSpinBox, QSplitter,
                               QTableView, QTabBar, QToolButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from .. import playlists as pl
from .. import startup
from ..app import AUTO_REMOVE_LIMIT
from . import theme
from .widgets import (Banner, Card, FlowLayout, ago, badge, button, clear_layout, confirm, fmt, fmt_bytes, icon,
                      icon_label, isolate, label, page_header, path_text, plural, tile_label, when)

KINDS = {
    "new": dict(label="New files", icon="plus", tone="violet", key="path",
                desc="Audio files in your watch folders that aren't in iTunes yet.",
                empty="No new files - everything in your watch folders is already in iTunes.",
                preselect=lambda x: True),
    "moved": dict(label="Moved files", icon="link", tone="info", key="pid",
                  desc="Tracks whose file moved or was renamed. Relinking keeps ratings, play counts and playlists.",
                  empty="No moved files found.", preselect=lambda x: x.get("confidence") == "high"),
    "missing": dict(label="Missing files", icon="alert", tone="bad", key="pid",
                    desc="Tracks whose file is gone and couldn't be found anywhere in your watch folders.",
                    empty="No missing files - every track points to a file that exists.", preselect=lambda x: False),
    "stale": dict(label="Tag updates", icon="tag", tone="warn", key="pid",
                  desc="Files edited outside iTunes (e.g. in a tag editor) since iTunes last read them.",
                  empty="All tags are up to date.", preselect=lambda x: True),
    "offline": dict(label="Unavailable", icon="cloudoff", tone="info", key="pid",
                    desc="Tracks on a drive or network share that isn't connected. They're left alone.",
                    empty="All drives are connected.", preselect=lambda x: False),
}
ACTIONS = {"new": "add", "moved": "relink", "missing": "remove", "stale": "refresh"}


class Page(QScrollArea):
    """A scrollable page. build() recreates the content; soft() refreshes live bits only."""
    scroll = True

    def __init__(self, win):
        super().__init__()
        self.win = win
        self.setObjectName("Page")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.body = QWidget()
        self.body.setObjectName("PageBody")
        self.lay = QVBoxLayout(self.body)
        self.lay.setContentsMargins(28, 22, 28, 22)
        self.lay.setSpacing(14)
        self.setWidget(self.body)
        if not self.scroll:
            self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

    @property
    def st(self):
        return self.win.state

    def build(self):
        clear_layout(self.lay)
        self.content()

    def content(self):
        pass

    def soft(self):
        pass

    def scan_btn(self, text="Scan now", primary=True):
        running = any(j["kind"] == "scan" and j["status"] in ("queued", "running") for j in self.st["jobs"])
        b = button(text, self.win.start_scan, primary=primary, icon_name="refresh")
        b.setEnabled(not running)
        return b


def grid(widgets, cols, spacing=12):
    w = QWidget()
    g = QGridLayout(w)
    g.setContentsMargins(0, 0, 0, 0)
    g.setSpacing(spacing)
    for i, x in enumerate(widgets):
        g.addWidget(x, i // cols, i % cols)
    for c in range(cols):
        g.setColumnStretch(c, 1)
    return w

# ================================================================ overview


class OverviewPage(Page):
    def content(self):
        st, win = self.st, self.win
        lib, scan, cfg = st["library"], st["scan"], st["config"]
        sub = (f"Last scan {ago(scan['finished_at']) if scan else 'never'} · library read {ago(lib['loaded_at'])}"
               if lib["tracks"] else "")
        self.lay.addWidget(page_header("Overview", sub, [self.scan_btn()]))

        if lib.get("error") and not lib.get("sharing_problem"):
            self.lay.addWidget(Banner("bad", "alert", "Can't read your iTunes library", lib["error"],
                                      [button("Open settings", lambda: win.go("settings"))]))
        if not cfg["watch_folders"]:
            sugg = win.suggested_folders()
            if sugg:
                where = ", ".join(path_text(f) for f in sugg)
                text = (f"New files are only found inside watch folders, and none are set yet. "
                        f"Your library's music is in {where}.")
                acts = [button("Watch " + ("this folder" if len(sugg) == 1 else "these folders"),
                               lambda: win.watch_folders(sugg), primary=True),
                        button("Choose another folder...", self.add_first_folder)]
            else:
                text = "New files are only found inside watch folders, and none are set yet."
                acts = [button("Choose a folder...", self.add_first_folder, primary=True)]
            self.lay.addWidget(Banner("warn", "folder", "New music can't be found yet", text, acts))
        if scan and scan["unavailable_roots"]:
            self.lay.addWidget(Banner("warn", "cloudoff", "Some watch folders aren't available",
                                      "These were skipped: " + ", ".join(scan["unavailable_roots"]) + ". Is a drive disconnected?"))

        stats = []
        for lab_text, value, ic, hue in (("Tracks", fmt(lib["tracks"]), "note", "pink"),
                                         ("Albums", fmt(lib["albums"]), "disc", "violet"),
                                         ("Artists", fmt(lib["artists"]), "mic", "info"),
                                         ("On disk", fmt_bytes(lib["size_bytes"]), "drive", "teal")):
            c = Card()
            row = QHBoxLayout()
            row.setSpacing(14)
            row.addWidget(tile_label(ic, hue, 40), 0, Qt.AlignVCenter)
            col = QVBoxLayout()
            col.setSpacing(0)
            col.addWidget(label(value, "StatValue"))
            col.addWidget(label(lab_text, muted=True))
            row.addLayout(col, 1)
            c.lay.addLayout(row)
            stats.append(c)
        self.lay.addWidget(grid(stats, 4))

        if not scan:
            c = Card(pad=28)
            t = label("Run your first scan", "H2")
            t.setAlignment(Qt.AlignHCenter)
            d = label("The scan only looks. Nothing in iTunes changes until you review and confirm.", muted=True, wrap=True)
            d.setAlignment(Qt.AlignHCenter)
            c.lay.addWidget(t)
            c.lay.addWidget(d)
            c.lay.addWidget(self.scan_btn(), 0, Qt.AlignHCenter)
            self.lay.addWidget(c)
            self.lay.addStretch(1)
            return

        total = win.pending_count()
        if total == 0 and not scan["roots"]:
            self.lay.addWidget(Banner("good", "check", "Library entries are fine",
                                      f"Checked {plural(scan['checked'], 'track')} in {scan['elapsed']}s. "
                                      "New files weren't looked for because no watch folder is set."))
        elif total == 0:
            self.lay.addWidget(Banner("good", "check", "Your library is in sync",
                                      f"Checked {plural(scan['checked'], 'track')} and {plural(len(scan['roots']), 'watch folder')} "
                                      f"in {scan['elapsed']}s. Nothing needs attention."))
        else:
            self.lay.addWidget(Banner("violet", "check", f"{plural(total, 'change')} ready",
                                      "Apply them all at once, or review each group first.",
                                      [button("Review", lambda: win.go("review")),
                                       button("Apply all changes", win.apply_all, primary=True)]))

        cards = [self.health_card(k, scan[k]) for k in ("new", "moved", "missing", "stale", "offline")]
        self.lay.addWidget(grid(cards, 3))

        a = st["automation"]
        c = Card()
        row = QHBoxLayout()
        col = QVBoxLayout()
        head = QHBoxLayout()
        head.addWidget(label("Automation", "H2"))
        head.addWidget(badge("On" if a["status"] == "on" else "Off", "good" if a["status"] == "on" else None))
        head.addStretch(1)
        col.addLayout(head)
        col.addWidget(label((a.get("pending") or a["text"]) if a["status"] == "on"
                            else "Turn it on to add, relink and refresh tracks by itself when your folders change.",
                            muted=True, wrap=True))
        if st["last_auto"]["time"]:
            col.addWidget(label(f"Last run {ago(st['last_auto']['time'])}: {st['last_auto']['summary']}", muted=True, wrap=True))
        row.addLayout(col, 1)
        row.addWidget(button("Configure" if a["status"] == "on" else "Set up", lambda: win.go("automation")))
        c.lay.addLayout(row)
        self.lay.addWidget(c)
        self.lay.addStretch(1)

    def health_card(self, kind, n):
        k = KINDS[kind]
        c = Card()
        top = QHBoxLayout()
        top.addWidget(tile_label(k["icon"], k["tone"] if n else "slate", 38, solid=False))
        top.addStretch(1)
        c.lay.addLayout(top)
        cnt = label(fmt(n), "HealthCount")
        if n:
            cnt.setStyleSheet(f"color: {theme.colors()[k['tone']]};")
        else:
            cnt.setProperty("muted", True)
        c.lay.addWidget(cnt)
        c.lay.addWidget(label(k["label"], "H3"))
        c.lay.addWidget(label(k["desc"], muted=True, wrap=True))
        c.lay.addStretch(1)
        if n:
            b = button("View" if kind == "offline" else "Review", lambda: self.win.go("review", kind),
                       primary=kind != "offline")
            c.lay.addWidget(b, 0, Qt.AlignLeft)
        return c

    def add_first_folder(self):
        p = QFileDialog.getExistingDirectory(self, "Choose a folder where your music lives")
        if p:
            self.win.watch_folders([p])

# ================================================================ review


class ScanModel(QAbstractTableModel):
    COLS = {
        "new": [("File", "path"), ("Size", "size"), ("Modified", "mtime")],
        "moved": [("Name", "name"), ("Artist", "artist"), ("Album", "album"), ("Was", "location"),
                  ("Now", "new_path"), ("Match", "confidence")],
        "missing": [("Name", "name"), ("Artist", "artist"), ("Album", "album"), ("Last known location", "location"),
                    ("Plays", "plays"), ("Rating", "rating"), ("Matches", "candidates")],
        "stale": [("Name", "name"), ("Artist", "artist"), ("Album", "album"), ("File", "location"), ("Edited", "file_mtime")],
        "offline": [("Name", "name"), ("Artist", "artist"), ("Album", "album"), ("Location", "location")],
    }

    def __init__(self, kind, items, sel, on_change):
        super().__init__()
        self.kind, self.items, self.sel, self.on_change = kind, items, sel, on_change
        self.key = KINDS[kind]["key"]
        self.checkable = kind != "offline"
        self.cols = self.COLS[kind]

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.items)

    def columnCount(self, parent=QModelIndex()):
        return len(self.cols)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.cols[section][0]
        return None

    def flags(self, index):
        f = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if self.checkable and index.column() == 0:
            f |= Qt.ItemIsUserCheckable
        return f

    def text(self, x, field):
        v = x.get(field)
        if field in ("path", "location", "new_path"):
            return path_text(v)
        if field == "size":
            return fmt_bytes(v)
        if field in ("mtime", "file_mtime"):
            return when(v)
        if field == "confidence":
            return "Exact" if v == "high" else "Likely"
        if field == "plays":
            return fmt(v)
        if field == "rating":
            if not v:
                return "—"
            r = round(v / 20)
            return "★" * r + "☆" * (5 - r)
        if field == "candidates":
            return f"{len(v)} identical file{'s' if len(v) != 1 else ''}" if v else ""
        return isolate(v or "") if field in ("name", "artist", "album") else (v or "")

    def sort_value(self, x, field):
        v = x.get(field)
        if field in ("size", "mtime", "file_mtime", "plays", "rating"):
            return v or 0
        if field == "candidates":
            return len(v or [])
        return str(v or "").lower()

    def data(self, index, role=Qt.DisplayRole):
        x = self.items[index.row()]
        field = self.cols[index.column()][1]
        if role == Qt.DisplayRole:
            if field == "name":
                return isolate(x.get("name") or "(untitled)")
            return self.text(x, field)
        if role == Qt.UserRole:
            return self.sort_value(x, field)
        if role == Qt.ToolTipRole:
            if field in ("path", "location", "new_path"):
                return x.get(field)
            if field == "confidence":
                return "Same file name and size" if x.get("confidence") == "high" else \
                    "Same size and type, different name - check before relinking"
            if field == "candidates" and x.get("candidates"):
                return "Double-click to pick the right file to relink:\n" + "\n".join(x["candidates"])
            return self.text(x, field)
        if role == Qt.CheckStateRole and self.checkable and index.column() == 0:
            return Qt.Checked if x[self.key] in self.sel else Qt.Unchecked
        if role == Qt.ForegroundRole and field == "confidence":
            return theme.qcolor("good" if x.get("confidence") == "high" else "warn")
        if role == Qt.ForegroundRole and field == "rating" and x.get("rating"):
            return theme.qcolor("warn")
        if role == Qt.ForegroundRole and field == "candidates":
            return theme.qcolor("info")
        if role == Qt.TextAlignmentRole and field in ("size", "plays"):
            return int(Qt.AlignRight | Qt.AlignVCenter)
        return None

    def setData(self, index, value, role=Qt.EditRole):
        if role == Qt.CheckStateRole and self.checkable:
            k = self.items[index.row()][self.key]
            if Qt.CheckState(value) == Qt.Checked:
                self.sel.add(k)
            else:
                self.sel.discard(k)
            self.dataChanged.emit(index, index, [Qt.CheckStateRole])
            self.on_change()
            return True
        return False

    def set_checked(self, rows, on):
        for r in rows:
            k = self.items[r][self.key]
            (self.sel.add if on else self.sel.discard)(k)
        if self.items:
            self.dataChanged.emit(self.index(0, 0), self.index(len(self.items) - 1, 0), [Qt.CheckStateRole])
        self.on_change()


class FilterProxy(QSortFilterProxyModel):
    def __init__(self):
        super().__init__()
        self.query = ""
        self.setSortRole(Qt.UserRole)

    def set_query(self, q):
        self.query = q.lower().strip()
        self.invalidateFilter()

    def filterAcceptsRow(self, row, parent):
        if not self.query:
            return True
        x = self.sourceModel().items[row]
        return any(v and self.query in str(v).lower()
                   for v in (x.get("path"), x.get("location"), x.get("new_path"), x.get("name"), x.get("artist"), x.get("album")))


class ReviewPage(Page):
    scroll = False

    def content(self):
        win, scan = self.win, self.win.scan
        self.lay.addWidget(page_header(
            "Review changes", "Nothing changes in iTunes until you apply. Use Apply all, or pick items in a group.",
            [button("Rescan", win.start_scan, icon_name="refresh"),
             button(f"Apply all changes ({fmt(win.pending_count())})", win.apply_all, primary=True, icon_name="check")
             if win.pending_count() else None]))
        if not scan:
            c = Card(pad=28)
            c.lay.addWidget(label("No scan yet", "H2"))
            c.lay.addWidget(label("Run a scan from the Overview first.", muted=True))
            self.lay.addWidget(c)
            self.lay.addStretch(1)
            return
        kind = win.review_kind
        if kind not in KINDS:
            kind = next((k for k in ("new", "moved", "missing", "stale") if scan.get(k)), "new")
            win.review_kind = kind

        tabs = QTabBar()
        tabs.setExpanding(False)
        tabs.setDrawBase(False)
        keys = list(KINDS)
        for k in keys:
            tabs.addTab(f"{KINDS[k]['label']}  ({fmt(len(scan.get(k) or []))})")
        tabs.setCurrentIndex(keys.index(kind))
        tabs.currentChanged.connect(lambda i: win.go("review", keys[i]))
        self.lay.addWidget(tabs)
        desc = KINDS[kind]["desc"]
        if kind == "missing" and any(x.get("candidates") for x in scan.get(kind) or []):
            desc += " Where identical files were found, double-click the track to pick the right one to relink."
        self.lay.addWidget(label(desc, muted=True, wrap=True))

        items = scan.get(kind) or []
        sel = win.selection.setdefault(kind, set())
        if not items:
            c = Card(pad=28)
            c.lay.addWidget(label("All clear", "H2"))
            c.lay.addWidget(label(KINDS[kind]["empty"], muted=True, wrap=True))
            self.lay.addWidget(c)
            self.lay.addStretch(1)
            return

        card = Card(pad=12)
        bar = QHBoxLayout()
        self.search = QLineEdit(win.review_filter)
        self.search.setPlaceholderText("Filter by name, artist, album or path")
        self.search.setClearButtonEnabled(True)
        self.search.addAction(icon("search", None, 16), QLineEdit.LeadingPosition)
        self.search.setMinimumWidth(280)
        bar.addWidget(self.search)
        self.count_lbl = label(muted=True)
        bar.addWidget(self.count_lbl)
        bar.addStretch(1)
        selectable = kind != "offline"
        if selectable:
            bar.addWidget(button("Select all", lambda: self.model.set_checked(self.visible_rows(), True)))
            bar.addWidget(button("Select none", lambda: self.model.set_checked(self.visible_rows(), False)))
        if kind == "new":
            bar.addWidget(button("Ignore selected", self.ignore_selected,
                                 tooltip="Never offer these files again (undo in Settings)"))
        self.action_btn = button("", lambda: win.apply_selection(kind), primary=True)
        if selectable:
            bar.addWidget(self.action_btn)
        card.lay.addLayout(bar)

        self.model = ScanModel(kind, items, sel, self.update_bar)
        self.proxy = FilterProxy()
        self.proxy.setSourceModel(self.model)
        self.proxy.set_query(win.review_filter)
        view = QTableView()
        view.setModel(self.proxy)
        view.setSortingEnabled(True)
        view.sortByColumn(-1, Qt.AscendingOrder)
        view.setSelectionBehavior(QAbstractItemView.SelectRows)
        view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        view.setAlternatingRowColors(True)
        view.setWordWrap(False)
        view.setTextElideMode(Qt.ElideMiddle)
        view.verticalHeader().hide()
        view.verticalHeader().setDefaultSectionSize(view.fontMetrics().height() + 12)
        hdr = view.horizontalHeader()
        hdr.setStretchLastSection(False)
        hdr.setSectionResizeMode(QHeaderView.Interactive)
        # paths share the spare width; short columns fit their contents; names get a sensible start width
        widths = {"name": 220, "artist": 150, "album": 170, "candidates": 130}
        for i, (_title, field) in enumerate(self.model.cols):
            if field in ("path", "location", "new_path"):
                hdr.setSectionResizeMode(i, QHeaderView.Stretch)
            elif field in widths:
                view.setColumnWidth(i, widths[field])
            else:
                hdr.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        view.setContextMenuPolicy(Qt.CustomContextMenu)
        view.customContextMenuRequested.connect(self.context_menu)
        view.doubleClicked.connect(self.double_clicked)
        self.view = view
        card.lay.addWidget(view, 1)
        self.lay.addWidget(card, 1)

        self.search.textChanged.connect(self.filter_changed)
        self.update_bar()

    def visible_rows(self):
        return [self.proxy.mapToSource(self.proxy.index(r, 0)).row() for r in range(self.proxy.rowCount())]

    def filter_changed(self, text):
        self.win.review_filter = text
        self.proxy.set_query(text)
        self.update_bar()

    def update_bar(self):
        kind = self.model.kind
        n = len(self.model.sel)
        labels = {"new": f"Add {plural(n, 'file')} to iTunes", "moved": f"Relink {plural(n, 'track')}",
                  "missing": f"Remove {plural(n, 'entry', 'entries')} from iTunes", "stale": f"Refresh tags for {plural(n, 'track')}"}
        self.action_btn.setText(labels.get(kind, ""))
        self.action_btn.setEnabled(n > 0)
        txt = f"{fmt(n)} of {fmt(len(self.model.items))} selected"
        if self.win.review_filter:
            txt += f" · {fmt(self.proxy.rowCount())} match"
        self.count_lbl.setText(txt)

    def selected_rows(self):
        return sorted({self.proxy.mapToSource(i).row() for i in self.view.selectionModel().selectedRows()})

    def context_menu(self, pos):
        rows = self.selected_rows()
        if not rows:
            return
        m = QMenu(self)
        if self.model.checkable:
            m.addAction(f"Tick {plural(len(rows), 'row')}", lambda: self.model.set_checked(rows, True))
            m.addAction(f"Untick {plural(len(rows), 'row')}", lambda: self.model.set_checked(rows, False))
        x = self.model.items[rows[0]]
        if self.model.kind == "missing" and len(rows) == 1 and x.get("candidates"):
            m.addSeparator()
            m.addAction("Relink to one of the identical files...", lambda: self.pick_candidate(x))
        path = x.get("new_path") or x.get("path") or x.get("location")
        if path:
            m.addSeparator()
            folder = os.path.dirname(path)
            a = m.addAction("Open containing folder", lambda: os.startfile(folder) if os.path.isdir(folder) else None)
            a.setEnabled(os.path.isdir(folder))
            from PySide6.QtGui import QGuiApplication
            m.addAction("Copy path", lambda: QGuiApplication.clipboard().setText(path))
        m.exec(self.view.viewport().mapToGlobal(pos))

    def double_clicked(self, index):
        x = self.model.items[self.proxy.mapToSource(index).row()]
        if self.model.kind == "missing" and x.get("candidates"):
            self.pick_candidate(x)
        elif self.model.checkable:
            src = self.proxy.mapToSource(index).row()
            self.model.set_checked([src], x[self.model.key] not in self.model.sel)

    def pick_candidate(self, x):
        cands = x["candidates"]
        choice, ok = QInputDialog.getItem(self, "Relink missing track",
                                          f"Found {len(cands)} identical files for “{x.get('name') or 'this track'}”.\n"
                                          "Pick the right one to relink:", cands, 0, False)
        if ok and choice:
            self.win.start_job(lambda: self.win.tk.apply("relink_to", [], [[x["pid"], choice]]))

    def ignore_selected(self):
        paths = list(self.model.sel)
        if not paths:
            return
        self.win.tk.ignore(paths, on=True)
        self.model.sel.clear()
        self.win.toast("Ignored", f"{plural(len(paths), 'file')} won't be offered again.")
        self.win.rebuild()


class ApplyAllDialog(QDialog):
    def __init__(self, parent, groups, ambiguous):
        super().__init__(parent)
        self.setWindowTitle("Apply all changes?")
        self.setMinimumWidth(460)
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.addWidget(label("Everything the last scan found will be applied. Untick anything you want to leave for now.", wrap=True))
        self.boxes = {}
        for kind, _action, _items, text, note in groups:
            cb = QCheckBox(text)
            cb.setChecked(True)
            f = cb.font()
            f.setBold(True)
            cb.setFont(f)
            self.boxes[kind] = cb
            lay.addWidget(cb)
            if note:
                n = label(note, muted=True, wrap=True)
                n.setContentsMargins(26, 0, 0, 4)
                lay.addWidget(n)
        if ambiguous:
            lay.addWidget(label(f"{plural(ambiguous, 'missing track')} with several matching files "
                                f"{'is' if ambiguous == 1 else 'are'} skipped. Pick the right file on the Missing tab.",
                                muted=True, wrap=True))
        lay.addWidget(label("Your files aren't touched. Removed entries are saved to the app's data folder.", muted=True, wrap=True))
        bb = QDialogButtonBox()
        ok = bb.addButton("Apply", QDialogButtonBox.AcceptRole)
        ok.setDefault(True)
        bb.addButton("Cancel", QDialogButtonBox.RejectRole)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
