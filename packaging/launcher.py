"""Entry point for the PyInstaller build (absolute import, so the package is bundled normally)."""
import sys

from confluencesync.app import main

if __name__ == "__main__":
    sys.exit(main())
