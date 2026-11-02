"""Base class for the main views: scrollable page with a heading."""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QScrollArea, QVBoxLayout, QWidget

from .widgets import label

if TYPE_CHECKING:
    from .main_window import MainWindow


class Page(QWidget):
    title = ""
    subtitle = ""

    def __init__(self, win: "MainWindow", scroll: bool = True, max_width: int = 1180):
        super().__init__()
        self.win = win
        self.services = win.services
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        container = QWidget()
        container.setObjectName("scrollBody")
        center = QHBoxLayout(container)
        center.setContentsMargins(36, 26, 36, 36)
        inner = QWidget()
        inner.setMaximumWidth(max_width)
        center.addWidget(inner)
        self.body = QVBoxLayout(inner)
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(16)
        self.scroll_area = None
        if scroll:
            area = QScrollArea()
            self.scroll_area = area
            area.setWidgetResizable(True)
            area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            area.setWidget(container)
            outer.addWidget(area)
        else:
            outer.addWidget(container)
        head = QHBoxLayout()
        head.setSpacing(12)
        titles = QVBoxLayout()
        titles.setSpacing(4)
        self.title_label = label(self.title, "h1")
        self.subtitle_label = label(self.subtitle, "sub")
        titles.addWidget(self.title_label)
        titles.addWidget(self.subtitle_label)
        self.subtitle_label.setVisible(bool(self.subtitle))
        head.addLayout(titles, 1)
        self.actions = QHBoxLayout()
        self.actions.setSpacing(8)
        head.addLayout(self.actions)
        head.setAlignment(self.actions, Qt.AlignBottom)
        self.body.addLayout(head)

    def on_show(self, **kwargs) -> None:
        """Called every time the page becomes visible."""
