"""App logo, drawn with QPainter so no image plugin is needed."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap


def logo_pixmap(size: int = 64) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.Antialiasing)
    s = size / 64.0
    gradient = QLinearGradient(0, 0, size, size)
    gradient.setColorAt(0, QColor("#ff8a3d"))
    gradient.setColorAt(1, QColor("#d9480f"))
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(gradient))
    p.drawRoundedRect(QRectF(2 * s, 2 * s, 60 * s, 60 * s), 14 * s, 14 * s)

    # note sheet
    p.setBrush(QColor("#ffffff"))
    p.drawRoundedRect(QRectF(13 * s, 12 * s, 26 * s, 34 * s), 4 * s, 4 * s)
    pen = QPen(QColor("#f08c4a"), 2.6 * s, Qt.SolidLine, Qt.RoundCap)
    p.setPen(pen)
    for y in (21, 28, 35):
        p.drawLine(QPointF(18 * s, y * s), QPointF((34 if y != 35 else 28) * s, y * s))

    # arrow to the right
    pen = QPen(QColor("#ffffff"), 4.2 * s, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    path = QPainterPath(QPointF(30 * s, 52 * s))
    path.cubicTo(QPointF(40 * s, 52 * s), QPointF(46 * s, 46 * s), QPointF(50 * s, 36 * s))
    p.drawPath(path)
    p.drawLine(QPointF(50 * s, 36 * s), QPointF(43 * s, 39 * s))
    p.drawLine(QPointF(50 * s, 36 * s), QPointF(53 * s, 43 * s))
    p.end()
    return pixmap


def app_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(logo_pixmap(size))
    return icon
