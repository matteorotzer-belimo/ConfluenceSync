# PyInstaller spec for ConfluenceSync.exe (one file, windowed).
# Build from the repository root:  pyinstaller packaging/ConfluenceSync.spec --noconfirm
from pathlib import Path
import re

from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo,
    StringFileInfo,
    StringStruct,
    StringTable,
    VarFileInfo,
    VarStruct,
    VSVersionInfo,
)

ROOT = Path(SPECPATH).parent  # noqa: F821 - provided by PyInstaller

VERSION = re.search(
    r'__version__\s*=\s*"([^"]+)"', (ROOT / "confluencesync" / "__init__.py").read_text(encoding="utf-8")
).group(1)
_nums = tuple(int(n) for n in re.findall(r"\d+", VERSION)[:3]) + (0,)
_nums = (_nums + (0, 0, 0, 0))[:4]
VERSION_INFO = VSVersionInfo(
    ffi=FixedFileInfo(filevers=_nums, prodvers=_nums),
    kids=[
        StringFileInfo([
            StringTable("040704B0", [
                StringStruct("CompanyName", "ConfluenceSync"),
                StringStruct("FileDescription", "ConfluenceSync – Notizen nach Confluence"),
                StringStruct("FileVersion", VERSION),
                StringStruct("ProductName", "ConfluenceSync"),
                StringStruct("ProductVersion", VERSION),
                StringStruct("OriginalFilename", "ConfluenceSync.exe"),
            ])
        ]),
        VarFileInfo([VarStruct("Translation", [0x0407, 1200])]),
    ],
)

a = Analysis(  # noqa: F821
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT)],
    datas=[],
    hiddenimports=[
        "keyring.backends.Windows",
        "msal_extensions",
    ],
    excludes=[
        "tkinter",
        "PySide6.QtNetwork",
        "PySide6.QtQml",
        "PySide6.QtQuick",
        "PySide6.QtPdf",
        "PySide6.QtWebEngineCore",
        "PySide6.QtMultimedia",
        "PySide6.Qt3DCore",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="ConfluenceSync",
    icon=str(ROOT / "packaging" / "ConfluenceSync.ico"),
    version=VERSION_INFO,
    console=False,
    upx=False,
    debug=False,
    strip=False,
)
