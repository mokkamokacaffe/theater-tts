"""Point d'entrée, très petit volontairement.

We load the local environment, create Qt, show one window, fini. If this file becomes
clever one day, somebody has probably built an usine à gaz by accident.
"""

from __future__ import annotations

import sys

from dotenv import load_dotenv
from PySide6.QtWidgets import QApplication

from app.gui.main_window import MainWindow


def main() -> int:
    load_dotenv()
    app = QApplication(sys.argv)
    app.setApplicationName("Theater TTS")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
