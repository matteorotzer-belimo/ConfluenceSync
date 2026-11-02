"""Look and feel: colours and one Qt stylesheet for the whole app."""
from __future__ import annotations

ACCENT = "#e8590c"
INK = "#1d2433"
INK_2 = "#4a5468"
INK_3 = "#7a8396"
LINE = "#e3e6ec"
BG = "#f6f7f9"

STATUS_STYLES = {  # status: (background, text)
    "synced": ("#e7f6ec", "#15803d"),
    "source_changed": ("#eaf1ff", "#2563eb"),
    "confluence_changed": ("#fff6e0", "#b45309"),
    "review": ("#fdecec", "#c62828"),
    "error": ("#fdecec", "#c62828"),
    "new": ("#f1ebff", "#6d28d9"),
    "source_missing": ("#eef0f4", "#4a5468"),
    "page_missing": ("#eef0f4", "#4a5468"),
    "unknown": ("#eef0f4", "#4a5468"),
}
NOTE_STYLES = {  # kind: (background, border, icon)
    "info": ("#eaf1ff", "#c9dafc", "ℹ️"),
    "ok": ("#e7f6ec", "#bfe5cc", "✅"),
    "warn": ("#fff6e0", "#f3dca5", "⚠️"),
    "err": ("#fdecec", "#f3c4c4", "⛔"),
    "accent": ("#fff1e8", "#f8d3bd", "💡"),
}

QSS = f"""
QWidget {{ font-family: "Segoe UI"; font-size: 10pt; color: {INK}; }}
QMainWindow, QWidget#content, QScrollArea, QWidget#scrollBody {{ background: {BG}; }}
QScrollArea {{ border: none; }}

QFrame#sidebar {{ background: #161b26; }}
QFrame#sidebar QLabel {{ color: #c5cad6; }}
QLabel#brandName {{ color: #ffffff; font-size: 12.5pt; font-weight: 700; }}
QLabel#brandSub {{ color: #8b93a7; font-size: 8.5pt; }}
QPushButton#nav {{ text-align: left; padding: 9px 14px; border: none; border-radius: 8px; color: #c5cad6;
    background: transparent; font-size: 10.5pt; }}
QPushButton#nav:hover {{ background: #222938; color: #ffffff; }}
QPushButton#nav:checked {{ background: #2a3245; color: #ffffff; border-left: 3px solid #ff7a1a; }}
QLabel#sideFoot {{ color: #8b93a7; font-size: 9pt; }}

QLabel#h1 {{ font-size: 19pt; font-weight: 700; }}
QLabel#h2 {{ font-size: 13.5pt; font-weight: 700; }}
QLabel#h3 {{ font-size: 11pt; font-weight: 700; }}
QLabel#sub {{ color: {INK_3}; font-size: 10.5pt; }}
QLabel#muted {{ color: {INK_3}; }}
QLabel#lead {{ color: {INK_2}; font-size: 11pt; }}

QFrame#card {{ background: #ffffff; border: 1px solid {LINE}; border-radius: 12px; }}
QFrame#tile {{ background: #fcfcfd; border: 1px solid {LINE}; border-radius: 12px; }}
QFrame#itBox {{ background: #ffffff; border: 1px dashed #c8cdd6; border-radius: 10px; }}

QLineEdit, QComboBox, QPlainTextEdit {{ border: 1px solid #cfd4dd; border-radius: 8px; padding: 7px 10px;
    background: #ffffff; selection-background-color: #fbd5bf; selection-color: {INK}; }}
QLineEdit:focus, QComboBox:focus {{ border: 2px solid {ACCENT}; padding: 6px 9px; }}
QComboBox::drop-down {{ border: none; width: 26px; }}
QComboBox QAbstractItemView {{ border: 1px solid {LINE}; selection-background-color: #fff1e8; selection-color: {INK}; }}

QPushButton {{ border: 1px solid #cfd4dd; background: #ffffff; border-radius: 8px; padding: 8px 16px; font-weight: 600; }}
QPushButton:hover {{ background: #f4f5f8; }}
QPushButton:disabled {{ color: #a3a9b6; background: #f7f8fa; }}
QPushButton#primary {{ background: {ACCENT}; border-color: {ACCENT}; color: #ffffff; }}
QPushButton#primary:hover {{ background: #d24f09; }}
QPushButton#primary:disabled {{ background: #f2b48f; border-color: #f2b48f; color: #ffffff; }}
QPushButton#danger {{ color: #c62828; border-color: #f0c2c2; }}
QPushButton#danger:hover {{ background: #fdecec; }}
QPushButton#ghost {{ border-color: transparent; background: transparent; color: {INK_2}; }}
QPushButton#ghost:hover {{ background: #eef0f4; }}
QPushButton#link {{ border: none; background: transparent; color: #2563eb; padding: 2px 0; text-decoration: underline; font-weight: 400; }}
QPushButton#choice {{ text-align: left; padding: 14px 16px; border: 2px solid {LINE}; border-radius: 12px; }}
QPushButton#choice:checked {{ border-color: {ACCENT}; background: #fff1e8; }}
QPushButton#step {{ text-align: left; border: none; background: transparent; padding: 9px 12px; border-radius: 10px;
    color: {INK_3}; font-weight: 600; }}
QPushButton#step:checked {{ background: #ffffff; color: {INK}; border: 1px solid {LINE}; }}

QToolButton#helpToggle {{ border: none; background: transparent; color: {INK_2}; font-weight: 600; padding: 4px 0; }}

QTabWidget::pane {{ border: none; }}
QTabBar::tab {{ background: transparent; padding: 9px 16px; font-weight: 600; color: {INK_3}; border-bottom: 3px solid transparent; }}
QTabBar::tab:selected {{ color: {INK}; border-bottom: 3px solid {ACCENT}; }}

QTreeWidget, QTableWidget, QListWidget {{ background: #ffffff; border: 1px solid {LINE}; border-radius: 10px;
    alternate-background-color: #fafbfc; outline: 0; }}
QTreeWidget::item, QListWidget::item {{ padding: 6px 4px; }}
QTreeWidget::item:selected, QTableWidget::item:selected, QListWidget::item:selected {{ background: #fff1e8; color: {INK}; }}
QTreeWidget::item:hover, QListWidget::item:hover {{ background: #f4f5f8; }}
QTableWidget {{ gridline-color: #eef0f4; }}
QTableWidget::item {{ padding: 8px; }}
QHeaderView::section {{ background: #ffffff; border: none; border-bottom: 1px solid {LINE}; padding: 8px;
    color: {INK_3}; font-weight: 600; font-size: 9pt; }}

QTextBrowser {{ background: #ffffff; border: 1px solid {LINE}; border-radius: 12px; padding: 20px 26px; }}
QProgressBar {{ border: none; background: #e8ebf0; border-radius: 3px; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 3px; }}
QCheckBox {{ spacing: 8px; }}
QToolTip {{ background: #1d2433; color: #ffffff; border: none; padding: 6px; }}
QFrame#banner {{ border-bottom: 1px solid {LINE}; }}
"""
