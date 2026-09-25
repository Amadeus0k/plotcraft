"""Schema-driven property inspector.

Builds a labelled form for whatever node is selected in the document tree.
Scalar keys come straight from schema.py's field tables; the four nested
dict structures (legend, zoom, smooth, fontsize) get dedicated section
builders below because their presence/absence is meaningfully tri-state
(see schema.py and widgets.py docstrings) in a way a flat field table can't
express on its own.
"""

import os
from functools import partial

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QGroupBox, QLabel, QScrollArea,
    QSizePolicy, QVBoxLayout, QWidget,
)

import plotter
from . import schema, widgets

KIND_FIELDS = {
    "project": schema.PROJECT_FIELDS,
    "plot":    schema.PLOT_FIELDS,
    "panel":   schema.PANEL_FIELDS,
    "figure":  schema.FIGURE_FIELDS,
    "series":  schema.SERIES_FIELDS,
}

FONTSIZE_DEFAULTS = {f.key: f.default for f in schema.FONTSIZE_FIELDS}
ZOOM_DEFAULTS = {f.key: f.default for f in schema.ZOOM_FIELDS if f.key != "loc"}
LEGEND_DEFAULTS = {"loc": "best"}
SMOOTH_SAVGOL_DEFAULTS = {"method": "savgol", **{f.key: f.default for f in schema.SMOOTH_SAVGOL_FIELDS}}
SMOOTH_SPLINE_DEFAULTS = {"method": "spline", **{f.key: f.default for f in schema.SMOOTH_SPLINE_FIELDS}}


def _discover_columns(doc, series_node):
    """Column names for a series' data file, or [] if it can't be read yet
    (no file set, file missing, unparseable) — never raises, the x/y
    dropdowns just fall back to free text in that case. Goes through
    plotter._load_dataframe, which is already cached by (path, mtime,
    format), so re-discovering on every keystroke in the file field is
    cheap after the first read."""
    file_rel = series_node.get("file")
    if not file_rel:
        return []
    full_path = os.path.join(doc.data_dir, file_rel)
    if not os.path.isfile(full_path):
        return []
    try:
        df = plotter._load_dataframe(full_path, series_node.get("format"))
    except Exception:
        return []
    return list(df.columns)


class Inspector(QScrollArea):
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self._container = QWidget()
        self._layout = QVBoxLayout(self._container)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.setWidget(self._container)

        self._doc = None
        self._node_path = None
        self._node_kind = None

        self._rebuild()

    def clear_selection(self):
        self._doc = None
        self._node_path = None
        self._node_kind = None
        self._rebuild()

    def show_node(self, doc, node_path, node_kind):
        self._doc = doc
        self._node_path = node_path
        self._node_kind = node_kind
        self._rebuild()

    # -- layout plumbing ------------------------------------------------

    def _clear_layout(self):
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _add_group(self, title, checkable=False):
        box = QGroupBox(title)
        box.setCheckable(checkable)
        form = QFormLayout()
        box.setLayout(form)
        self._layout.addWidget(box)
        return box, form

    def _commit(self, node_path, spec, widget):
        value = widget.get()
        if value is widgets.OMIT:
            self._doc.delete_key(node_path, spec.key)
        else:
            self._doc.set_key(node_path, spec.key, value)
        self.changed.emit()

    def _add_fields(self, node_path, node, fields, form):
        """Render every visible field except the ones with document-aware
        widgets (WIDGET_COLUMN, WIDGET_FILEPATH — see
        _add_series_data_section, the only place those appear). Returns the
        created widgets by key, so a caller can hook additional behavior
        onto a specific one."""
        created = {}
        for spec in schema.visible_fields(fields, node):
            if spec.widget in (schema.WIDGET_COLUMN, schema.WIDGET_FILEPATH):
                continue
            w = widgets.create_field_widget(spec)
            w.set(node[spec.key] if spec.key in node else widgets.OMIT)
            w.changed.connect(partial(self._commit, node_path, spec, w))
            form.addRow(spec.label, w)
            created[spec.key] = w
        return created

    def _add_series_data_section(self, node, form):
        """Series' "Data" section, fully custom-built (not through
        _add_fields) so file/x/y/format can be wired together in the right
        order: file uses a browse-button FilePathField (needs the
        document's data_dir to resolve picks back to a relative path); x/y
        are ColumnChoiceField dropdowns that need to refresh whenever file
        or format changes."""
        specs = {f.key: f for f in schema.SERIES_FIELDS if f.section == "Data"}

        file_spec = specs["file"]
        file_widget = widgets.FilePathField(file_spec)
        file_widget.set_data_dir_getter(lambda: self._doc.data_dir)
        file_widget.set(node[file_spec.key] if file_spec.key in node else widgets.OMIT)
        file_widget.changed.connect(partial(self._commit, self._node_path, file_spec, file_widget))
        form.addRow(file_spec.label, file_widget)

        column_widgets = {}
        for key in ("x", "y"):
            spec = specs[key]
            w = widgets.ColumnChoiceField(spec)
            w.set(node[spec.key] if spec.key in node else widgets.OMIT)
            w.changed.connect(partial(self._commit, self._node_path, spec, w))
            form.addRow(spec.label, w)
            column_widgets[key] = w

        format_spec = specs["format"]
        format_widget = widgets.create_field_widget(format_spec)
        format_widget.set(node[format_spec.key] if format_spec.key in node else widgets.OMIT)
        format_widget.changed.connect(
            partial(self._commit, self._node_path, format_spec, format_widget))
        form.addRow(format_spec.label, format_widget)

        def refresh_columns():
            columns = _discover_columns(self._doc, node)
            for w in column_widgets.values():
                w.set_columns(columns)

        refresh_columns()
        file_widget.changed.connect(refresh_columns)
        format_widget.changed.connect(refresh_columns)

    # -- main build -------------------------------------------------------

    def _rebuild(self):
        self._clear_layout()
        if self._doc is None:
            label = QLabel("Select an item in the tree to edit it.")
            label.setStyleSheet("color: gray; padding: 16px;")
            self._layout.addWidget(label)
            return

        node = self._doc.get(self._node_path)
        fields = KIND_FIELDS[self._node_kind]

        for section in schema.sections_in_order(schema.visible_fields(fields, node)):
            box, form = self._add_group(section)
            if self._node_kind == "series" and section == "Data":
                self._add_series_data_section(node, form)
            else:
                section_fields = [f for f in fields if f.section == section]
                self._add_fields(self._node_path, node, section_fields, form)

        if self._node_kind in ("plot", "panel"):
            self._add_fontsize_section(node)
            self._add_legend_section(node, figure_level=False)
            self._add_zoom_section(node)
        elif self._node_kind == "figure":
            self._add_fontsize_section(node)
            self._add_legend_section(node, figure_level=True)
        elif self._node_kind == "series":
            self._add_smooth_section(node)

    # -- fontsize: number | dict -------------------------------------------

    def _add_fontsize_section(self, node):
        box, form = self._add_group("Font size", checkable=True)
        has_value = "fontsize" in node
        box.setChecked(has_value)

        mode_row = QComboBox()
        mode_row.addItems(["Scalar (all text)", "Detailed"])
        is_dict = isinstance(node.get("fontsize"), dict)
        mode_row.setCurrentIndex(1 if is_dict else 0)
        form.addRow("Mode", mode_row)

        scalar_spin = widgets.FloatField(
            schema.FieldSpec("fontsize", "Base size", schema.WIDGET_FLOAT, default=10.0))
        detail_form_box = QWidget()
        detail_form = QFormLayout(detail_form_box)
        detail_form.setContentsMargins(0, 0, 0, 0)

        if not is_dict:
            scalar_spin.set(node.get("fontsize", widgets.OMIT))
        form.addRow(scalar_spin)
        form.addRow(detail_form_box)

        def refresh_visibility():
            detailed = mode_row.currentIndex() == 1
            scalar_spin.setVisible(not detailed)
            detail_form_box.setVisible(detailed)

        def rebuild_detail_form():
            while detail_form.count():
                item = detail_form.takeAt(0)
                w = item.widget()
                if w:
                    w.deleteLater()
            sub_node = node.get("fontsize", {})
            sub_node = sub_node if isinstance(sub_node, dict) else {}
            fs_path = self._node_path + ("fontsize",)
            self._add_fields(fs_path, sub_node, schema.FONTSIZE_FIELDS, detail_form)

        def on_toggle(checked):
            if checked:
                if mode_row.currentIndex() == 1:
                    self._doc.ensure_dict(self._node_path, "fontsize", FONTSIZE_DEFAULTS)
                else:
                    self._doc.set_key(self._node_path, "fontsize", scalar_spin.get())
            else:
                self._doc.delete_key(self._node_path, "fontsize")
            self.changed.emit()
            self._rebuild()

        def on_mode_change(index):
            if not box.isChecked():
                return
            if index == 1:
                self._doc.ensure_dict(self._node_path, "fontsize", FONTSIZE_DEFAULTS)
            else:
                self._doc.set_key(self._node_path, "fontsize", scalar_spin.get())
            self.changed.emit()
            self._rebuild()

        def on_scalar_change():
            if box.isChecked() and mode_row.currentIndex() == 0:
                self._doc.set_key(self._node_path, "fontsize", scalar_spin.get())
                self.changed.emit()

        box.toggled.connect(on_toggle)
        mode_row.currentIndexChanged.connect(on_mode_change)
        scalar_spin.changed.connect(on_scalar_change)

        refresh_visibility()
        mode_row.currentIndexChanged.connect(lambda _: refresh_visibility())
        if is_dict:
            rebuild_detail_form()

    # -- legend: absent (auto) | false | dict ------------------------------

    def _add_legend_section(self, node, figure_level):
        title = "Legend (shared across panels)" if figure_level else "Legend"
        box, form = self._add_group(title)

        mode_combo = QComboBox()
        mode_combo.addItems(["Auto", "None", "Custom"])
        value = node.get("legend", widgets.OMIT)
        if value is False:
            mode_combo.setCurrentIndex(1)
        elif isinstance(value, dict):
            mode_combo.setCurrentIndex(2)
        else:
            mode_combo.setCurrentIndex(0)
        form.addRow("Mode", mode_combo)
        if not figure_level:
            note = QLabel("Ignored if the parent figure sets its own legend.")
            note.setStyleSheet("color: gray;")
            form.addRow(note)

        detail_box = QWidget()
        detail_form = QFormLayout(detail_box)
        detail_form.setContentsMargins(0, 0, 0, 0)
        form.addRow(detail_box)

        split_check = QCheckBox("Split into color + line-style legends")
        split_detail_box = QWidget()
        split_form = QFormLayout(split_detail_box)
        split_form.setContentsMargins(0, 0, 0, 0)
        if figure_level:
            detail_form.addRow(split_check)
            detail_form.addRow(split_detail_box)

        def rebuild_detail():
            while detail_form.count():
                item = detail_form.takeAt(0)
                w = item.widget()
                if w and w not in (split_check, split_detail_box):
                    w.deleteLater()
            legend_node = node.get("legend", {})
            legend_node = legend_node if isinstance(legend_node, dict) else {}
            legend_path = self._node_path + ("legend",)
            self._add_fields(legend_path, legend_node, schema.LEGEND_FIELDS, detail_form)
            if figure_level:
                detail_form.addRow(split_check)
                detail_form.addRow(split_detail_box)
                split_check.blockSignals(True)
                split_check.setChecked(bool(legend_node.get("split")))
                split_check.blockSignals(False)
                rebuild_split_detail(legend_node)

        def rebuild_split_detail(legend_node):
            while split_form.count():
                item = split_form.takeAt(0)
                w = item.widget()
                if w:
                    w.deleteLater()
            if not split_check.isChecked():
                split_detail_box.setVisible(False)
                return
            split_detail_box.setVisible(True)
            legend_path = self._node_path + ("legend",)
            self._add_fields(legend_path, legend_node, schema.LEGEND_SPLIT_FIELDS, split_form)

        def on_split_toggle(checked):
            legend_path = self._node_path + ("legend",)
            self._doc.set_key(legend_path, "split", checked)
            self.changed.emit()
            legend_node = node.get("legend", {})
            rebuild_split_detail(legend_node if isinstance(legend_node, dict) else {})

        def on_mode_change(index):
            if index == 0:
                self._doc.delete_key(self._node_path, "legend")
            elif index == 1:
                self._doc.set_key(self._node_path, "legend", False)
            else:
                self._doc.ensure_dict(self._node_path, "legend", LEGEND_DEFAULTS)
            self.changed.emit()
            self._rebuild()

        mode_combo.currentIndexChanged.connect(on_mode_change)
        split_check.toggled.connect(on_split_toggle)

        detail_box.setVisible(mode_combo.currentIndex() == 2)
        if mode_combo.currentIndex() == 2:
            rebuild_detail()

    # -- zoom: absent | dict ------------------------------------------------

    def _add_zoom_section(self, node):
        box, form = self._add_group("Zoom inset", checkable=True)
        box.setChecked("zoom" in node)

        def rebuild():
            while form.count():
                item = form.takeAt(0)
                w = item.widget()
                if w:
                    w.deleteLater()
            zoom_node = node.get("zoom")
            if zoom_node is not None and not isinstance(zoom_node, dict):
                # Malformed input (zoom has no valid non-dict form) — replace
                # rather than crash on the first field edit below.
                zoom_node = dict(ZOOM_DEFAULTS)
                self._doc.set_key(self._node_path, "zoom", zoom_node)
            zoom_node = zoom_node if isinstance(zoom_node, dict) else {}
            zoom_path = self._node_path + ("zoom",)
            self._add_fields(zoom_path, zoom_node, schema.ZOOM_FIELDS, form)

        def on_toggle(checked):
            if checked:
                self._doc.ensure_dict(self._node_path, "zoom", ZOOM_DEFAULTS)
            else:
                self._doc.delete_key(self._node_path, "zoom")
            self.changed.emit()
            self._rebuild()

        box.toggled.connect(on_toggle)
        if box.isChecked():
            rebuild()

    # -- smooth (series only): absent | dict ---------------------------------

    def _add_smooth_section(self, node):
        box, form = self._add_group("Smoothing", checkable=True)
        current = node.get("smooth")
        has_value = current is not None
        box.setChecked(has_value)

        method_combo = QComboBox()
        method_combo.addItems(["Savitzky-Golay", "Spline"])
        if isinstance(current, dict) and current.get("method") == "spline":
            method_combo.setCurrentIndex(1)
        form.addRow("Method", method_combo)

        detail_box = QWidget()
        detail_form = QFormLayout(detail_box)
        detail_form.setContentsMargins(0, 0, 0, 0)
        form.addRow(detail_box)

        def rebuild_detail():
            while detail_form.count():
                item = detail_form.takeAt(0)
                w = item.widget()
                if w:
                    w.deleteLater()
            smooth_node = node.get("smooth")
            if smooth_node is not None and not isinstance(smooth_node, dict):
                # `smooth: 11` shorthand (bare int = savgol window) — normalize
                # to the equivalent full dict before the form can write into
                # it, or the first field edit would crash on `(11)["window"]`.
                smooth_node = dict(SMOOTH_SAVGOL_DEFAULTS, window=int(smooth_node))
                self._doc.set_key(self._node_path, "smooth", smooth_node)
            smooth_node = smooth_node if isinstance(smooth_node, dict) else {}
            smooth_path = self._node_path + ("smooth",)
            fields = (schema.SMOOTH_SPLINE_FIELDS if method_combo.currentIndex() == 1
                      else schema.SMOOTH_SAVGOL_FIELDS)
            self._add_fields(smooth_path, smooth_node, fields, detail_form)

        def on_method_change(index):
            if not box.isChecked():
                return
            defaults = SMOOTH_SPLINE_DEFAULTS if index == 1 else SMOOTH_SAVGOL_DEFAULTS
            self._doc.set_key(self._node_path, "smooth", dict(defaults))
            self.changed.emit()
            self._rebuild()

        def on_toggle(checked):
            if checked:
                defaults = (SMOOTH_SPLINE_DEFAULTS if method_combo.currentIndex() == 1
                            else SMOOTH_SAVGOL_DEFAULTS)
                self._doc.set_key(self._node_path, "smooth", dict(defaults))
            else:
                self._doc.delete_key(self._node_path, "smooth")
            self.changed.emit()
            self._rebuild()

        box.toggled.connect(on_toggle)
        method_combo.currentIndexChanged.connect(on_method_change)

        if box.isChecked():
            rebuild_detail()
