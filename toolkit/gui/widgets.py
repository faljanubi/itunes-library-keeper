"""Small building blocks shared by the pages."""
import time

from PySide6.QtCore import QByteArray, QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QLayout, QMessageBox, QPushButton, QSizePolicy,
                               QVBoxLayout, QWidget, QWidgetItem)

from . import theme

# ---------------------------------------------------------------- formatting


def fmt(n):
    return f"{int(n or 0):,}"


def plural(n, one, many=None):
    return f"{fmt(n)} {one if n == 1 else (many or one + 's')}"


def fmt_bytes(b):
    if not b:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    b = float(b)
    while b >= 1024 and i < len(units) - 1:
        b /= 1024
        i += 1
    return f"{b:.1f} {units[i]}" if i > 2 else f"{b:.0f} {units[i]}"


def ago(t):
    if not t:
        return "never"
    s = time.time() - t
    if s < 45:
        return "just now"
    if s < 3600:
        return f"{round(s / 60)} min ago"
    if s < 86400:
        return f"{round(s / 3600)} h ago"
    return when(t)


def when(t):
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(t)) if t else ""


LRM, LRI, FSI, PDI = "\u200e", "\u2066", "\u2068", "\u2069"


def path_text(p):
    """A Windows path that always reads left to right like Explorer, even with Arabic or Hebrew
    folder names: every segment is isolated so the bidi algorithm can't reorder the segments."""
    if not p:
        return ""
    parts = p.replace("/", "\\").split("\\")
    # LRI: each segment reads left to right like in Explorer ("06. <Arabic name>.mp3"),
    # and the Arabic inside it still reads right to left
    return LRM + (LRM + "\\" + LRM).join(LRI + s + PDI for s in parts)


def isolate(t):
    """User text (track names etc.) as its own bidi run inside surrounding UI text."""
    return FSI + (t or "") + PDI


# ---------------------------------------------------------------- icons

_SVG = {
    "home": '<path d="M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/>',
    "check": '<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
    "playlist": '<path d="M3 6h12M3 12h12M3 18h7"/><circle cx="18" cy="17" r="3"/><path d="M21 17V6"/>',
    "bolt": '<path d="M13 2 4 14h7l-1 8 9-12h-7z"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "gear": '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "link": '<path d="M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7"/><path d="M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7"/>',
    "alert": '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4M12 17h.01"/>',
    "tag": '<path d="M20.6 13.4 13.4 20.6a2 2 0 0 1-2.8 0L3 13V3h10l7.6 7.6a2 2 0 0 1 0 2.8z"/><circle cx="7.5" cy="7.5" r="1.5"/>',
    "cloudoff": '<path d="m2 2 20 20"/><path d="M5.8 5.8A7 7 0 0 0 6 20h11a5 5 0 0 0 2.3-.6M21.5 15.9A5 5 0 0 0 17 9h-1.3A7 7 0 0 0 9.4 4.6"/>',
    "folder": '<path d="M3 6a2 2 0 0 1 2-2h4.6l2 2H19a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "power": '<path d="M12 3v9"/><path d="M6.3 6.8a8 8 0 1 0 11.4 0"/>',
    "refresh": '<path d="M21 12a9 9 0 1 1-2.6-6.4L21 8"/><path d="M21 3v5h-5"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7h.01"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
    "x": '<path d="M18 6 6 18M6 6l12 12"/>',
    "trash": '<path d="M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6M10 11v6M14 11v6"/>',
    "note": '<path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>',
    "disc": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="2.5"/>',
    "mic": '<rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10v1a7 7 0 0 0 14 0v-1M12 18v4M8 22h8"/>',
    "drive": '<rect x="2" y="13" width="20" height="8" rx="2"/><path d="M5.5 13 8 4h8l2.5 9M6 17h.01M10 17h.01"/>',
}


def icon(name, color=None, size=20):
    color = color or theme.colors()["text"]
    body = _SVG.get(name, "")
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
           f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{body}</svg>')
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    ic = QIcon()
    for scale in (1, 2):
        pm = QPixmap(size * scale, size * scale)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        renderer.render(p)
        p.end()
        pm.setDevicePixelRatio(scale)
        ic.addPixmap(pm)
    return ic


def app_icon_pixmap(size=64):
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect x="0.5" y="0.5" width="31" height="31" rx="7.5" fill="#000" stroke="#3c3c3c"/>'
           '<path d="M14.5 22a3 3 0 1 1-2-2.8V9l11-2v11.5a3 3 0 1 1-2-2.8V10.4l-7 1.3z" fill="#fff"/></svg>')
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    renderer.render(p)
    p.end()
    return pm


def tile_pixmap(name, hue, box=28, solid=True):
    """An icon on a rounded colour tile: white glyph on the vivid hue (solid), or the hue's glyph
    on its soft tint (for bigger, calmer tiles inside cards)."""
    c = theme.colors()
    fill = theme.TILE[hue] if solid else c[hue + "_soft"]
    glyph = "#ffffff" if solid else c[hue]
    scale = 2
    pm = QPixmap(box * scale, box * scale)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(fill))
    r = box * scale
    p.drawRoundedRect(0, 0, r, r, r * 0.26, r * 0.26)
    inner = round(box * (0.6 if box < 32 else 0.55))
    off = (box - inner) * scale // 2
    p.drawPixmap(off, off, icon(name, glyph, inner).pixmap(inner * scale, inner * scale)
                 .scaled(inner * scale, inner * scale, Qt.KeepAspectRatio, Qt.SmoothTransformation))
    p.end()
    pm.setDevicePixelRatio(scale)
    return pm


def tile_label(name, hue, box=28, solid=True):
    lab = QLabel()
    lab.setPixmap(tile_pixmap(name, hue, box, solid))
    lab.setFixedSize(box, box)
    return lab


def icon_label(name, tone=None, size=22):
    lab = QLabel()
    color = theme.colors()[tone] if tone else None
    lab.setPixmap(icon(name, color, size).pixmap(size, size))
    lab.setFixedSize(size + 4, size + 4)
    lab.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
    return lab

# ---------------------------------------------------------------- labels & frames


def label(text="", name=None, wrap=False, muted=False, selectable=False):
    lab = QLabel(text)
    if name:
        lab.setObjectName(name)
    if muted:
        lab.setProperty("muted", True)
    if wrap:
        lab.setWordWrap(True)
    if selectable:
        lab.setTextInteractionFlags(Qt.TextSelectableByMouse)
    return lab


def badge(text, tone=None):
    b = QLabel(text)
    b.setObjectName("Badge")
    if tone:
        b.setProperty("tone", tone)
    b.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)
    return b


def button(text, on_click=None, primary=False, icon_name=None, tooltip=None):
    b = QPushButton(text)
    b.setAutoDefault(False)
    if primary:
        b.setProperty("primary", True)  # filled accent button, like WinUI's AccentButton
    if icon_name:
        b.setIcon(icon(icon_name, theme.colors()["on_accent"] if primary else None, 16))
    if tooltip:
        b.setToolTip(tooltip)
    if on_click:
        b.clicked.connect(lambda *_: on_click())
    b.setCursor(Qt.PointingHandCursor)
    return b


class Card(QFrame):
    def __init__(self, parent=None, pad=16):
        super().__init__(parent)
        self.setObjectName("Card")
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(pad, pad, pad, pad)
        self.lay.setSpacing(8)


class Banner(QFrame):
    def __init__(self, tone, icon_name, title, text=None, buttons=(), extra=None):
        super().__init__()
        self.setObjectName("Banner")
        if tone:
            self.setProperty("tone", tone)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(12)
        lay.addWidget(tile_label(icon_name, tone or "slate", 30), 0, Qt.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(4)
        col.addWidget(label(title, "H3", wrap=True))
        if text:
            col.addWidget(label(text, wrap=True))
        if extra is not None:
            col.addWidget(extra)
        lay.addLayout(col, 1)
        for b in buttons:
            lay.addWidget(b, 0, Qt.AlignVCenter)


def page_header(title, sub=None, actions=()):
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 8)
    col = QVBoxLayout()
    col.setSpacing(2)
    col.addWidget(label(title, "PageTitle"))
    sub_lab = label(sub or "", muted=True, wrap=True)
    sub_lab.setVisible(bool(sub))
    col.addWidget(sub_lab)
    lay.addLayout(col, 1)
    for a in actions:
        if a is not None:
            lay.addWidget(a, 0, Qt.AlignBottom)
    w.sub_label = sub_lab
    return w


def clear_layout(lay):
    while lay.count():
        it = lay.takeAt(0)
        if it.widget():
            it.widget().deleteLater()
        elif it.layout():
            clear_layout(it.layout())


class FlowLayout(QLayout):
    """Lays widgets out left to right and wraps them onto new lines (for chips and presets)."""

    def __init__(self, parent=None, spacing=6):
        super().__init__(parent)
        self._items = []
        self._sp = spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):
        self._items.append(item)

    def addWidget(self, w):
        super().addWidget(w)

    def count(self):
        return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientations(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        s = QSize()
        for it in self._items:
            s = s.expandedTo(it.minimumSize())
        return s

    def _do(self, rect, test):
        x, y, line_h = rect.x(), rect.y(), 0
        for it in self._items:
            hint = it.sizeHint()
            nx = x + hint.width() + self._sp
            if nx - self._sp > rect.right() and line_h > 0:
                x, y = rect.x(), y + line_h + self._sp
                nx = x + hint.width() + self._sp
                line_h = 0
            if not test:
                it.setGeometry(QRect(QPoint(x, y), hint))
            x = nx
            line_h = max(line_h, hint.height())
        return y + line_h - rect.y()

# ---------------------------------------------------------------- dialogs


def confirm(parent, title, text, ok_label="Continue", danger=False, detail=None):
    box = QMessageBox(QMessageBox.Warning if danger else QMessageBox.Question, title, text, parent=parent)
    if detail:
        box.setInformativeText(detail)
    ok = box.addButton(ok_label, QMessageBox.AcceptRole)
    box.addButton("Cancel", QMessageBox.RejectRole)
    box.setDefaultButton(ok)
    box.exec()
    return box.clickedButton() is ok

# ---------------------------------------------------------------- toasts


class Toast(QFrame):
    closed = Signal()

    def __init__(self, host, title, msg, tone, action):
        super().__init__(host)
        self.setObjectName("Toast")
        if tone:
            self.setProperty("tone", tone)
        self.setFixedWidth(360)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 8, 10)
        col = QVBoxLayout()
        col.setSpacing(2)
        col.addWidget(label(title, "H3", wrap=True))
        if msg:
            col.addWidget(label(msg, muted=True, wrap=True))
        if action:
            b = QPushButton(action[0])
            b.setFlat(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda: (action[1](), self.dismiss()))
            col.addWidget(b, 0, Qt.AlignLeft)
        lay.addLayout(col, 1)
        x = QPushButton()
        x.setFlat(True)
        x.setIcon(icon("x", None, 14))
        x.setFixedSize(26, 26)
        x.setToolTip("Dismiss")
        x.clicked.connect(self.dismiss)
        lay.addWidget(x, 0, Qt.AlignTop)
        QTimer.singleShot(12000 if tone == "bad" else 7000, self.dismiss)

    def dismiss(self):
        if self.isVisible():
            self.hide()
            self.closed.emit()
            self.deleteLater()


class ToastHost:
    """Stacks toasts in the bottom-right corner of a window."""

    def __init__(self, window, bottom_offset=lambda: 0):
        self.window = window
        self.toasts = []
        self.bottom_offset = bottom_offset

    def show(self, title, msg="", tone="", action=None):
        t = Toast(self.window, title, msg, tone, action)
        t.closed.connect(lambda: (self.toasts.remove(t) if t in self.toasts else None, self.relayout()))
        self.toasts.append(t)
        t.adjustSize()
        t.show()
        t.raise_()
        self.relayout()
        return t

    def relayout(self):
        y = self.window.height() - 16 - self.bottom_offset()
        for t in reversed(self.toasts):
            t.adjustSize()
            y -= t.height()
            t.move(self.window.width() - t.width() - 16, y)
            t.raise_()
            y -= 8
