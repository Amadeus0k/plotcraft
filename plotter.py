#!/usr/bin/env python3
"""
plotter.py — Journal-quality SVG figure generator.

Usage:
    python plotter.py <config.yaml> [config2.yaml ...]

Each YAML config describes one project's worth of plots.
Data files are resolved under  data/<path>.
Output SVGs are written to     output/<project>/<name>.svg
"""

import argparse
import math
import os
import sys

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import FuncFormatter, MaxNLocator, MultipleLocator, ScalarFormatter
from mpl_toolkits.axes_grid1.inset_locator import inset_axes, mark_inset
from scipy.interpolate import interp1d, UnivariateSpline
from scipy.signal import savgol_filter
try:
    import yaml
except ImportError:
    sys.exit("PyYAML is required.  Install it with:  pip install pyyaml")

# ---------------------------------------------------------------------------
# Journal-quality defaults (single-column width = 3.5 in, double = 7.0 in)
# ---------------------------------------------------------------------------
matplotlib.rcParams.update({
    "font.family":        "serif",
    "font.serif":         ["Times New Roman", "DejaVu Serif"],
    "font.size":          10,
    "axes.labelsize":     10,
    "axes.titlesize":     10,
    "xtick.labelsize":    9,
    "ytick.labelsize":    9,
    "legend.fontsize":    9,
    "legend.framealpha":  0.9,
    "legend.edgecolor":   "0.7",
    "axes.linewidth":     0.8,
    "xtick.direction":    "in",
    "ytick.direction":    "in",
    "xtick.major.width":  0.8,
    "ytick.major.width":  0.8,
    "xtick.minor.visible": True,
    "ytick.minor.visible": True,
    "xtick.minor.width":  0.5,
    "ytick.minor.width":  0.5,
    "lines.linewidth":    1.2,
    "lines.markersize":   4,
    "grid.linewidth":     0.4,
    "grid.linestyle":     "--",
    "grid.alpha":         0.6,
    "savefig.bbox":       "tight",
    "savefig.pad_inches": 0.02,
})

DATA_DIR   = "data"
OUTPUT_DIR = "output"

# Okabe-Ito colorblind-safe palette, extended with additional publication-quality hues.
_PALETTE = [
    "#0072B2",  # blue
    "#D55E00",  # vermilion
    "#009E73",  # green
    "#CC79A7",  # mauve
    "#E69F00",  # amber
    "#56B4E9",  # sky blue
    "#F0027F",  # magenta
    "#7B4F9E",  # violet
    "#3CB464",  # emerald
    "#BF5B17",  # sienna
]


def _assign_colors(series_list):
    """Fill in missing colors from the palette, skipping any already used explicitly."""
    used  = {s["color"] for s in series_list if s.get("color")}
    pool  = [c for c in _PALETTE if c not in used]
    pool += [c for c in _PALETTE if c in used]   # cycle back if more series than palette
    idx   = 0
    for s in series_list:
        if not s.get("color"):
            s["color"] = pool[idx % len(pool)]
            idx += 1


def _assign_colors_panels(panels):
    """Assign colors consistently across all panels: same label always gets the same color."""
    label_color = {}

    # Respect explicit colors first (first explicit assignment for a label wins)
    for panel in panels:
        if not isinstance(panel, dict):
            continue
        for s in panel.get("series", []):
            if s.get("color") and s.get("label"):
                label_color.setdefault(s["label"], s["color"])

    used = set(label_color.values())
    pool = [c for c in _PALETTE if c not in used]
    pool += [c for c in _PALETTE if c in used]
    idx = 0

    for panel in panels:
        if not isinstance(panel, dict):
            continue
        for s in panel.get("series", []):
            if s.get("color"):
                continue
            label = s.get("label", "")
            if label in label_color:
                s["color"] = label_color[label]
            else:
                color = pool[idx % len(pool)]
                s["color"] = color
                if label:
                    label_color[label] = color
                idx += 1


def _fontsize_rcparams(fontsize_cfg):
    """Convert a fontsize config value to a matplotlib rcParams override dict.

    fontsize_cfg can be:
      int / float  — base size; ticks and legend are 1 pt smaller
      dict with any subset of:
        base   : float  — sets all elements; individual keys override it
        label  : float  — axes x/y label size
        title  : float  — axes title size
        tick   : float  — tick label size (x and y)
        legend : float  — legend text size

    Returns an empty dict (no-op) when fontsize_cfg is None/falsy.
    """
    if not fontsize_cfg:
        return {}

    if isinstance(fontsize_cfg, (int, float)):
        base = float(fontsize_cfg)
        return {
            "axes.labelsize":  base,
            "axes.titlesize":  base,
            "xtick.labelsize": base - 1,
            "ytick.labelsize": base - 1,
            "legend.fontsize": base - 1,
        }

    cfg = dict(fontsize_cfg)
    overrides = {}
    if "base" in cfg:
        base = float(cfg["base"])
        overrides.update({
            "axes.labelsize":  base,
            "axes.titlesize":  base,
            "xtick.labelsize": base - 1,
            "ytick.labelsize": base - 1,
            "legend.fontsize": base - 1,
        })
    if "label"  in cfg: overrides["axes.labelsize"]  = float(cfg["label"])
    if "title"  in cfg: overrides["axes.titlesize"]  = float(cfg["title"])
    if "tick"   in cfg:
        overrides["xtick.labelsize"] = float(cfg["tick"])
        overrides["ytick.labelsize"] = float(cfg["tick"])
    if "legend" in cfg: overrides["legend.fontsize"] = float(cfg["legend"])
    return overrides


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def rotate_arrays(theta, variable, rotation_angle):
    """Shift variable values to new angular positions, wrapping to [-pi, pi]."""
    theta    = np.asarray(theta,    dtype=float)
    variable = np.asarray(variable, dtype=float)
    theta_rotated = np.arctan2(
        np.sin(theta + rotation_angle),
        np.cos(theta + rotation_angle),
    )
    order = np.argsort(theta_rotated)
    return theta_rotated[order], variable[order]


def smooth_series(x, y, smooth_cfg):
    """Smooth and resample (x, y), returning a denser (x_out, y_out).

    smooth_cfg can be:
      - an int  → shorthand for savgol with that window size
      - a dict  → full control:

        method: savgol   (default) — Savitzky-Golay filter then cubic resample.
          window:    11   window length (forced odd)
          polyorder: 3
          resample:  500  output point count

        method: spline   — smoothing spline; does NOT pass through every point.
          factor:   0.5   0 = interpolating, 1 = very smooth
          resample: 500
    """
    cfg      = {"window": int(smooth_cfg)} if isinstance(smooth_cfg, int) else dict(smooth_cfg)
    method   = cfg.get("method", "savgol")
    resample = int(cfg.get("resample", 500))
    order    = np.argsort(x)
    x, y     = x[order], y[order]
    x_new    = np.linspace(x[0], x[-1], resample)

    if method == "spline":
        factor = float(cfg.get("factor", 0.5))
        unique_x, inv = np.unique(x, return_inverse=True)
        if len(unique_x) < len(x):
            unique_y = np.zeros_like(unique_x)
            np.add.at(unique_y, inv, y)
            counts = np.bincount(inv).astype(float)
            unique_y /= counts
            x, y = unique_x, unique_y
        spl    = UnivariateSpline(x, y, s=factor * len(y), k=3)
        return x_new, spl(x_new)

    # savgol: filter then cubic interpolate to resample points
    window    = int(cfg.get("window", 11))
    polyorder = int(cfg.get("polyorder", 3))
    window    = min(window, len(y))
    window    = window - 1 if window % 2 == 0 else window
    window    = max(window, polyorder + 1)
    y_sm      = savgol_filter(y, window_length=window, polyorder=polyorder)
    return x_new, interp1d(x, y_sm, kind="cubic")(x_new)


def _load_dataframe(full_path, fmt=None):
    """Load a data file into a DataFrame.

    fmt values
    ----------
    None  — auto-detect: 'dat' if the first non-empty line starts with '#', else 'csv'
    'csv' — comma-separated with a header row
    'dat' — whitespace-delimited; column names taken from the first '#'-prefixed line
    """
    if fmt is None:
        with open(full_path, "r") as fh:
            first = fh.readline()
        fmt = "dat" if first.strip().startswith("#") else "csv"

    if fmt == "dat":
        cols = None
        with open(full_path, "r") as fh:
            for line in fh:
                stripped = line.strip()
                if stripped.startswith("#"):
                    cols = stripped.lstrip("#").split()
                    break
        if cols is None:
            raise ValueError(f"No '#' header line found in dat file: {full_path}")
        return pd.read_csv(full_path, sep=r"\s+", comment="#",
                           header=None, names=cols, engine="python")

    return pd.read_csv(full_path)


def load_series(series_cfg):
    """Return (x, y) arrays for one series entry in a plot config."""
    rel_path  = series_cfg["file"]
    full_path = os.path.join(DATA_DIR, rel_path)
    if not os.path.exists(full_path):
        raise FileNotFoundError(f"Data file not found: {full_path}")

    df = _load_dataframe(full_path, series_cfg.get("format"))
    x  = df[series_cfg["x"]].to_numpy(dtype=float)
    y  = df[series_cfg["y"]].to_numpy(dtype=float)

    if "rotate" in series_cfg:
        x, y = rotate_arrays(x, y, float(series_cfg["rotate"]))

    if "smooth" in series_cfg:
        x, y = smooth_series(x, y, series_cfg["smooth"])

    return x, y


# ---------------------------------------------------------------------------
# Zoom inset helpers
# ---------------------------------------------------------------------------

def _parse_zoom_scale(val):
    """Parse 'x2', 'x5', 2, 5.0 → float."""
    if isinstance(val, (int, float)):
        return float(val)
    return float(str(val).strip().lstrip("xX"))


def _inset_loc_num(loc_str):
    """Convert a human-readable location string to a matplotlib loc integer."""
    if isinstance(loc_str, int):
        return loc_str
    mapping = {
        "upper right": 1, "upper_right": 1, "ur": 1,
        "upper left":  2, "upper_left":  2, "ul": 2,
        "lower left":  3, "lower_left":  3, "ll": 3,
        "lower right": 4, "lower_right": 4, "lr": 4,
    }
    key = str(loc_str).lower().strip()
    return mapping.get(key, int(key) if key.isdigit() else 1)


def _auto_inset_loc(ax, xy_pairs):
    """Return the matplotlib loc int (1–4) for the least-populated quadrant."""
    xlim, ylim = ax.get_xlim(), ax.get_ylim()
    mx = (xlim[0] + xlim[1]) / 2.0
    my = (ylim[0] + ylim[1]) / 2.0
    counts = np.zeros(4, dtype=float)
    for xs, ys in xy_pairs:
        xs = np.asarray(xs, dtype=float)
        ys = np.asarray(ys, dtype=float)
        mask = (xs >= xlim[0]) & (xs <= xlim[1]) & (ys >= ylim[0]) & (ys <= ylim[1])
        xf, yf = xs[mask], ys[mask]
        counts[0] += np.sum((xf >= mx) & (yf >= my))  # upper-right → loc 1
        counts[1] += np.sum((xf <  mx) & (yf >= my))  # upper-left  → loc 2
        counts[2] += np.sum((xf <  mx) & (yf <  my))  # lower-left  → loc 3
        counts[3] += np.sum((xf >= mx) & (yf <  my))  # lower-right → loc 4
    return [1, 2, 3, 4][int(np.argmin(counts))]


def _mark_corners(loc):
    """Select mark_inset corner pair that draws clean connecting lines."""
    return {1: (2, 4), 2: (1, 3), 3: (2, 4), 4: (1, 3)}.get(loc, (2, 4))


def _apply_pi_ticks(ax, which, den_cfg):
    """Format an axis' tick labels as multiples of pi (e.g. -pi, -pi/2, 0, pi/2, pi)
    instead of raw decimal numbers — for angle axes given in radians.

    which   : "x" or "y" — which axis to format.
    den_cfg : True → default denominator (4, i.e. ticks every pi/4), or an
              explicit int denominator (e.g. 2 → ticks every pi/2).
    """
    den  = 4 if den_cfg is True else int(den_cfg)
    step = math.pi / den
    axis = ax.xaxis if which == "x" else ax.yaxis
    axis.set_major_locator(MultipleLocator(step))

    def _fmt(val, _pos):
        n = int(round(val / step))
        if n == 0:
            return "0"
        g = math.gcd(abs(n), den)
        num, denom = n // g, den // g
        sign  = "-" if num < 0 else ""
        coeff = "" if abs(num) == 1 else str(abs(num))
        # $...$ math mode renders correctly whether or not full LaTeX (text.usetex) is on.
        body = f"{coeff}\\pi" if denom == 1 else f"{coeff}\\pi/{denom}"
        return f"${sign}{body}$"

    axis.set_major_formatter(FuncFormatter(_fmt))


def _apply_sci_ticks(ax, which, precision_cfg):
    """Format an axis in journal-standard scientific notation: tick labels show
    only the mantissa (e.g. 0.90, 0.95, 1.00) and the shared power of ten is
    printed once, as an offset label at the end of the axis (e.g. "x10^5") —
    matplotlib's standard scientific-notation convention, not per-tick 1.05x10^5.

    which         : "x" or "y" — which axis to format.
    precision_cfg : True → automatic mantissa precision, or an explicit int
                    giving a fixed number of mantissa decimal places.
    """
    axis = ax.xaxis if which == "x" else ax.yaxis

    class _SciFormatter(ScalarFormatter):
        def _set_format(self):
            super()._set_format()
            if precision_cfg is not True:
                self.format = f"%.{int(precision_cfg)}f"

    formatter = _SciFormatter(useMathText=True)
    formatter.set_scientific(True)
    formatter.set_powerlimits((0, 0))   # always use scientific notation
    axis.set_major_formatter(formatter)


def _style_twin_axis(ax, series_list, side):
    """Color the y-axis label/ticks to match the series color when exactly one
    series occupies this side of a dual-axis plot (standard journal convention)."""
    side_series = [s for s in series_list if s.get("axis", "left") == side]
    if len(side_series) == 1 and side_series[0].get("color"):
        color = side_series[0]["color"]
        ax.yaxis.label.set_color(color)
        ax.tick_params(axis="y", colors=color)


def _render_series(ax, s, x, y, show_label=True):
    """Render one series config on *ax*."""
    style     = s.get("style",     "line")
    label     = s.get("label",     "") if show_label else ""
    color     = s.get("color",     None)
    linestyle = s.get("linestyle", "-")
    linewidth = s.get("linewidth", None)
    marker    = s.get("marker",    None)

    if style == "scatter":
        ax.scatter(x, y, label=label, color=color,
                   edgecolors="k", s=s.get("markersize", 16), zorder=3)
    else:
        ax.plot(x, y, linestyle=linestyle, marker=marker,
                label=label, color=color, linewidth=linewidth, zorder=2)


def _add_zoom_inset(ax, zoom_cfg, series_data, show_grid):
    """Add a publication-quality zoom inset axes to *ax*.

    zoom_cfg keys
    -------------
    xmin, xmax, ymin, ymax : float  — region of interest (required).  The highlight
                             rectangle is always drawn around this region.
    scale                  : str/float — magnification factor, e.g. 'x3' (default 1).
                             scale=1 uses base width/height; scale=2 doubles the
                             inset panel size for better visibility, etc.
                             The inset always shows exactly the xmin–xmax, ymin–ymax
                             region; scale only controls how large the panel is.
    width                  : float — base inset width  as % of parent axes (default 35)
    height                 : float — base inset height as % of parent axes (default 35)
    loc                    : str/int — inset placement (auto-detected if omitted)
                             'upper_right'|'upper_left'|'lower_left'|'lower_right'
                             or 1|2|3|4
    """
    x1 = float(zoom_cfg["xmin"])
    x2 = float(zoom_cfg["xmax"])
    y1 = float(zoom_cfg["ymin"])
    y2 = float(zoom_cfg["ymax"])
    scale = _parse_zoom_scale(zoom_cfg.get("scale", 1))
    scale = max(scale, 1.0)

    base_w = float(zoom_cfg.get("width",  35))
    base_h = float(zoom_cfg.get("height", 35))
    w_pct = min(base_w * scale, 90)
    h_pct = min(base_h * scale, 90)

    xy_pairs = [(x, y) for _, x, y in series_data]
    loc = (_inset_loc_num(zoom_cfg["loc"])
           if "loc" in zoom_cfg
           else _auto_inset_loc(ax, xy_pairs))

    axins = inset_axes(ax,
                       width=f"{w_pct:.0f}%",
                       height=f"{h_pct:.0f}%",
                       loc=loc,
                       borderpad=0.8)

    for s, x, y in series_data:
        _render_series(axins, s, x, y, show_label=False)

    axins.set_xlim(x1, x2)
    axins.set_ylim(y1, y2)

    axins.xaxis.set_major_locator(MaxNLocator(nbins=4, prune="both"))
    axins.yaxis.set_major_locator(MaxNLocator(nbins=4, prune="both"))
    axins.tick_params(axis="both", which="major",
                      labelsize=7, direction="in", length=3, width=0.6)
    axins.tick_params(axis="both", which="minor",
                      length=1.5, width=0.4)

    # Flip tick labels to the inner sides so they don't overlap main axes labels.
    # loc: 1=upper-right  2=upper-left  3=lower-left  4=lower-right
    if loc in (3, 4):       # lower half → x labels on top edge (inner)
        axins.xaxis.tick_top()
    else:                   # upper half → x labels on bottom edge (inner)
        axins.xaxis.tick_bottom()
    if loc in (2, 3):       # left half  → y labels on right edge (inner)
        axins.yaxis.tick_right()
    else:                   # right half → y labels on left edge (inner)
        axins.yaxis.tick_left()

    if show_grid:
        axins.grid(True, linewidth=0.3, linestyle="--", alpha=0.5)

    lc1, lc2 = _mark_corners(loc)
    mark_inset(ax, axins, loc1=lc1, loc2=lc2,
               fc="none", ec="0.35", lw=0.8, zorder=5)


# ---------------------------------------------------------------------------
# Legend helper
# ---------------------------------------------------------------------------

# Maps "outside <position>" keywords to (bbox_to_anchor, loc) pairs.
# bbox_to_anchor is in axes-fraction coordinates; borderaxespad=0 avoids double-gap.
_OUTSIDE_LEGEND = {
    "outside right":         ((1.02, 1.0),  "upper left"),
    "outside upper right":   ((1.02, 1.0),  "upper left"),
    "outside center right":  ((1.02, 0.5),  "center left"),
    "outside lower right":   ((1.02, 0.0),  "lower left"),
    "outside left":          ((-0.02, 1.0), "upper right"),
    "outside upper left":    ((-0.02, 1.0), "upper right"),
    "outside center left":   ((-0.02, 0.5), "center right"),
    "outside lower left":    ((-0.02, 0.0), "lower right"),
    "outside top":           ((0.5, 1.02),  "lower center"),
    "outside upper center":  ((0.5, 1.02),  "lower center"),
    "outside bottom":        ((0.5, -0.02), "upper center"),
    "outside lower center":  ((0.5, -0.02), "upper center"),
}


def _legend_title_fontsize():
    """Legend title size: 1 pt smaller than the current legend body font size."""
    try:
        size = float(matplotlib.rcParams.get("legend.fontsize", 9))
    except (TypeError, ValueError):
        size = 9.0
    return size - 1


def _place_legend(ax, legend_cfg, extra_ax=None):
    """Place the legend according to *legend_cfg*.

    legend_cfg values
    -----------------
    false / null   — no legend
    true           — auto (show if any series have a label, default placement)
    loc: <str>     — standard matplotlib location, e.g. "upper right"
    loc: "outside right" | "outside bottom" | … — place outside the axes
    ncol: <int>    — number of columns  (default 1)
    title: <str>   — legend title

    extra_ax : Axes or None — a twin (secondary) axis whose handles/labels
               are merged in, so a dual-axis plot gets one combined legend.
    """
    handles, labels = ax.get_legend_handles_labels()
    if extra_ax is not None:
        h2, l2 = extra_ax.get_legend_handles_labels()
        handles, labels = handles + h2, labels + l2

    if not any(labels):
        return None

    if legend_cfg is False:
        return None

    # Normalise: True or missing → empty dict (auto placement)
    cfg = {} if (legend_cfg is True or legend_cfg is None) else dict(legend_cfg)

    loc   = str(cfg.get("loc", "best")).lower().strip()
    ncol  = int(cfg.get("ncol", 1))
    title = cfg.get("title", None)

    kwargs = dict(ncol=ncol)
    if title:
        kwargs["title"] = title
        kwargs["title_fontsize"] = _legend_title_fontsize()

    if loc in _OUTSIDE_LEGEND:
        bta, anchor_loc = _OUTSIDE_LEGEND[loc]
        return ax.legend(
            handles, labels,
            bbox_to_anchor=bta,
            loc=anchor_loc,
            bbox_transform=ax.transAxes,
            borderaxespad=0,
            **kwargs,
        )

    return ax.legend(handles, labels, loc=loc, **kwargs)


def _split_series_legend_entries(all_series):
    """Split a flat list of series configs into (color_entries, style_entries).

    The group (color-coded quantity, e.g. species/temperature) is taken from the
    part of the label before the first " - "; the variant (line style/marker-coded
    data type, e.g. exp/simToro/KT/FT) is the part after it. A series' explicit
    `group`/`variant` keys override the parsed label when present.

    Returns two ordered dicts (insertion order = first appearance):
      color_entries : group label   -> color
      style_entries : variant label -> {"linestyle": ..., "marker": ...}
    """
    color_entries = {}
    style_entries = {}

    for s in all_series:
        label = s.get("label", "")
        if " - " in label:
            group, variant = label.split(" - ", 1)
        else:
            group, variant = label, None
        group   = s.get("group",   group)
        variant = s.get("variant", variant)

        color = s.get("color")
        if group and color and group not in color_entries:
            color_entries[group] = color

        if variant and variant not in style_entries:
            if s.get("style", "line") == "scatter":
                style_entries[variant] = dict(linestyle="None", marker=s.get("marker", "o"))
            else:
                style_entries[variant] = dict(linestyle=s.get("linestyle", "-"), marker=s.get("marker"))

    return color_entries, style_entries


def _build_split_legend_handles(color_entries, style_entries):
    """Build proxy artists for a color-only legend and a style/marker-only legend."""
    color_handles = [Patch(facecolor=color, edgecolor="0.3", label=group)
                      for group, color in color_entries.items()]
    style_handles = [Line2D([0], [0], color="black",
                            linestyle=spec["linestyle"], marker=spec["marker"],
                            markerfacecolor="black", markeredgecolor="black",
                            label=variant)
                      for variant, spec in style_entries.items()]
    return color_handles, style_handles


def _split_anchor_axis(anchor_loc):
    """Classify an _OUTSIDE_LEGEND anchor keyword for splitting into two legends.

    Returns ("h", fixed_word) for a horizontal-center anchor (top/bottom outside
    placements, e.g. "upper center") — the two legends split left/right, pinned
    to the figure's left and right edges so they use the full width and cannot
    meet in the middle.

    Returns ("v", fixed_word) for a vertical-center anchor (left/right outside
    placements, e.g. "center left") — the two legends split top/bottom, pinned
    to the figure's top and bottom edges.

    Returns (None, None) for a fixed-corner anchor (e.g. "upper right"), where
    there is no free centerline to split along.
    """
    words = anchor_loc.split()
    if "center" not in words:
        return None, None
    return ("v", words[1]) if words[0] == "center" else ("h", words[0])


def _place_split_figure_legend(fig, legend_cfg, color_handles, style_handles):
    """Place two figure-level legends — one for color, one for style — spread
    across the figure's free space with three equal gaps (margin, middle gap,
    margin), so they never overlap and don't just sit centered next to each
    other. Legend title text is rendered 1 pt smaller than the legend body.

    legend_cfg extra keys (on top of the usual loc/title)
    ------------------------------------------------------
    color_title : str  — title for the color legend    (default "Color")
    style_title : str  — title for the style legend     (default "Line style")
    color_ncol  : int  — columns in the color legend    (default: one row)
    style_ncol  : int  — columns in the style legend    (default: one row)
    gap         : float — figure-fraction offset between the two legends,
                          only used for a fixed-corner `loc` (e.g. "outside
                          upper right") where there's no centerline to split
                          along and the two legends are stacked instead
                          (default 0.12)
    """
    cfg   = {} if (legend_cfg is True) else dict(legend_cfg)
    loc   = str(cfg.get("loc", "outside bottom")).lower().strip()
    color_title = cfg.get("color_title", "Color")
    style_title = cfg.get("style_title", "Line style")
    color_ncol  = int(cfg.get("color_ncol", max(len(color_handles), 1)))
    style_ncol  = int(cfg.get("style_ncol", max(len(style_handles), 1)))
    title_fontsize = _legend_title_fontsize()

    bta, anchor_loc = _OUTSIDE_LEGEND.get(loc, _OUTSIDE_LEGEND["outside bottom"])
    x0, y0 = bta
    direction, fixed_word = _split_anchor_axis(anchor_loc)

    common = dict(bbox_transform=fig.transFigure, borderaxespad=0)

    if direction == "h":
        # Horizontal outside placement (top/bottom) — split left/right, then
        # equalize the left margin, middle gap, and right margin.
        loc1, loc2 = f"{fixed_word} left", f"{fixed_word} right"
        leg1 = fig.legend(color_handles, [h.get_label() for h in color_handles],
                          bbox_to_anchor=(0.0, y0), loc=loc1, ncol=color_ncol,
                          title=color_title, title_fontsize=title_fontsize, **common)
        leg2 = fig.legend(style_handles, [h.get_label() for h in style_handles],
                          bbox_to_anchor=(1.0, y0), loc=loc2, ncol=style_ncol,
                          title=style_title, title_fontsize=title_fontsize, **common)
        fig.canvas.draw()
        w1 = leg1.get_window_extent().transformed(fig.transFigure.inverted()).width
        w2 = leg2.get_window_extent().transformed(fig.transFigure.inverted()).width
        gap = max((1.0 - w1 - w2) / 3.0, 0.0)
        leg1.set_bbox_to_anchor((gap, y0), transform=fig.transFigure)
        leg2.set_bbox_to_anchor((1.0 - gap, y0), transform=fig.transFigure)
        return

    if direction == "v":
        # Vertical outside placement (left/right) — split top/bottom, then
        # equalize the top margin, middle gap, and bottom margin.
        loc1, loc2 = f"upper {fixed_word}", f"lower {fixed_word}"
        leg1 = fig.legend(color_handles, [h.get_label() for h in color_handles],
                          bbox_to_anchor=(x0, 1.0), loc=loc1, ncol=color_ncol,
                          title=color_title, title_fontsize=title_fontsize, **common)
        leg2 = fig.legend(style_handles, [h.get_label() for h in style_handles],
                          bbox_to_anchor=(x0, 0.0), loc=loc2, ncol=style_ncol,
                          title=style_title, title_fontsize=title_fontsize, **common)
        fig.canvas.draw()
        h1 = leg1.get_window_extent().transformed(fig.transFigure.inverted()).height
        h2 = leg2.get_window_extent().transformed(fig.transFigure.inverted()).height
        gap = max((1.0 - h1 - h2) / 3.0, 0.0)
        leg1.set_bbox_to_anchor((x0, 1.0 - gap), transform=fig.transFigure)
        leg2.set_bbox_to_anchor((x0, gap), transform=fig.transFigure)
        return

    # Fixed corner (e.g. "outside upper right") — no free centerline to
    # spread along; stack the two legends with a fixed gap instead.
    gap = float(cfg.get("gap", 0.12))
    dy = -gap if y0 >= 0.5 else gap
    fig.legend(color_handles, [h.get_label() for h in color_handles],
               bbox_to_anchor=(x0, y0), loc=anchor_loc, ncol=color_ncol,
               title=color_title, title_fontsize=title_fontsize, **common)
    fig.legend(style_handles, [h.get_label() for h in style_handles],
               bbox_to_anchor=(x0, y0 + dy), loc=anchor_loc, ncol=style_ncol,
               title=style_title, title_fontsize=title_fontsize, **common)


def _place_figure_legend(fig, legend_cfg, handles, labels):
    """Place a figure-level legend shared across all panels.

    Uses fig.transFigure so bbox_to_anchor is in figure-fraction coordinates,
    which makes the _OUTSIDE_LEGEND offsets work the same way as for axes legends.
    """
    cfg   = {} if (legend_cfg is True) else dict(legend_cfg)
    loc   = str(cfg.get("loc", "outside right")).lower().strip()
    ncol  = int(cfg.get("ncol", 1))
    title = cfg.get("title", None)

    kwargs = dict(ncol=ncol)
    if title:
        kwargs["title"] = title
        kwargs["title_fontsize"] = _legend_title_fontsize()

    if loc in _OUTSIDE_LEGEND:
        bta, anchor_loc = _OUTSIDE_LEGEND[loc]
        fig.legend(handles, labels,
                   bbox_to_anchor=bta,
                   loc=anchor_loc,
                   bbox_transform=fig.transFigure,
                   borderaxespad=0,
                   **kwargs)
    else:
        fig.legend(handles, labels, loc=loc, **kwargs)


# ---------------------------------------------------------------------------
# Plot builder
# ---------------------------------------------------------------------------

def build_plot(plot_cfg, output_dir):
    with matplotlib.rc_context(_fontsize_rcparams(plot_cfg.get("fontsize"))):
        width  = float(plot_cfg.get("width",  3.5))
        height = float(plot_cfg.get("height", 2.8))
        fig, ax = plt.subplots(figsize=(width, height))

        series_list = plot_cfg.get("series", [])
        _assign_colors(series_list)

        # A series with `axis: right` goes on a twin y-axis sharing the same x-axis.
        has_right = any(s.get("axis", "left") == "right" for s in series_list)
        ax2 = ax.twinx() if has_right else None

        # Load all series data first so it can be reused for the zoom inset
        series_data = []
        for s in series_list:
            x, y = load_series(s)
            series_data.append((s, x, y))
            target_ax = ax2 if (ax2 is not None and s.get("axis", "left") == "right") else ax
            _render_series(target_ax, s, x, y, show_label=True)

        ax.set_xlabel(plot_cfg.get("xlabel", "x"))
        ax.set_ylabel(plot_cfg.get("ylabel", "y"))
        if ax2 is not None:
            ax2.set_ylabel(plot_cfg.get("ylabel2", ""))
            _style_twin_axis(ax,  series_list, "left")
            _style_twin_axis(ax2, series_list, "right")

        if "title" in plot_cfg:
            ax.set_title(plot_cfg["title"])
        if "xlim" in plot_cfg:
            ax.set_xlim(plot_cfg["xlim"])
        if "ylim" in plot_cfg:
            ax.set_ylim(plot_cfg["ylim"])
        if ax2 is not None and "ylim2" in plot_cfg:
            ax2.set_ylim(plot_cfg["ylim2"])

        if plot_cfg.get("xtick_pi"):
            _apply_pi_ticks(ax, "x", plot_cfg["xtick_pi"])
        if plot_cfg.get("ytick_pi"):
            _apply_pi_ticks(ax, "y", plot_cfg["ytick_pi"])
        if ax2 is not None and plot_cfg.get("ytick_pi2"):
            _apply_pi_ticks(ax2, "y", plot_cfg["ytick_pi2"])

        if plot_cfg.get("xtick_sci"):
            _apply_sci_ticks(ax, "x", plot_cfg["xtick_sci"])
        if plot_cfg.get("ytick_sci"):
            _apply_sci_ticks(ax, "y", plot_cfg["ytick_sci"])
        if ax2 is not None and plot_cfg.get("ytick_sci2"):
            _apply_sci_ticks(ax2, "y", plot_cfg["ytick_sci2"])

        show_grid = plot_cfg.get("grid", True)
        if show_grid:
            ax.grid(True)
            if ax2 is not None:
                ax2.grid(False)   # avoid overlapping gridlines from the twin axis

        _place_legend(ax, plot_cfg.get("legend", True), extra_ax=ax2)

        fig.tight_layout()

        zoom_cfg = plot_cfg.get("zoom")
        if zoom_cfg:
            _add_zoom_inset(ax, zoom_cfg, series_data, show_grid)

        name     = plot_cfg.get("name", "figure")
        out_path = os.path.join(output_dir, f"{name}.svg")
        fig.savefig(out_path, format="svg")
        plt.close(fig)
        print(f"  saved  {out_path}")


# ---------------------------------------------------------------------------
# Multi-panel figure builder
# ---------------------------------------------------------------------------

def build_figure(fig_cfg, output_dir):
    """Build a grid of panels into a single SVG with an optional shared legend.

    fig_cfg keys
    ------------
    name   : str          output file stem
    rows   : int          grid rows  (default 1)
    cols   : int          grid cols  (default 1)
    width  : float        total figure width in inches  (default 7.0)
    height : float        total figure height in inches (default 5.6)
    sharex : bool         share x-axis across columns  (default false)
    sharey : bool         share y-axis across rows     (default false)
    legend : dict|false   figure-level shared legend; same options as plot-level legend.
                          When set, per-panel legend keys are ignored.
                          When omitted, each panel manages its own legend.
                          split: true splits it into two side-by-side legends instead
                          of one combined legend: a color legend (one entry per group,
                          taken from the label before " - ", or a series' `group` key)
                          and a line-style/marker legend (one entry per variant, taken
                          from the label after " - ", or a series' `variant` key).
                          See color_title/style_title/color_ncol/style_ncol/gap.
    panels : list         panel configs in row-major order (left→right, top→bottom).
                          Use null for an empty cell. Each panel supports the same
                          keys as a plot: xlabel, ylabel, title, xlim, ylim, grid,
                          series, zoom, and (if no figure-level legend) legend.
                          ylabel2/ylim2 set the label/limits of a secondary (right)
                          y-axis, used by any series with `axis: right` (see below).
                          xtick_pi/ytick_pi/ytick_pi2 format that axis' ticks as
                          multiples of pi (True → steps of pi/4, or an int denominator).
                          xtick_sci/ytick_sci/ytick_sci2 format that axis' ticks in
                          scientific notation (True → 2 decimal places, or an int
                          giving the mantissa decimal places).
    """
    with matplotlib.rc_context(_fontsize_rcparams(fig_cfg.get("fontsize"))):
        rows   = int(fig_cfg.get("rows",   1))
        cols   = int(fig_cfg.get("cols",   1))
        width  = float(fig_cfg.get("width",  7.0))
        height = float(fig_cfg.get("height", 5.6))
        sharex = fig_cfg.get("sharex", False)
        sharey = fig_cfg.get("sharey", False)

        fig, axes = plt.subplots(rows, cols,
                                 figsize=(width, height),
                                 sharex=sharex, sharey=sharey,
                                 squeeze=False)

        panels            = fig_cfg.get("panels", [])
        figure_legend_cfg = fig_cfg.get("legend")   # None → per-panel legends

        # Assign colors globally so the same label always gets the same color
        _assign_colors_panels(panels)

        all_handles = {}   # label → handle; first appearance wins (for shared legend)
        zoom_tasks  = []   # deferred: add zoom insets after tight_layout

        for idx, panel_cfg in enumerate(panels):
            row = idx // cols
            col = idx % cols
            if row >= rows:
                break

            ax = axes[row][col]

            if not isinstance(panel_cfg, dict):
                ax.set_visible(False)
                continue

            panel_series = panel_cfg.get("series", [])
            has_right = any(s.get("axis", "left") == "right" for s in panel_series)
            ax2 = ax.twinx() if has_right else None

            series_data = []
            for s in panel_series:
                x, y = load_series(s)
                series_data.append((s, x, y))
                target_ax = ax2 if (ax2 is not None and s.get("axis", "left") == "right") else ax
                _render_series(target_ax, s, x, y, show_label=True)

            # Collect unique handles for the shared legend (dedup by label)
            legend_pairs = list(zip(*ax.get_legend_handles_labels()))
            if ax2 is not None:
                legend_pairs += list(zip(*ax2.get_legend_handles_labels()))
            for h, l in legend_pairs:
                all_handles.setdefault(l, h)

            ax.set_xlabel(panel_cfg.get("xlabel", "x"))
            ax.set_ylabel(panel_cfg.get("ylabel", "y"))
            if ax2 is not None:
                ax2.set_ylabel(panel_cfg.get("ylabel2", ""))
                _style_twin_axis(ax,  panel_series, "left")
                _style_twin_axis(ax2, panel_series, "right")

            if "title" in panel_cfg:
                ax.set_title(panel_cfg["title"])
            if "xlim" in panel_cfg:
                ax.set_xlim(panel_cfg["xlim"])
            if "ylim" in panel_cfg:
                ax.set_ylim(panel_cfg["ylim"])
            if ax2 is not None and "ylim2" in panel_cfg:
                ax2.set_ylim(panel_cfg["ylim2"])

            if panel_cfg.get("xtick_pi"):
                _apply_pi_ticks(ax, "x", panel_cfg["xtick_pi"])
            if panel_cfg.get("ytick_pi"):
                _apply_pi_ticks(ax, "y", panel_cfg["ytick_pi"])
            if ax2 is not None and panel_cfg.get("ytick_pi2"):
                _apply_pi_ticks(ax2, "y", panel_cfg["ytick_pi2"])

            if panel_cfg.get("xtick_sci"):
                _apply_sci_ticks(ax, "x", panel_cfg["xtick_sci"])
            if panel_cfg.get("ytick_sci"):
                _apply_sci_ticks(ax, "y", panel_cfg["ytick_sci"])
            if ax2 is not None and panel_cfg.get("ytick_sci2"):
                _apply_sci_ticks(ax2, "y", panel_cfg["ytick_sci2"])

            show_grid = panel_cfg.get("grid", True)
            if show_grid:
                ax.grid(True)
                if ax2 is not None:
                    ax2.grid(False)   # avoid overlapping gridlines from the twin axis

            # Per-panel legend only when no figure-level legend is requested
            if figure_legend_cfg is None:
                _place_legend(ax, panel_cfg.get("legend", True), extra_ax=ax2)

            zoom_cfg = panel_cfg.get("zoom")
            if zoom_cfg:
                zoom_tasks.append((ax, zoom_cfg, series_data, show_grid))

        # Hide surplus axes when panels < rows * cols
        for idx in range(len(panels), rows * cols):
            axes[idx // cols][idx % cols].set_visible(False)

        fig.tight_layout()

        # Figure-level shared legend (placed after tight_layout, before zoom insets)
        if figure_legend_cfg is not None and figure_legend_cfg is not False:
            if isinstance(figure_legend_cfg, dict) and figure_legend_cfg.get("split"):
                all_series = [s for p in panels if isinstance(p, dict) for s in p.get("series", [])]
                color_entries, style_entries = _split_series_legend_entries(all_series)
                color_handles, style_handles = _build_split_legend_handles(color_entries, style_entries)
                _place_split_figure_legend(fig, figure_legend_cfg, color_handles, style_handles)
            elif all_handles:
                _place_figure_legend(fig,
                                     figure_legend_cfg,
                                     list(all_handles.values()),
                                     list(all_handles.keys()))

        # Zoom insets last — incompatible with tight_layout
        for ax, zoom_cfg, series_data, show_grid in zoom_tasks:
            _add_zoom_inset(ax, zoom_cfg, series_data, show_grid)

        name     = fig_cfg.get("name", "figure")
        out_path = os.path.join(output_dir, f"{name}.svg")
        fig.savefig(out_path, format="svg")
        plt.close(fig)
        print(f"  saved  {out_path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _apply_latex_settings(cfg):
    """Enable full LaTeX rendering if requested, otherwise mathtext handles $…$ natively."""
    if not cfg.get("latex", False):
        return
    try:
        matplotlib.rcParams.update({
            "text.usetex":   True,
            "font.family":   "serif",
            "font.serif":    ["Computer Modern Roman"],
        })
    except Exception as exc:
        print(f"[warn] LaTeX rendering unavailable ({exc}); falling back to mathtext",
              file=sys.stderr)
        matplotlib.rcParams["text.usetex"] = False


def process_config(config_path):
    if not os.path.exists(config_path):
        print(f"[error] config not found: {config_path}", file=sys.stderr)
        return

    with open(config_path, "r") as fh:
        cfg = yaml.safe_load(fh)

    _apply_latex_settings(cfg)

    project    = cfg.get("project", "default")
    output_dir = os.path.join(OUTPUT_DIR, project)
    os.makedirs(output_dir, exist_ok=True)

    plots   = cfg.get("plots",   [])
    figures = cfg.get("figures", [])
    print(f"\n[{config_path}]  project={project}  "
          f"({len(plots)} plot(s), {len(figures)} figure(s))")
    for plot_cfg in plots:
        build_plot(plot_cfg, output_dir)
    for fig_cfg in figures:
        build_figure(fig_cfg, output_dir)


def main():
    parser = argparse.ArgumentParser(
        description="Generate journal-quality SVG plots from YAML configs.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Example:  python plotter.py my_study.yaml",
    )
    parser.add_argument("configs", nargs="+", metavar="config.yaml",
                        help="One or more YAML configuration files")
    args = parser.parse_args()

    for cfg_path in args.configs:
        process_config(cfg_path)


if __name__ == "__main__":
    main()
