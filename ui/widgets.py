"""Reusable field widgets bound to a schema.FieldSpec.

Every widget exposes get()/set() around a single convention: OMIT means
"this key should not be written to the document at all" (see schema.py's
docstring and CONFIG.md — plotter.py gives real meaning to a key being
*absent*, e.g. no `color` means auto-assign from the palette, so a naive
form that always writes a default value would silently change the render).
"""

import os

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QDoubleSpinBox, QFileDialog,
    QHBoxLayout, QLineEdit, QPushButton, QSpinBox, QWidget,
)

from . import schema, settings

OMIT = object()

_BIG = 1.0e9


def _numeric_step():
    return settings.numeric_wheel_step()


def _swatch_icon(color):
    pix = QPixmap(14, 14)
    pix.fill(QColor(color))
    return QIcon(pix)


class StrField(QLineEdit):
    changed = pyqtSignal()

    def __init__(self, spec, parent=None):
        super().__init__(parent)
        self.spec = spec
        if spec.tooltip:
            self.setToolTip(spec.tooltip)
        self.textChanged.connect(lambda _: self.changed.emit())

    def get(self):
        text = self.text()
        if self.spec.omit_if_empty and text == "":
            return OMIT
        return text

    def set(self, value):
        self.blockSignals(True)
        if value is OMIT:
            self.setText(str(self.spec.default) if self.spec.default else "")
        else:
            self.setText(str(value))
        self.blockSignals(False)


class ColumnChoiceField(QComboBox):
    """Dropdown of column names discovered from the series' data file
    (populated externally via set_columns — this widget has no way to
    resolve a data path on its own). Editable, so a column that hasn't been
    discovered yet (file not found, not yet saved, wrong format) can still
    be typed — errors surface via the preview's own error banner at render
    time, same as before this existed."""

    changed = pyqtSignal()

    def __init__(self, spec, parent=None):
        super().__init__(parent)
        self.spec = spec
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        if spec.tooltip:
            self.setToolTip(spec.tooltip)
        self.activated.connect(lambda _: self.changed.emit())
        self.lineEdit().editingFinished.connect(self.changed.emit)

    def set_columns(self, columns):
        current = self.currentText()
        self.blockSignals(True)
        self.clear()
        self.addItems(columns)
        if current and current not in columns:
            self.addItem(current)
        self.setCurrentText(current)
        self.blockSignals(False)

    def get(self):
        return self.currentText()

    def set(self, value):
        self.blockSignals(True)
        self.setCurrentText("" if value is OMIT else str(value))
        self.blockSignals(False)


class FilePathField(QWidget):
    """Text field + Browse... button for a path under data/. The dialog
    opens rooted at the data directory and the picked absolute path is
    converted back to data-dir-relative — plotter.py always resolves `file`
    that way (os.path.join(DATA_DIR, rel_path)), so this must never write
    an absolute path. Needs a data-dir getter injected after construction
    (see set_data_dir_getter) since a schema.FieldSpec alone doesn't carry
    the document it belongs to."""

    changed = pyqtSignal()

    def __init__(self, spec, parent=None):
        super().__init__(parent)
        self.spec = spec
        self._data_dir_getter = lambda: os.getcwd()
        self._edit = QLineEdit(self)
        self._browse = QPushButton("Browse…", self)
        if spec.tooltip:
            self.setToolTip(spec.tooltip)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._edit, 1)
        layout.addWidget(self._browse)
        self._edit.textChanged.connect(lambda _: self.changed.emit())
        self._browse.clicked.connect(self._on_browse)

    def set_data_dir_getter(self, getter):
        self._data_dir_getter = getter

    def _on_browse(self):
        data_dir = self._data_dir_getter()
        current = self._edit.text()
        candidate = os.path.join(data_dir, current) if current else data_dir
        start_dir = candidate if os.path.isdir(candidate) else (os.path.dirname(candidate) or data_dir)
        path, _ = QFileDialog.getOpenFileName(
            self, "Select data file", start_dir,
            "Data files (*.csv *.dat *.txt);;All files (*)")
        if not path:
            return
        try:
            rel = os.path.relpath(path, data_dir)
        except ValueError:
            rel = path  # different drive (Windows) — fall back to absolute
        self._edit.setText(rel)

    def get(self):
        return self._edit.text()

    def set(self, value):
        self._edit.blockSignals(True)
        self._edit.setText("" if value is OMIT else str(value))
        self._edit.blockSignals(False)


class FloatField(QDoubleSpinBox):
    changed = pyqtSignal()

    def __init__(self, spec, parent=None):
        super().__init__(parent)
        self.spec = spec
        self.setRange(-_BIG, _BIG)
        self.setDecimals(6)
        self.setSingleStep(_numeric_step())
        if spec.tooltip:
            self.setToolTip(spec.tooltip)
        self.valueChanged.connect(lambda _: self.changed.emit())

    def get(self):
        return self.value()

    def set(self, value):
        self.blockSignals(True)
        self.setValue(float(value) if value is not OMIT else float(self.spec.default or 0.0))
        self.blockSignals(False)


class IntField(QSpinBox):
    changed = pyqtSignal()

    def __init__(self, spec, parent=None):
        super().__init__(parent)
        self.spec = spec
        self.setRange(-2_000_000_000, 2_000_000_000)
        if spec.tooltip:
            self.setToolTip(spec.tooltip)
        self.valueChanged.connect(lambda _: self.changed.emit())

    def get(self):
        return self.value()

    def set(self, value):
        self.blockSignals(True)
        self.setValue(int(value) if value is not OMIT else int(self.spec.default or 0))
        self.blockSignals(False)


class BoolField(QCheckBox):
    changed = pyqtSignal()

    def __init__(self, spec, parent=None):
        super().__init__(parent)
        self.spec = spec
        if spec.tooltip:
            self.setToolTip(spec.tooltip)
        self.stateChanged.connect(lambda _: self.changed.emit())

    def get(self):
        return self.isChecked()

    def set(self, value):
        self.blockSignals(True)
        self.setChecked(bool(self.spec.default) if value is OMIT else bool(value))
        self.blockSignals(False)


class ChoiceField(QComboBox):
    changed = pyqtSignal()

    def __init__(self, spec, parent=None):
        super().__init__(parent)
        self.spec = spec
        self.addItems(list(spec.choices))
        if spec.tooltip:
            self.setToolTip(spec.tooltip)
        self.currentIndexChanged.connect(lambda _: self.changed.emit())

    def get(self):
        text = self.currentText()
        if text in self.spec.omit_choices:
            return OMIT
        return text

    def set(self, value):
        self.blockSignals(True)
        if value is OMIT:
            default = self.spec.default
            target = default if default in self.spec.choices else self.spec.choices[0]
            self.setCurrentText(target)
        else:
            self.setCurrentText(str(value))
        self.blockSignals(False)


class ColorField(QWidget):
    """Auto (palette-assigned) or a swatch picked from the palette / custom dialog."""

    changed = pyqtSignal()

    def __init__(self, spec, parent=None):
        super().__init__(parent)
        self.spec = spec
        self._combo = QComboBox(self)
        self._combo.addItem("Auto")
        for c in schema.PALETTE:
            self._combo.addItem(_swatch_icon(c), c, userData=c)
        self._combo.addItem("Custom…")
        if spec.tooltip:
            self.setToolTip(spec.tooltip)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._combo)
        self._combo.activated.connect(self._on_activated)
        self._custom_color = None

    def _on_activated(self, index):
        if self._combo.currentText() == "Custom…":
            initial = QColor(self._custom_color or "#000000")
            color = QColorDialog.getColor(initial, self, "Pick a color")
            if color.isValid():
                self._custom_color = color.name()
                self._set_custom_item(self._custom_color)
            else:
                self._combo.setCurrentIndex(0)
                self.changed.emit()
                return
        self.changed.emit()

    def _set_custom_item(self, hex_color):
        idx = self._combo.count() - 1
        self._combo.setItemText(idx, hex_color)
        self._combo.setItemIcon(idx, _swatch_icon(hex_color))
        self._combo.setItemData(idx, hex_color)
        self._combo.setCurrentIndex(idx)

    def get(self):
        idx = self._combo.currentIndex()
        if idx <= 0:
            return OMIT
        return self._combo.itemData(idx) or self._combo.currentText()

    def set(self, value):
        self._combo.blockSignals(True)
        if value is OMIT:
            self._combo.setCurrentIndex(0)
        else:
            match = self._combo.findData(value)
            if match >= 0:
                self._combo.setCurrentIndex(match)
            else:
                self._custom_color = value
                self._set_custom_item(value)
        self._combo.blockSignals(False)


class OptFloatField(QWidget):
    """Enable checkbox + spin box, for fields with no meaningful default
    (e.g. rotate: 0 is a real, different value from "not rotated")."""

    changed = pyqtSignal()

    def __init__(self, spec, parent=None):
        super().__init__(parent)
        self.spec = spec
        self._check = QCheckBox(self)
        self._spin = QDoubleSpinBox(self)
        self._spin.setRange(-_BIG, _BIG)
        self._spin.setDecimals(6)
        self._spin.setSingleStep(_numeric_step())
        self._spin.setEnabled(False)
        if spec.tooltip:
            self.setToolTip(spec.tooltip)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._check)
        layout.addWidget(self._spin, 1)
        self._check.toggled.connect(self._spin.setEnabled)
        self._check.toggled.connect(lambda _: self.changed.emit())
        self._spin.valueChanged.connect(lambda _: self.changed.emit())

    def get(self):
        if not self._check.isChecked():
            return OMIT
        return self._spin.value()

    def set(self, value):
        self.blockSignals(True)
        self._spin.blockSignals(True)
        self._check.blockSignals(True)
        if value is OMIT:
            self._check.setChecked(False)
            self._spin.setEnabled(False)
        else:
            self._check.setChecked(True)
            self._spin.setEnabled(True)
            self._spin.setValue(float(value))
        self._check.blockSignals(False)
        self._spin.blockSignals(False)
        self.blockSignals(False)


class PairField(QWidget):
    """Enable checkbox + [min, max] spin boxes — for xlim/ylim/ylim2, which
    autoscale (a fundamentally different behavior, not a fixed default) when
    absent."""

    changed = pyqtSignal()

    def __init__(self, spec, parent=None):
        super().__init__(parent)
        self.spec = spec
        self._check = QCheckBox(self)
        self._min = QDoubleSpinBox(self)
        self._max = QDoubleSpinBox(self)
        for sp in (self._min, self._max):
            sp.setRange(-_BIG, _BIG)
            sp.setDecimals(6)
            sp.setSingleStep(_numeric_step())
            sp.setEnabled(False)
        if spec.tooltip:
            self.setToolTip(spec.tooltip)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._check)
        layout.addWidget(self._min, 1)
        layout.addWidget(self._max, 1)
        self._check.toggled.connect(self._min.setEnabled)
        self._check.toggled.connect(self._max.setEnabled)
        self._check.toggled.connect(lambda _: self.changed.emit())
        self._min.valueChanged.connect(lambda _: self.changed.emit())
        self._max.valueChanged.connect(lambda _: self.changed.emit())

    def get(self):
        if not self._check.isChecked():
            return OMIT
        return [self._min.value(), self._max.value()]

    def set(self, value):
        self.blockSignals(True)
        for w in (self._check, self._min, self._max):
            w.blockSignals(True)
        if value is OMIT:
            self._check.setChecked(False)
            self._min.setEnabled(False)
            self._max.setEnabled(False)
        else:
            self._check.setChecked(True)
            self._min.setEnabled(True)
            self._max.setEnabled(True)
            self._min.setValue(float(value[0]))
            self._max.setValue(float(value[1]))
        for w in (self._check, self._min, self._max):
            w.blockSignals(False)
        self.blockSignals(False)


class TickField(QWidget):
    """Off / On (auto) / Custom(int) — for xtick_pi/xtick_sci and friends,
    whose YAML value is True | int, never a plain default."""

    changed = pyqtSignal()

    def __init__(self, spec, parent=None):
        super().__init__(parent)
        self.spec = spec
        self._combo = QComboBox(self)
        self._combo.addItems(["Off", "On (auto)", "Custom"])
        self._spin = QSpinBox(self)
        self._spin.setRange(1, 100)
        self._spin.setValue(4)
        self._spin.setVisible(False)
        if spec.tooltip:
            self.setToolTip(spec.tooltip)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._combo)
        layout.addWidget(self._spin, 1)
        self._combo.currentIndexChanged.connect(self._on_combo)
        self._spin.valueChanged.connect(lambda _: self.changed.emit())

    def _on_combo(self, index):
        self._spin.setVisible(index == 2)
        self.changed.emit()

    def get(self):
        idx = self._combo.currentIndex()
        if idx == 0:
            return OMIT
        if idx == 1:
            return True
        return self._spin.value()

    def set(self, value):
        self.blockSignals(True)
        self._combo.blockSignals(True)
        self._spin.blockSignals(True)
        if value is OMIT:
            self._combo.setCurrentIndex(0)
            self._spin.setVisible(False)
        elif value is True:
            self._combo.setCurrentIndex(1)
            self._spin.setVisible(False)
        else:
            self._combo.setCurrentIndex(2)
            self._spin.setValue(int(value))
            self._spin.setVisible(True)
        self._combo.blockSignals(False)
        self._spin.blockSignals(False)
        self.blockSignals(False)


_WIDGET_CLASSES = {
    schema.WIDGET_STR: StrField,
    schema.WIDGET_FLOAT: FloatField,
    schema.WIDGET_INT: IntField,
    schema.WIDGET_BOOL: BoolField,
    schema.WIDGET_CHOICE: ChoiceField,
    schema.WIDGET_COLOR: ColorField,
    schema.WIDGET_PAIR: PairField,
    schema.WIDGET_OPT_FLOAT: OptFloatField,
    schema.WIDGET_TICK: TickField,
}


def create_field_widget(spec, parent=None):
    cls = _WIDGET_CLASSES[spec.widget]
    return cls(spec, parent)
