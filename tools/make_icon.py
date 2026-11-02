"""Developer tool: render the app logo into packaging/ConfluenceSync.ico (used by PyInstaller).

    python tools/make_icon.py
"""
from __future__ import annotations

import io
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SIZES = (16, 24, 32, 48, 64, 128, 256)


def main() -> int:
    from PySide6.QtCore import QBuffer, QIODevice
    from PySide6.QtGui import QGuiApplication

    from confluencesync.ui.logo import logo_pixmap

    app = QGuiApplication(sys.argv[:1])  # noqa: F841 - needed for QPixmap
    images = []
    for size in SIZES:
        buffer = QBuffer()
        buffer.open(QIODevice.WriteOnly)
        logo_pixmap(size).save(buffer, "PNG")
        images.append((size, bytes(buffer.data())))

    # ICO container with PNG-compressed entries (supported since Windows Vista)
    out = io.BytesIO()
    out.write(struct.pack("<HHH", 0, 1, len(images)))
    offset = 6 + 16 * len(images)
    for size, data in images:
        dim = 0 if size >= 256 else size
        out.write(struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset))
        offset += len(data)
    for _, data in images:
        out.write(data)
    target = ROOT / "packaging" / "ConfluenceSync.ico"
    target.parent.mkdir(exist_ok=True)
    target.write_bytes(out.getvalue())
    print("saved", target)
    return 0


if __name__ == "__main__":
    sys.exit(main())
