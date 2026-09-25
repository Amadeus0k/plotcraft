"""Declarative field table for the plotcraft YAML schema (see CONFIG.md).

Every key plotter.py understands is described once here — label, widget
kind, default, choices, tooltip — so ui/inspector.py can build forms
generically instead of hand-wiring ~60 fields, and choice lists are pulled
from plotter.py itself rather than retyped, so they can't drift.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Sequence

import plotter

WIDGET_STR       = "str"
WIDGET_FLOAT     = "float"
WIDGET_INT       = "int"
WIDGET_BOOL      = "bool"
WIDGET_CHOICE    = "choice"
WIDGET_COLOR     = "color"
WIDGET_PAIR      = "pair"        # optional [min, max]
WIDGET_OPT_FLOAT = "opt_float"   # optional float, no meaningful default
WIDGET_TICK      = "tick"        # optional True | int
WIDGET_COLUMN    = "column"      # data-file column name — dropdown, populated
                                  # from the sibling `file` field; handled
                                  # specially by inspector.py, not the
                                  # generic per-spec widget factory
WIDGET_FILEPATH  = "filepath"    # path under data/ — text field + browse
                                  # button; also handled specially, since it
                                  # needs the document's data_dir to resolve
                                  # a picked absolute path back to relative


@dataclass(frozen=True)
class FieldSpec:
    key: str
    label: str
    widget: str
    default: Any = None
    choices: Optional[Sequence[str]] = None
    omit_choices: frozenset = field(default_factory=frozenset)
    tooltip: str = ""
    section: str = "General"
    omit_if_empty: bool = False
    show_if: Optional[Callable[[dict], bool]] = None


STANDARD_LOC = [
    "best", "upper right", "upper left", "lower left", "lower right",
    "right", "center left", "center right", "lower center", "upper center",
    "center",
]
LEGEND_LOC_CHOICES = STANDARD_LOC + list(plotter._OUTSIDE_LEGEND.keys())

LINESTYLE_CHOICES = ["-", "--", ":", "-."]
MARKER_CHOICES = [
    "None", "o", "s", "^", "v", "<", ">", "D", "d", "*", "x", "+",
    "p", "h", "H", "8", "1", "2", "3", "4",
]
FORMAT_CHOICES = ["auto", "csv", "dat"]
STYLE_CHOICES = ["line", "scatter"]
AXIS_CHOICES = ["left", "right"]
ZOOM_LOC_CHOICES = ["auto", "upper_right", "upper_left", "lower_left", "lower_right"]
SMOOTH_METHOD_CHOICES = ["savgol", "spline"]

PALETTE = list(plotter._PALETTE)


def _is_line(series_node):
    return series_node.get("style", "line") == "line"


def _is_scatter(series_node):
    return series_node.get("style", "line") == "scatter"


def _plot_fields(include_name_size):
    fields = []
    if include_name_size:
        fields += [
            FieldSpec("name", "Name", WIDGET_STR, default="figure", section="General",
                      tooltip="Output file stem."),
            FieldSpec("width", "Width (in)", WIDGET_FLOAT, default=3.5, section="Size",
                      tooltip="Figure width, inches."),
            FieldSpec("height", "Height (in)", WIDGET_FLOAT, default=2.8, section="Size",
                      tooltip="Figure height, inches."),
        ]
    fields += [
        FieldSpec("xlabel", "X label", WIDGET_STR, default="x", section="Axes"),
        FieldSpec("ylabel", "Y label", WIDGET_STR, default="y", section="Axes"),
        FieldSpec("ylabel2", "Y label (right)", WIDGET_STR, default="", section="Axes",
                  omit_if_empty=True,
                  tooltip="Only used if a series on this plot has axis: right."),
        FieldSpec("title", "Title", WIDGET_STR, section="Axes", omit_if_empty=True),
        FieldSpec("xlim", "X limits", WIDGET_PAIR, section="Limits",
                  tooltip="Autoscaled when disabled."),
        FieldSpec("ylim", "Y limits", WIDGET_PAIR, section="Limits"),
        FieldSpec("ylim2", "Y limits (right)", WIDGET_PAIR, section="Limits",
                  tooltip="Dual-axis plots only."),
        FieldSpec("grid", "Show grid", WIDGET_BOOL, default=True, section="Grid"),
        FieldSpec("xtick_pi", "X ticks as π", WIDGET_TICK, section="Ticks",
                  tooltip="On = every π/4; Custom sets the denominator."),
        FieldSpec("ytick_pi", "Y ticks as π", WIDGET_TICK, section="Ticks"),
        FieldSpec("ytick_pi2", "Y2 ticks as π", WIDGET_TICK, section="Ticks",
                  tooltip="Dual-axis plots only."),
        FieldSpec("xtick_sci", "X ticks scientific", WIDGET_TICK, section="Ticks",
                  tooltip="On = automatic mantissa precision; Custom sets decimal places."),
        FieldSpec("ytick_sci", "Y ticks scientific", WIDGET_TICK, section="Ticks"),
        FieldSpec("ytick_sci2", "Y2 ticks scientific", WIDGET_TICK, section="Ticks",
                  tooltip="Dual-axis plots only."),
    ]
    return fields


PLOT_FIELDS  = _plot_fields(include_name_size=True)
PANEL_FIELDS = _plot_fields(include_name_size=False)

FIGURE_FIELDS = [
    FieldSpec("name", "Name", WIDGET_STR, default="figure", section="General",
              tooltip="Output file stem."),
    FieldSpec("rows", "Rows", WIDGET_INT, default=1, section="Grid"),
    FieldSpec("cols", "Columns", WIDGET_INT, default=1, section="Grid"),
    FieldSpec("width", "Width (in)", WIDGET_FLOAT, default=7.0, section="Size"),
    FieldSpec("height", "Height (in)", WIDGET_FLOAT, default=5.6, section="Size"),
    FieldSpec("sharex", "Share X axis", WIDGET_BOOL, default=False, section="Grid"),
    FieldSpec("sharey", "Share Y axis", WIDGET_BOOL, default=False, section="Grid"),
]

SERIES_FIELDS = [
    FieldSpec("file", "Data file", WIDGET_FILEPATH, section="Data",
              tooltip="Path under data/, e.g. rdeturb/line.csv"),
    FieldSpec("x", "X column", WIDGET_COLUMN, section="Data",
              tooltip="Discovered from the data file above; type a name if it hasn't loaded yet."),
    FieldSpec("y", "Y column", WIDGET_COLUMN, section="Data",
              tooltip="Discovered from the data file above; type a name if it hasn't loaded yet."),
    FieldSpec("format", "File format", WIDGET_CHOICE, choices=FORMAT_CHOICES,
              default="auto", omit_choices=frozenset({"auto"}), section="Data"),
    FieldSpec("label", "Legend label", WIDGET_STR, default="", section="Style",
              omit_if_empty=True,
              tooltip="Series with no label are omitted from the legend."),
    FieldSpec("style", "Style", WIDGET_CHOICE, choices=STYLE_CHOICES,
              default="line", section="Style"),
    FieldSpec("axis", "Axis", WIDGET_CHOICE, choices=AXIS_CHOICES,
              default="left", section="Style"),
    FieldSpec("color", "Color", WIDGET_COLOR, section="Style",
              tooltip="Auto-assigned from the palette when disabled; same label "
                      "always gets the same color across a figure."),
    FieldSpec("linestyle", "Line style", WIDGET_CHOICE, choices=LINESTYLE_CHOICES,
              default="-", section="Style", show_if=_is_line),
    FieldSpec("linewidth", "Line width", WIDGET_FLOAT, default=1.2, section="Style",
              show_if=_is_line),
    FieldSpec("marker", "Marker", WIDGET_CHOICE, choices=MARKER_CHOICES,
              default="None", omit_choices=frozenset({"None"}), section="Style",
              show_if=_is_line),
    FieldSpec("markersize", "Marker size", WIDGET_FLOAT, default=16, section="Style",
              show_if=_is_scatter),
    FieldSpec("rotate", "Rotate (rad)", WIDGET_OPT_FLOAT, section="Transform",
              tooltip="Rotates (x, y) about the origin; wraps x to [-pi, pi]."),
    FieldSpec("group", "Split-legend group", WIDGET_STR, section="Split legend",
              omit_if_empty=True,
              tooltip="Defaults to the label text before ' - '."),
    FieldSpec("variant", "Split-legend variant", WIDGET_STR, section="Split legend",
              omit_if_empty=True,
              tooltip="Defaults to the label text after ' - '."),
]

LEGEND_FIELDS = [
    FieldSpec("loc", "Location", WIDGET_CHOICE, choices=LEGEND_LOC_CHOICES, default="best"),
    FieldSpec("ncol", "Columns", WIDGET_INT, default=1),
    FieldSpec("title", "Title", WIDGET_STR, omit_if_empty=True),
]

LEGEND_SPLIT_FIELDS = [
    FieldSpec("color_title", "Color legend title", WIDGET_STR, default="Color"),
    FieldSpec("style_title", "Style legend title", WIDGET_STR, default="Line style"),
    FieldSpec("color_ncol", "Color legend columns", WIDGET_INT, default=1),
    FieldSpec("style_ncol", "Style legend columns", WIDGET_INT, default=1),
    FieldSpec("gap", "Fixed-corner gap", WIDGET_FLOAT, default=0.12,
              tooltip="Only used when loc has no free centerline to split along."),
]

ZOOM_FIELDS = [
    FieldSpec("xmin", "X min", WIDGET_FLOAT, default=0.0),
    FieldSpec("xmax", "X max", WIDGET_FLOAT, default=1.0),
    FieldSpec("ymin", "Y min", WIDGET_FLOAT, default=0.0),
    FieldSpec("ymax", "Y max", WIDGET_FLOAT, default=1.0),
    FieldSpec("scale", "Scale", WIDGET_STR, default="x1", tooltip='e.g. "x2" or 2'),
    FieldSpec("width", "Width (%)", WIDGET_FLOAT, default=35),
    FieldSpec("height", "Height (%)", WIDGET_FLOAT, default=35),
    FieldSpec("loc", "Location", WIDGET_CHOICE, choices=ZOOM_LOC_CHOICES,
              default="auto", omit_choices=frozenset({"auto"})),
]

SMOOTH_SAVGOL_FIELDS = [
    FieldSpec("window", "Window", WIDGET_INT, default=11),
    FieldSpec("polyorder", "Poly order", WIDGET_INT, default=3),
    FieldSpec("resample", "Resample points", WIDGET_INT, default=500),
]
SMOOTH_SPLINE_FIELDS = [
    FieldSpec("factor", "Smoothing factor", WIDGET_FLOAT, default=0.5),
    FieldSpec("resample", "Resample points", WIDGET_INT, default=500),
]

FONTSIZE_FIELDS = [
    FieldSpec("base", "Base size", WIDGET_FLOAT, default=10.0),
    FieldSpec("label", "Axis label size", WIDGET_FLOAT, default=10.0),
    FieldSpec("title", "Title size", WIDGET_FLOAT, default=10.0),
    FieldSpec("tick", "Tick label size", WIDGET_FLOAT, default=9.0),
    FieldSpec("legend", "Legend text size", WIDGET_FLOAT, default=9.0),
]

PROJECT_FIELDS = [
    FieldSpec("project", "Project", WIDGET_STR, default="default",
              tooltip="Output subfolder: output/<project>/"),
    FieldSpec("latex", "Use LaTeX rendering", WIDGET_BOOL, default=False,
              tooltip="Falls back to mathtext with a warning if LaTeX isn't installed."),
]


def visible_fields(fields, node):
    return [f for f in fields if f.show_if is None or f.show_if(node)]


def sections_in_order(fields):
    seen = []
    for f in fields:
        if f.section not in seen:
            seen.append(f.section)
    return seen
