"""Light/dark handling. Controls (buttons, inputs, lists, menus, dialogs) are drawn by Qt's native
Windows 11 style; only the app's own pieces (cards, banners, badges, sidebar) get colours here."""
import ctypes
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication

THEMES = ("system", "light", "dark")
TONES = ("good", "warn", "bad", "info", "violet", "pink", "orange", "teal", "slate")

# Solid fills for the little icon tiles (white glyph on top); vivid enough to read in both schemes.
TILE = {"info": "#2f6fed", "violet": "#7c4dea", "pink": "#e0457b", "orange": "#f0711c", "teal": "#139f8e",
        "slate": "#64748b", "good": "#2a9d5c", "warn": "#d9901a", "bad": "#d64545"}

# The accent (primary buttons, checkboxes, selection) stays monochrome to match the black app icon:
# black on light, near-white on dark. Colour comes from the hues below - each page has its own,
# and the cards, badges and banners use them for their icons and tints.
LIGHT = {
    "card": "#ffffff", "card2": "#f4f4f4", "border": "#e2e2e2", "text": "#1a1a1a", "muted": "#6e6e6e",
    "sidebar": "#f1f1f1", "accent": "#1a1a1a", "accent_hover": "#3a3a3a", "on_accent": "#ffffff",
    "accent_soft": "#e4e4e4", "accent_text": "#000000",
    "good": "#1f9d55", "good_soft": "#e3f6ea", "warn": "#a86c12", "warn_soft": "#fdf3dc",
    "bad": "#c93838", "bad_soft": "#fde8e8", "info": "#2563eb", "info_soft": "#e3ecfd",
    "violet": "#7c3aed", "violet_soft": "#efe8fd", "pink": "#d6336c", "pink_soft": "#fce6ee",
    "orange": "#e8590c", "orange_soft": "#fdeadb", "teal": "#0c8f80", "teal_soft": "#dcf3ef",
    "slate": "#5b6b82", "slate_soft": "#e8ecf1",
}
DARK = {
    "card": "#262626", "card2": "#2e2e2e", "border": "#3a3a3a", "text": "#ededed", "muted": "#a3a3a3",
    "sidebar": "#1c1c1c", "accent": "#f0f0f0", "accent_hover": "#d0d0d0", "on_accent": "#141414",
    "accent_soft": "#363636", "accent_text": "#ffffff",
    "good": "#4cc47f", "good_soft": "#1b3326", "warn": "#e0a84a", "warn_soft": "#3a2f18",
    "bad": "#f07272", "bad_soft": "#3d1f22", "info": "#6aa1f5", "info_soft": "#1b2a42",
    "violet": "#a98bf7", "violet_soft": "#2c2442", "pink": "#f27aa3", "pink_soft": "#3d2130",
    "orange": "#fb9a52", "orange_soft": "#3c2819", "teal": "#3cc9b5", "teal_soft": "#16332f",
    "slate": "#9aa8bc", "slate_soft": "#283039",
}


def apply_scheme(choice):
    """choice: system | light | dark. Qt then repaints every native control in that scheme."""
    hints = QGuiApplication.styleHints()
    scheme = {"light": Qt.ColorScheme.Light, "dark": Qt.ColorScheme.Dark}.get(choice, Qt.ColorScheme.Unknown)
    hints.setColorScheme(scheme)


def apply_palette(app):
    """Use the monochrome accent for Qt's own controls too (checkboxes, switches, selections, focus)."""
    from PySide6.QtGui import QPalette
    # only these roles are set; every other role keeps following Qt's light/dark palette
    pal = QPalette()
    c = colors()
    for group in (QPalette.Active, QPalette.Inactive):
        pal.setColor(group, QPalette.Accent, QColor(c["accent"]))
        pal.setColor(group, QPalette.Highlight, QColor(c["accent"]))
        pal.setColor(group, QPalette.HighlightedText, QColor(c["on_accent"]))
    app.setPalette(pal)


def is_dark():
    return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark


def colors():
    return DARK if is_dark() else LIGHT


def qcolor(name):
    return QColor(colors()[name])


def set_titlebar_dark(win_id, dark):
    """Windows draws the title bar; ask it for the dark variant to match (Windows 10 2004+)."""
    if sys.platform != "win32":
        return
    try:
        value = ctypes.c_int(1 if dark else 0)
        for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (and its pre-20H1 number)
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(int(win_id), attr, ctypes.byref(value), ctypes.sizeof(value)) == 0:
                break
    except Exception:
        pass


def stylesheet():
    c = colors()
    banner_tones = "\n    ".join(
        f'QFrame#Banner[tone="{t}"] {{ background: {c[t + "_soft"]}; border-color: {c[t + "_soft"]}; }}' for t in TONES)
    badge_tones = "\n    ".join(
        f'QLabel#Badge[tone="{t}"] {{ background: {c[t + "_soft"]}; color: {c[t]}; }}' for t in TONES)
    return f"""
    QWidget#Sidebar {{ background: {c['sidebar']}; border-right: 1px solid {c['border']}; }}
    QLabel#BrandName {{ font-size: 10.5pt; font-weight: 600; }}
    QLabel#Muted, QLabel[muted="true"] {{ color: {c['muted']}; }}
    QLabel#PageTitle {{ font-size: 20pt; font-weight: 600; }}
    QLabel#H2 {{ font-size: 12.5pt; font-weight: 600; }}
    QLabel#H3 {{ font-size: 10.5pt; font-weight: 600; }}
    QLabel#StatValue {{ font-size: 20pt; font-weight: 600; }}
    QLabel#HealthCount {{ font-size: 22pt; font-weight: 600; }}
    QFrame#Card {{ background: {c['card']}; border: 1px solid {c['border']}; border-radius: 10px; }}
    QFrame#Card QLabel {{ background: transparent; }}
    QFrame#Banner {{ background: {c['accent_soft']}; border: 1px solid {c['accent_soft']}; border-radius: 10px; }}
    {banner_tones}
    QFrame#Banner QLabel {{ background: transparent; }}
    QLabel#Badge {{ border-radius: 8px; padding: 1px 8px; font-size: 8.5pt; font-weight: 600;
                    background: {c['card2']}; color: {c['muted']}; }}
    {badge_tones}
    QLabel#Badge[tone="accent"] {{ background: {c['accent_soft']}; color: {c['accent_text']}; }}
    QLabel#ErrorText {{ color: {c['bad']}; }}
    QFrame#Dock {{ background: {c['card']}; border-top: 1px solid {c['border']}; }}
    QFrame#Toast {{ background: {c['card']}; border: 1px solid {c['border']}; border-radius: 10px; }}
    QFrame#Toast[tone="good"] {{ border-left: 4px solid {c['good']}; }}
    QFrame#Toast[tone="warn"] {{ border-left: 4px solid {c['warn']}; }}
    QFrame#Toast[tone="bad"] {{ border-left: 4px solid {c['bad']}; }}
    QFrame#Toast[tone="info"] {{ border-left: 4px solid {c['info']}; }}
    QFrame#Toast QLabel {{ background: transparent; }}
    QScrollArea#Page, QScrollArea#Page > QWidget > QWidget#PageBody {{ background: transparent; border: none; }}
    """
