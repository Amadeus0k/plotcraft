"""Preferences dialog — currently just the two wheel-tuning knobs. Add new
preference groups here as their own QGroupBox as the settings list grows.

Non-modal: values apply live as you change them (so you can see the effect
— e.g. scroll a numeric field in the inspector behind it — without closing
the dialog first). OK just closes it; Cancel reverts to whatever was set
before the dialog was opened.
"""

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QGroupBox,
    QVBoxLayout,
)

from . import settings


class PreferencesDialog(QDialog):
    preferencesChanged = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.setModal(False)

        self._original_wheel_zoom_step = settings.wheel_zoom_step_pct()
        self._original_numeric_step = settings.numeric_wheel_step()

        preview_box = QGroupBox("Preview")
        preview_form = QFormLayout(preview_box)

        self._wheel_zoom_step = QDoubleSpinBox()
        self._wheel_zoom_step.setRange(0.5, 50.0)
        self._wheel_zoom_step.setSingleStep(0.5)
        self._wheel_zoom_step.setSuffix(" %")
        self._wheel_zoom_step.setValue(self._original_wheel_zoom_step)
        self._wheel_zoom_step.valueChanged.connect(self._apply)
        preview_form.addRow("Wheel zoom step", self._wheel_zoom_step)

        inspector_box = QGroupBox("Property inspector")
        inspector_form = QFormLayout(inspector_box)

        self._numeric_wheel_step = QDoubleSpinBox()
        self._numeric_wheel_step.setRange(0.001, 100.0)
        self._numeric_wheel_step.setDecimals(3)
        self._numeric_wheel_step.setSingleStep(0.01)
        self._numeric_wheel_step.setValue(self._original_numeric_step)
        self._numeric_wheel_step.valueChanged.connect(self._apply)
        inspector_form.addRow("Numeric field wheel step", self._numeric_wheel_step)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(preview_box)
        layout.addWidget(inspector_box)
        layout.addWidget(buttons)

    def _apply(self):
        settings.set_wheel_zoom_step_pct(self._wheel_zoom_step.value())
        settings.set_numeric_wheel_step(self._numeric_wheel_step.value())
        self.preferencesChanged.emit()

    def reject(self):
        settings.set_wheel_zoom_step_pct(self._original_wheel_zoom_step)
        settings.set_numeric_wheel_step(self._original_numeric_step)
        self.preferencesChanged.emit()
        super().reject()
