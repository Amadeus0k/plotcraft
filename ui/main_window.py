import os
import traceback

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFileDialog, QMainWindow, QMessageBox, QSplitter, QStatusBar,
)

from .document import Document
from .export import export_document, output_dir_for
from .inspector import Inspector
from .preferences_dialog import PreferencesDialog
from .preview import PreviewCanvas, resolve_renderable
from .tree import DocumentTree


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("plotcraft")
        self.resize(1400, 900)

        self.doc = Document.new()
        self._current_selection = (None, None)
        self._preferences_dialog = None

        self.tree = DocumentTree()
        self.preview = PreviewCanvas()
        self.inspector = Inspector()

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.tree)
        splitter.addWidget(self.preview)
        splitter.addWidget(self.inspector)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([260, 800, 380])
        self.setCentralWidget(splitter)

        self.setStatusBar(QStatusBar())

        self._build_menu()
        self.tree.nodeSelected.connect(self._on_node_selected)
        self.tree.structureChanged.connect(self._on_structure_changed)
        self.inspector.changed.connect(self._on_field_changed)

        self._load_document(Document.new())

    # -- menu -------------------------------------------------------------

    def _add_action(self, menu, text, slot, shortcut=None):
        action = menu.addAction(text)
        action.triggered.connect(slot)
        if shortcut:
            action.setShortcut(shortcut)
        return action

    def _build_menu(self):
        menu = self.menuBar()
        file_menu = menu.addMenu("&File")
        self._add_action(file_menu, "&New", self.new_file, "Ctrl+N")
        self._add_action(file_menu, "&Open...", self.open_file, "Ctrl+O")
        file_menu.addSeparator()
        self._add_action(file_menu, "&Save", self.save_file, "Ctrl+S")
        self._add_action(file_menu, "Save &As...", self.save_file_as, "Ctrl+Shift+S")
        file_menu.addSeparator()
        self._add_action(file_menu, "Set &data directory...", self.set_data_dir)
        file_menu.addSeparator()
        self.act_export_selected = self._add_action(
            file_menu, "Export selected to SVG", self.export_selected)
        self._add_action(file_menu, "Export &all to SVG", self.export_all, "Ctrl+E")
        file_menu.addSeparator()
        self._add_action(file_menu, "E&xit", self.close)

        settings_menu = menu.addMenu("&Settings")
        self._add_action(settings_menu, "&Preferences...", self.open_preferences)

    def open_preferences(self):
        if self._preferences_dialog is None:
            dialog = PreferencesDialog(self)
            # Numeric spin-box steps are set at widget-creation time, so the
            # currently-open form needs a rebuild to pick up a live change;
            # the wheel-zoom step is read fresh on every notch by preview.py,
            # no rebuild needed for that one.
            dialog.preferencesChanged.connect(self.inspector._rebuild)
            dialog.finished.connect(self._on_preferences_closed)
            self._preferences_dialog = dialog
        self._preferences_dialog.show()
        self._preferences_dialog.raise_()
        self._preferences_dialog.activateWindow()

    def _on_preferences_closed(self):
        self._preferences_dialog = None

    # -- document lifecycle -------------------------------------------------

    def _load_document(self, doc):
        self.doc = doc
        self.tree.set_document(doc)
        self.preview.set_document(doc)
        self.inspector.clear_selection()
        self._current_selection = (None, None)
        self._update_title()

    def _confirm_discard_if_dirty(self):
        if not self.doc.dirty:
            return True
        result = QMessageBox.question(
            self, "Unsaved changes",
            "Discard unsaved changes?",
            QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
        )
        return result == QMessageBox.StandardButton.Discard

    def new_file(self):
        if not self._confirm_discard_if_dirty():
            return
        self._load_document(Document.new())

    def open_file(self):
        if not self._confirm_discard_if_dirty():
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Open config", "", "YAML files (*.yaml *.yml)")
        if not path:
            return
        try:
            doc = Document.open(path)
        except Exception as exc:
            QMessageBox.critical(self, "Could not open file", str(exc))
            return
        self._load_document(doc)

    def save_file(self):
        if self.doc.path is None:
            self.save_file_as()
            return
        self._do_save(self.doc.path)

    def save_file_as(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save config as", self.doc.path or "config.yaml",
            "YAML files (*.yaml *.yml)")
        if not path:
            return
        self._do_save(path)

    def _do_save(self, path):
        try:
            self.doc.save(path)
        except Exception as exc:
            QMessageBox.critical(self, "Could not save file", str(exc))
            return
        self._update_title()
        self.statusBar().showMessage(f"Saved {path}", 4000)

    def set_data_dir(self):
        start = self.doc.data_dir
        path = QFileDialog.getExistingDirectory(self, "Data directory", start)
        if not path:
            return
        self.doc.data_dir_override = path
        self._render_current()
        self.statusBar().showMessage(f"Data directory: {path}", 4000)

    def closeEvent(self, event):
        if self._confirm_discard_if_dirty():
            event.accept()
        else:
            event.ignore()

    def _update_title(self):
        name = os.path.basename(self.doc.path) if self.doc.path else "Untitled"
        star = "*" if self.doc.dirty else ""
        self.setWindowTitle(f"plotcraft — {name}{star}")

    # -- selection / editing / preview wiring --------------------------------

    def _on_node_selected(self, node_path, node_kind):
        self._current_selection = (node_path, node_kind)
        if node_path is None:
            self.inspector.clear_selection()
        else:
            self.inspector.show_node(self.doc, node_path, node_kind)
        self._render_current(immediate=True)
        renderable, _ = resolve_renderable(node_path, node_kind)
        self.act_export_selected.setEnabled(renderable is not None)

    def _on_field_changed(self):
        self._update_title()
        self._render_current(immediate=False)

    def _on_structure_changed(self):
        self._update_title()

    def _render_current(self, immediate=False):
        node_path, node_kind = self._current_selection
        if node_path is None:
            self.preview.clear()
            return
        if immediate:
            self.preview.render_now(node_path, node_kind)
        else:
            self.preview.request_render(node_path, node_kind)

    # -- export -------------------------------------------------------------

    def export_selected(self):
        node_path, node_kind = self._current_selection
        renderable, _ = resolve_renderable(node_path, node_kind)
        if renderable is None:
            return
        self._export(only_path=renderable)

    def export_all(self):
        self._export(only_path=None)

    def _export(self, only_path):
        try:
            out_dir = export_document(self.doc, only_path=only_path)
        except Exception:
            QMessageBox.critical(self, "Export failed", traceback.format_exc())
            return
        self.statusBar().showMessage(f"Exported to {out_dir}", 5000)
