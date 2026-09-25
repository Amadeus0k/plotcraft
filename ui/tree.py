"""Document tree: project -> plots[]/series[] and figures[]/panels[]/series[].

Add/remove/duplicate/reorder all funnel through ui.document's list helpers,
then the tree is rebuilt from the document and the previous selection is
restored by path where possible.
"""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView, QMenu, QToolBar, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)
from ruamel.yaml.comments import CommentedMap

ROLE_PATH = Qt.ItemDataRole.UserRole
ROLE_KIND = Qt.ItemDataRole.UserRole + 1

NEW_PLOT = lambda: CommentedMap({
    "name": "new_plot", "xlabel": "x", "ylabel": "y", "series": [],
})
NEW_PANEL = lambda: CommentedMap({"xlabel": "x", "ylabel": "y", "series": []})
NEW_FIGURE = lambda: CommentedMap({
    "name": "new_figure", "rows": 1, "cols": 1, "panels": [NEW_PANEL()],
})
NEW_SERIES = lambda: CommentedMap({"file": "", "x": "", "y": ""})


class DocumentTree(QWidget):
    nodeSelected = pyqtSignal(object, object)  # (node_path, node_kind) or (None, None)
    structureChanged = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._doc = None

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_context_menu)
        self.tree.itemSelectionChanged.connect(self._on_selection_changed)

        self.toolbar = QToolBar()
        self.act_add_plot = self.toolbar.addAction("+ Plot", self._add_plot)
        self.act_add_figure = self.toolbar.addAction("+ Figure", self._add_figure)
        self.toolbar.addSeparator()
        self.act_duplicate = self.toolbar.addAction("Duplicate", self._duplicate_selected)
        self.act_delete = self.toolbar.addAction("Delete", self._delete_selected)
        self.toolbar.addSeparator()
        self.act_up = self.toolbar.addAction("↑", self._move_up)
        self.act_down = self.toolbar.addAction("↓", self._move_down)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.toolbar)
        layout.addWidget(self.tree)

    # -- document plumbing ---------------------------------------------

    def set_document(self, doc):
        self._doc = doc
        self.refresh()

    def refresh(self, select_path=None):
        if select_path is None:
            select_path = self._current_path()
        self.tree.blockSignals(True)
        self.tree.clear()
        if self._doc is not None:
            self._build()
        self.tree.blockSignals(False)
        if select_path is not None:
            self._select_path(select_path)
        else:
            self._on_selection_changed()

    def _build(self):
        doc = self._doc.doc
        root = QTreeWidgetItem(["Project"])
        root.setData(0, ROLE_PATH, ())
        root.setData(0, ROLE_KIND, "project")
        self.tree.addTopLevelItem(root)

        plots_item = QTreeWidgetItem(["Plots"])
        plots_item.setData(0, ROLE_KIND, "category")
        root.addChild(plots_item)
        for i, plot in enumerate(doc.get("plots", [])):
            self._add_plot_item(plots_item, i, plot)

        figures_item = QTreeWidgetItem(["Figures"])
        figures_item.setData(0, ROLE_KIND, "category")
        root.addChild(figures_item)
        for i, fig in enumerate(doc.get("figures", [])):
            self._add_figure_item(figures_item, i, fig)

        root.setExpanded(True)
        plots_item.setExpanded(True)
        figures_item.setExpanded(True)

    def _add_plot_item(self, parent, index, plot):
        name = plot.get("name", f"plot {index}") if isinstance(plot, dict) else f"plot {index}"
        item = QTreeWidgetItem([name])
        item.setData(0, ROLE_PATH, ("plots", index))
        item.setData(0, ROLE_KIND, "plot")
        parent.addChild(item)
        series = plot.get("series", []) if isinstance(plot, dict) else []
        for j, s in enumerate(series):
            self._add_series_item(item, ("plots", index, "series"), j, s)
        item.setExpanded(True)

    def _add_series_item(self, parent, series_list_path, index, series):
        label = series.get("label") or series.get("file", f"series {index}") if isinstance(series, dict) else f"series {index}"
        item = QTreeWidgetItem([f"• {label}"])
        item.setData(0, ROLE_PATH, series_list_path + (index,))
        item.setData(0, ROLE_KIND, "series")
        parent.addChild(item)

    def _add_figure_item(self, parent, index, fig):
        name = fig.get("name", f"figure {index}") if isinstance(fig, dict) else f"figure {index}"
        item = QTreeWidgetItem([name])
        item.setData(0, ROLE_PATH, ("figures", index))
        item.setData(0, ROLE_KIND, "figure")
        parent.addChild(item)
        panels = fig.get("panels", []) if isinstance(fig, dict) else []
        for j, panel in enumerate(panels):
            self._add_panel_item(item, index, j, panel)
        item.setExpanded(True)

    def _add_panel_item(self, parent, fig_index, panel_index, panel):
        panel_path = ("figures", fig_index, "panels", panel_index)
        if panel is None:
            item = QTreeWidgetItem([f"(empty cell {panel_index})"])
            item.setData(0, ROLE_PATH, panel_path)
            item.setData(0, ROLE_KIND, "panel_empty")
            parent.addChild(item)
            return
        title = panel.get("title") or panel.get("ylabel") or f"panel {panel_index}"
        item = QTreeWidgetItem([title])
        item.setData(0, ROLE_PATH, panel_path)
        item.setData(0, ROLE_KIND, "panel")
        parent.addChild(item)
        series = panel.get("series", []) if isinstance(panel, dict) else []
        for k, s in enumerate(series):
            self._add_series_item(item, panel_path + ("series",), k, s)
        item.setExpanded(True)

    # -- selection --------------------------------------------------------

    def _current_item(self):
        items = self.tree.selectedItems()
        return items[0] if items else None

    def _current_path(self):
        item = self._current_item()
        return item.data(0, ROLE_PATH) if item else None

    def _current_kind(self):
        item = self._current_item()
        return item.data(0, ROLE_KIND) if item else None

    def _select_path(self, path):
        def walk(item):
            if item.data(0, ROLE_PATH) == path:
                return item
            for i in range(item.childCount()):
                found = walk(item.child(i))
                if found is not None:
                    return found
            return None

        for i in range(self.tree.topLevelItemCount()):
            found = walk(self.tree.topLevelItem(i))
            if found is not None:
                self.tree.setCurrentItem(found)
                return
        self._on_selection_changed()

    def _on_selection_changed(self):
        kind = self._current_kind()
        path = self._current_path()
        self._update_actions(kind)
        if kind in ("project", "plot", "panel", "figure", "series"):
            self.nodeSelected.emit(path, kind)
        else:
            self.nodeSelected.emit(None, None)

    def _update_actions(self, kind):
        self.act_duplicate.setEnabled(kind in ("plot", "figure", "series", "panel"))
        self.act_delete.setEnabled(kind in ("plot", "figure", "series", "panel"))
        self.act_up.setEnabled(kind in ("plot", "figure", "series", "panel"))
        self.act_down.setEnabled(kind in ("plot", "figure", "series", "panel"))

    # -- structural edits ---------------------------------------------------

    def _add_plot(self):
        idx = self._doc.add_list_item(("plots",), NEW_PLOT())
        self.structureChanged.emit()
        self.refresh(select_path=("plots", idx))

    def _add_figure(self):
        idx = self._doc.add_list_item(("figures",), NEW_FIGURE())
        self.structureChanged.emit()
        self.refresh(select_path=("figures", idx))

    def add_series(self, list_path):
        idx = self._doc.add_list_item(list_path, NEW_SERIES())
        self.structureChanged.emit()
        self.refresh(select_path=list_path + (idx,))

    def add_panel_here(self, panels_path, index):
        lst = self._doc.get(panels_path)
        lst[index] = NEW_PANEL()
        self._doc.dirty = True
        self.structureChanged.emit()
        self.refresh(select_path=panels_path + (index,))

    def _duplicate_selected(self):
        path, kind = self._current_path(), self._current_kind()
        if path is None or kind not in ("plot", "figure", "series", "panel"):
            return
        list_path, index = path[:-1], path[-1]
        new_index = self._doc.duplicate_list_item(list_path, index)
        self.structureChanged.emit()
        self.refresh(select_path=list_path + (new_index,))

    def _delete_selected(self):
        path, kind = self._current_path(), self._current_kind()
        if path is None or kind not in ("plot", "figure", "series", "panel", "panel_empty"):
            return
        list_path, index = path[:-1], path[-1]
        if kind == "panel_empty":
            return
        self._doc.remove_list_item(list_path, index)
        self.structureChanged.emit()
        self.refresh()

    def _move_up(self):
        self._move(-1)

    def _move_down(self):
        self._move(1)

    def _move(self, delta):
        path, kind = self._current_path(), self._current_kind()
        if path is None or kind not in ("plot", "figure", "series", "panel"):
            return
        list_path, index = path[:-1], path[-1]
        lst = self._doc.get(list_path)
        new_index = index + delta
        if not (0 <= new_index < len(lst)):
            return
        self._doc.move_list_item(list_path, index, new_index)
        self.structureChanged.emit()
        self.refresh(select_path=list_path + (new_index,))

    # -- context menu -------------------------------------------------------

    def _on_context_menu(self, pos):
        item = self.tree.itemAt(pos)
        if item is None:
            return
        kind = item.data(0, ROLE_KIND)
        path = item.data(0, ROLE_PATH)
        menu = QMenu(self)

        if kind in ("plot", "panel"):
            menu.addAction("Add series", lambda: self.add_series(path + ("series",)))
        if kind == "panel_empty":
            fig_path = path[:2]
            panels_path = fig_path + ("panels",)
            menu.addAction("Add panel here", lambda: self.add_panel_here(panels_path, path[-1]))
        if kind == "figure":
            menu.addAction("Add panel", lambda: self._add_panel_to_figure(path))
        if kind in ("plot", "figure", "series", "panel"):
            menu.addAction("Duplicate", self._duplicate_selected)
            menu.addAction("Delete", self._delete_selected)
            menu.addSeparator()
            menu.addAction("Move up", self._move_up)
            menu.addAction("Move down", self._move_down)

        if not menu.isEmpty():
            menu.exec(self.tree.viewport().mapToGlobal(pos))

    def _add_panel_to_figure(self, fig_path):
        fig = self._doc.get(fig_path)
        rows, cols = int(fig.get("rows", 1)), int(fig.get("cols", 1))
        capacity = rows * cols
        panels = fig.get("panels", [])
        if len(panels) >= capacity:
            return
        idx = self._doc.add_list_item(fig_path + ("panels",), NEW_PANEL())
        self.structureChanged.emit()
        self.refresh(select_path=fig_path + ("panels", idx))
