"""Persistent app preferences (QSettings-backed, survives across sessions).

Kept deliberately small: a couple of module-level get/set functions rather
than a class, since there's no per-instance state — QSettings itself is the
store. Add new preferences here as plain (get, set, DEFAULT) triples.
"""

from PyQt6.QtCore import QSettings

ORG = "plotcraft"
APP = "plotcraft"

DEFAULT_WHEEL_ZOOM_STEP_PCT = 5.0
DEFAULT_NUMERIC_WHEEL_STEP = 0.1


def _settings():
    return QSettings(ORG, APP)


def wheel_zoom_step_pct():
    return float(_settings().value("preview/wheel_zoom_step_pct", DEFAULT_WHEEL_ZOOM_STEP_PCT))


def set_wheel_zoom_step_pct(value):
    _settings().setValue("preview/wheel_zoom_step_pct", float(value))


def numeric_wheel_step():
    return float(_settings().value("inspector/numeric_wheel_step", DEFAULT_NUMERIC_WHEEL_STEP))


def set_numeric_wheel_step(value):
    _settings().setValue("inspector/numeric_wheel_step", float(value))
