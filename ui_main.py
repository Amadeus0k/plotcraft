#!/usr/bin/env python3
"""
plotcraft GUI — live YAML config editor with a matplotlib preview.

Usage:
    python ui_main.py [config.yaml]
"""

import sys

from PyQt6.QtWidgets import QApplication

from ui.document import Document
from ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    window = MainWindow()

    if len(sys.argv) > 1:
        try:
            window._load_document(Document.open(sys.argv[1]))
        except Exception as exc:
            print(f"[error] could not open {sys.argv[1]}: {exc}", file=sys.stderr)

    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
