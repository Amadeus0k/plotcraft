# plotter.py — YAML configuration reference

`plotter.py` reads one or more YAML config files and renders journal-quality
SVG figures with matplotlib.

```
python plotter.py <config.yaml> [config2.yaml ...]
```

Data files are resolved under `data/<path>`. Output SVGs are written to
`output/<project>/<name>.svg`.

---

## Top-level keys

| Key       | Type          | Default     | Description                                              |
|-----------|---------------|-------------|------------------------------------------------------------|
| `project` | string        | `"default"` | Output subfolder: `output/<project>/`                     |
| `latex`   | bool          | `false`     | Use full LaTeX rendering (`text.usetex`) instead of mathtext. Falls back to mathtext with a warning if LaTeX isn't available on the system. |
| `plots`   | list          | `[]`        | List of single-axes plot configs (see [Plot config](#plot-config)). |
| `figures` | list          | `[]`        | List of multi-panel figure configs (see [Figure config](#figure-config)). |

```yaml
project: rdeTurb
latex: true

plots:
  - ...
figures:
  - ...
```

---

## Plot config

Each entry under `plots:` produces one standalone SVG (`output/<project>/<name>.svg`).

| Key        | Type            | Default   | Description |
|------------|-----------------|-----------|--------------|
| `name`     | string          | `"figure"`| Output file stem. |
| `xlabel`   | string          | `"x"`     | X-axis label. |
| `ylabel`   | string          | `"y"`     | Left y-axis label. |
| `ylabel2`  | string          | `""`      | Right y-axis label — only used if any series has `axis: right` (see [Series config](#series-config)). |
| `title`    | string          | —         | Axes title. |
| `width`    | float (inches)  | `3.5`     | Figure width. |
| `height`   | float (inches)  | `2.8`     | Figure height. |
| `xlim`     | `[min, max]`    | auto      | X-axis limits. |
| `ylim`     | `[min, max]`    | auto      | Left y-axis limits. |
| `ylim2`    | `[min, max]`    | auto      | Right y-axis limits (dual-axis plots only). |
| `grid`     | bool            | `true`    | Show gridlines on the left/primary axis. The right (twin) axis never draws its own grid, to avoid overlapping lines. |
| `legend`   | bool / dict / `false` | `true` (auto) | See [Legend config](#legend-config). |
| `fontsize` | number / dict   | —         | See [Fontsize config](#fontsize-config). |
| `xtick_pi` | `true` / int    | —         | Format x-axis ticks as multiples of π (e.g. `-π`, `-π/2`, `0`, `π/2`, `π`) instead of raw decimals — for angle axes in radians. See [Pi-tick config](#pi-tick-config). |
| `ytick_pi` | `true` / int    | —         | Same, for the left y-axis. |
| `ytick_pi2`| `true` / int    | —         | Same, for the right (twin) y-axis (dual-axis plots only). |
| `xtick_sci` | `true` / int   | —         | Format x-axis ticks in scientific notation (e.g. `1.05×10⁵`) instead of raw decimals. See [Scientific-tick config](#scientific-tick-config). |
| `ytick_sci` | `true` / int   | —         | Same, for the left y-axis. |
| `ytick_sci2`| `true` / int   | —         | Same, for the right (twin) y-axis (dual-axis plots only). |
| `zoom`     | dict            | —         | Adds a magnified inset. See [Zoom config](#zoom-config). |
| `series`   | list            | `[]`      | The data series to plot. See [Series config](#series-config). |

### Single-axis example

```yaml
plots:
  - name: pressure_position
    xlabel: "z (m)"
    ylabel: "p (Pa)"
    width:  4
    height: 2.8
    grid: true
    series:
      - label: "Pressure"
        file:  rdeturb/line.csv
        x: Points_2
        y: p
        style: line
```

### Dual-axis example (two y-axes, shared x-axis)

Give one or more series `axis: right` to plot them on a secondary y-axis
(`ax.twinx()`). `ylabel2` / `ylim2` control that right-hand axis. When a
side has exactly one series, its axis label and tick labels are
automatically colored to match that series' line color. The legend
combines entries from both axes into one box.

```yaml
plots:
  - name: pressure_mach_position
    xlabel: "z (m)"
    ylabel:  "p (Pa)"        # left axis
    ylabel2: "Mach (-)"      # right axis
    width:  4
    height: 2
    grid: true
    legend: false
    series:
      - label: "Pressure"
        file:  rdeturb/line.csv
        x: Points_2
        y: p
        style: line
        axis: left            # default, can be omitted
      - label: "Mach"
        file:  rdeturb/line.csv
        x: Points_2
        y: Ma
        style: line
        axis: right
```

---

## Series config

Each entry under a plot's/panel's `series:` list describes one data curve.

| Key          | Type    | Default    | Description |
|--------------|---------|------------|--------------|
| `file`       | string  | *required* | Path under `data/`, e.g. `rdeturb/line.csv`. |
| `x`          | string  | *required* | Column name for x values. |
| `y`          | string  | *required* | Column name for y values. |
| `format`     | string  | auto       | `"csv"` or `"dat"`. Auto-detected: `dat` if the file's first non-empty line starts with `#`, else `csv`. See [Data file formats](#data-file-formats). |
| `label`      | string  | `""`       | Legend label. Series with no label are omitted from the legend. |
| `style`      | string  | `"line"`   | `"line"` or `"scatter"`. |
| `axis`       | string  | `"left"`   | `"left"` or `"right"`. `"right"` plots on a secondary (twin) y-axis — see [Dual-axis example](#dual-axis-example-two-y-axes-shared-x-axis). |
| `color`      | string  | auto       | Any matplotlib color (e.g. `"#0072B2"`, `"red"`). If omitted, colors are auto-assigned from a colorblind-safe palette; the same label always gets the same color across a whole figure. |
| `linestyle`  | string  | `"-"`      | matplotlib linestyle (`"-"`, `"--"`, `":"`, `"-."`, ...). Used only for `style: line`. |
| `linewidth`  | float   | rcParam default (`1.2`) | Line width. Used only for `style: line`. |
| `marker`     | string  | `None`     | matplotlib marker (`"o"`, `"s"`, `"^"`, ...). Used only for `style: line`. |
| `markersize` | float   | `16`       | Marker size (points²). Used only for `style: scatter`. |
| `rotate`     | float (radians) | —  | Rotates `(x, y)` around the origin by this angle (used for angular/theta data), wrapping x to `[-pi, pi]` and re-sorting. |
| `smooth`     | int / dict | —       | Smooths and resamples the series. See [Smoothing config](#smoothing-config). |
| `group`      | string  | parsed from `label` | Color-legend grouping key, used only by a figure's [split legend](#split-legend-color--line-style). Defaults to the part of `label` before the first `" - "`. |
| `variant`    | string  | parsed from `label` | Line-style-legend grouping key, used only by a figure's [split legend](#split-legend-color--line-style). Defaults to the part of `label` after the first `" - "`. |

```yaml
series:
  - label: "Pressure"
    file:  rdeturb/line.csv
    x: Points_2
    y: p
    style: line
    color: "#0072B2"
    linestyle: "--"
    linewidth: 1.5
    marker: "o"
    axis: left
```

---

## Smoothing config

Set `smooth` on a series to smooth and resample it.

- **Shorthand:** an integer is treated as the Savitzky-Golay window size.

  ```yaml
  smooth: 11
  ```

- **Full form:** a dict with a `method` key.

  **`method: savgol`** (default) — Savitzky-Golay filter, then cubic resample.

  | Key         | Default | Description |
  |-------------|---------|--------------|
  | `window`    | `11`    | Window length (forced odd, clamped to data length). |
  | `polyorder` | `3`     | Polynomial order. |
  | `resample`  | `500`   | Number of output points. |

  ```yaml
  smooth:
    method: savgol
    window: 15
    polyorder: 3
    resample: 500
  ```

  **`method: spline`** — smoothing spline; does **not** pass through every point.

  | Key        | Default | Description |
  |------------|---------|--------------|
  | `factor`   | `0.5`   | `0` = interpolating (passes through all points), `1` = very smooth. |
  | `resample` | `500`   | Number of output points. |

  ```yaml
  smooth:
    method: spline
    factor: 0.3
    resample: 500
  ```

---

## Data file formats

Controlled by a series' `format` key (or auto-detected).

- **`csv`** — standard comma-separated file with a header row (`pandas.read_csv` defaults).
- **`dat`** — whitespace-delimited file; column names are taken from the first line
  starting with `#`:

  ```
  # Points_2 p Ma
  0.000  101325.0  0.10
  0.001  101200.4  0.12
  ...
  ```

Auto-detection rule: if the file's first line starts with `#`, it's treated as `dat`; otherwise `csv`.

---

## Legend config

Set via a plot's/panel's `legend` key (or `figures[].legend` for a shared legend — see [Figure config](#figure-config)).

| Value                    | Behavior |
|--------------------------|----------|
| omitted / `true`         | Auto: shown if any series has a `label`, placed at `"best"`. |
| `false`                  | No legend. |
| dict                     | Explicit placement/styling, see below. |

Dict keys:

| Key     | Type   | Default  | Description |
|---------|--------|----------|--------------|
| `loc`   | string | `"best"` | Any standard matplotlib location (`"upper right"`, `"lower left"`, `"center"`, `"best"`, ...), **or** one of the `"outside ..."` keywords below to place the legend outside the axes. |
| `ncol`  | int    | `1`      | Number of legend columns. |
| `title` | string | —        | Legend title. |

`"outside ..."` locations (legend drawn outside the plot area):

```
outside right          outside upper right     outside center right    outside lower right
outside left           outside upper left      outside center left     outside lower left
outside top            outside upper center
outside bottom         outside lower center
```

```yaml
legend:
  loc: "outside right"
  ncol: 1
  title: "Series"
```

```yaml
legend: false
```

On a dual-axis plot, the legend automatically combines entries from both the left and right axes into a single box.

### Split legend (color + line style)

A **figure-level** legend (`figures[].legend` — see [Figure config](#figure-config))
can be split into two side-by-side legends instead of one combined box: a
color legend (one swatch per group) and a line-style/marker legend (one
entry per variant, drawn in black so it conveys shape only). This is useful
when every series' label follows a `"<group> - <variant>"` convention, e.g.
`"H2O - exp"`, `"H2O - simToro"`, `"T - KT"` — the color legend then shows
one entry per group (`H2O`, `H2`, `N2`, `T`, ...) and the style legend shows
one entry per variant (`exp`, `simToro`, `KT`, `FT`, ...), instead of every
group×variant combination.

Group/variant are parsed from each series' `label` by splitting on the first
`" - "` (group = before, variant = after); a series' explicit `group` /
`variant` keys override that parsing (see [Series config](#series-config)).

Set `split: true` on the figure's `legend`:

| Key           | Type   | Default        | Description |
|---------------|--------|----------------|--------------|
| `split`       | bool   | `false`        | Split into a color legend + a style legend instead of one combined legend. |
| `loc`         | string | `"outside bottom"` | Same `"outside ..."` keywords as a normal legend. For a horizontal-center location (`"outside bottom"`, `"outside top"`, ...) the two legends are laid out left/right with three **equal** gaps — left margin, middle gap, right margin — computed from each legend's actual rendered size, so spacing stays even regardless of how wide either legend is and they can never overlap. For a vertical-center location (`"outside right"`, `"outside left"`) the same happens top/bottom (top margin, middle gap, bottom margin). For a fixed-corner location (`"outside upper right"`, ...) there's no centerline to split along, so they're stacked using a fixed `gap` instead. |
| `color_title` | string | `"Color"`      | Title of the color legend. |
| `style_title` | string | `"Line style"` | Title of the style legend. |
| `color_ncol`  | int    | one row        | Columns in the color legend. |
| `style_ncol`  | int    | one row        | Columns in the style legend. |
| `gap`         | float  | `0.12`         | Figure-fraction offset between the two legends — only used for a fixed-corner `loc`; ignored otherwise, since the gap is then computed automatically for equal spacing. |

Every legend title (split or not) is rendered 1 pt smaller than that legend's body/entry text (`legend.fontsize`, from [Fontsize config](#fontsize-config) if set, otherwise the rcParams default).

```yaml
figures:
  - name: species_comparison
    rows: 1
    cols: 2
    legend:
      loc: outside bottom
      split: true
      color_title: "Species / Temperature"
      style_title: "Data type"
    panels:
      - series:
          - label: "H2O - exp"
            style: scatter
            color: red
            ...
          - label: "H2O - simToro"
            style: line
            linestyle: "--"
            color: red
            ...
```

> Note: `split` is only supported for a figure-level legend, not a single [plot](#plot-config)'s legend.

---

## Pi-tick config

Set `xtick_pi` / `ytick_pi` / `ytick_pi2` on a plot or panel to format that
axis' tick labels as multiples of π (`-π`, `-π/2`, `0`, `π/2`, `π`, ...)
instead of raw decimal numbers — useful for angle axes given in radians
(e.g. `theta`).

| Value  | Behavior |
|--------|----------|
| omitted / `false` | Normal decimal tick labels (default). |
| `true`             | π-formatted ticks, spaced every π/4. |
| int (e.g. `2`, `6`)| π-formatted ticks, spaced every π/*n* (the int is the denominator). |

Ticks are snapped to exact multiples of π/*n* (via `MultipleLocator`) and
labeled with the simplest reduced fraction, e.g. with `den=4`: `-π`, `-3π/4`,
`-π/2`, `-π/4`, `0`, `π/4`, `π/2`, `3π/4`, `π`.

```yaml
- name: pressure_ref
  xlabel: "θ (rad)"
  ylabel: "p (Pa)"
  xtick_pi: true        # ticks every pi/4
  series:
    - label: "Pressure"
      file:  rdeturb/rde_stator.csv
      x: theta
      y: p
```

```yaml
ytick_pi2: 2             # right axis ticks every pi/2
```

---

## Scientific-tick config

Set `xtick_sci` / `ytick_sci` / `ytick_sci2` on a plot or panel to format
that axis in journal-standard scientific notation — useful when values
share a large common order of magnitude (e.g. pressure in Pa). This is
matplotlib's standard convention: tick labels show only the mantissa
(`0.90`, `0.95`, `1.00`, ...) and the shared power of ten is printed once,
as an offset label at the top (or right, for a y-axis) of the axis, e.g.
`×10⁵` — **not** repeated on every tick.

| Value  | Behavior |
|--------|----------|
| omitted / `false` | Normal decimal tick labels (default). |
| `true`             | Scientific notation, automatic mantissa precision. |
| int (e.g. `1`, `3`)| Scientific notation with that many fixed mantissa decimal places. |

```yaml
- name: pressure_mach_position
  xlabel: "z (m)"
  ylabel: "p (Pa)"
  ytick_sci: true          # ticks: 0.90, 0.95, 1.00, 1.05 ... with "x10^5" shown once
  series:
    - label: "Pressure"
      file:  rdeturb/line.csv
      x: Points_2
      y: p
```

```yaml
ytick_sci2: 1              # right axis, 1 mantissa decimal place
```

---

## Zoom config

Set `zoom` on a plot/panel to add a magnified inset with a highlighted region and connector lines back to the main axes.

| Key      | Type          | Default   | Description |
|----------|---------------|-----------|--------------|
| `xmin`   | float         | *required*| Region of interest, x min. |
| `xmax`   | float         | *required*| Region of interest, x max. |
| `ymin`   | float         | *required*| Region of interest, y min. |
| `ymax`   | float         | *required*| Region of interest, y max. |
| `scale`  | float / `"xN"`| `1`       | Magnification factor for the inset panel size (e.g. `"x3"` or `3`). The inset always shows exactly `xmin`–`xmax`, `ymin`–`ymax`; `scale` only controls how large the panel is drawn. |
| `width`  | float (%)     | `35`      | Base inset width as a percentage of the parent axes, before `scale`. |
| `height` | float (%)     | `35`      | Base inset height as a percentage of the parent axes, before `scale`. |
| `loc`    | string / int  | auto      | `"upper_right"` / `"upper_left"` / `"lower_left"` / `"lower_right"` (or `1`–`4`). If omitted, the least-populated quadrant is chosen automatically. |

```yaml
zoom:
  xmin: 0.01
  xmax: 0.03
  ymin: 100000
  ymax: 102000
  scale: x2
  loc: upper_left
```

> Note: zoom insets currently render series on the plot's primary axis only; they are not aware of a dual-axis (`axis: right`) split.

---

## Fontsize config

Set `fontsize` on a plot or figure to override matplotlib rcParams for that render only.

- **Shorthand:** a single number sets the base size; ticks and legend become 1pt smaller.

  ```yaml
  fontsize: 12
  ```

- **Full form:** a dict overriding individual elements (each optional; `base` sets all of them, other keys override `base`).

  | Key      | Affects |
  |----------|---------|
  | `base`   | All of the below at once. |
  | `label`  | Axis label size. |
  | `title`  | Axes title size. |
  | `tick`   | X and Y tick label size. |
  | `legend` | Legend text size. |

  ```yaml
  fontsize:
    base: 11
    title: 12
    tick: 9
  ```

---

## Figure config

Each entry under `figures:` produces a single SVG containing a grid of panels
(`output/<project>/<name>.svg`).

| Key       | Type            | Default   | Description |
|-----------|-----------------|-----------|--------------|
| `name`    | string          | `"figure"`| Output file stem. |
| `rows`    | int             | `1`       | Grid rows. |
| `cols`    | int             | `1`       | Grid columns. |
| `width`   | float (inches)  | `7.0`     | Total figure width. |
| `height`  | float (inches)  | `5.6`     | Total figure height. |
| `sharex`  | bool            | `false`   | Share x-axis across columns. |
| `sharey`  | bool            | `false`   | Share y-axis across rows. |
| `fontsize`| number / dict   | —         | Same as [Fontsize config](#fontsize-config). |
| `legend`  | dict / `false`  | per-panel | Figure-level shared legend (same options as [Legend config](#legend-config)). When set, per-panel `legend` keys are ignored and one combined legend (deduplicated by label) is drawn for the whole figure — or, with `split: true`, two side-by-side legends (see [Split legend](#split-legend-color--line-style)). When omitted, each panel manages its own legend. |
| `panels`  | list            | `[]`      | Panel configs, in row-major order (left→right, top→bottom). Use `null` for an empty cell. |

Each panel supports the same keys as a [plot](#plot-config): `xlabel`, `ylabel`,
`ylabel2`, `title`, `xlim`, `ylim`, `ylim2`, `grid`, `series`, `zoom`, `axis`
(per-series), `xtick_pi`, `ytick_pi`, `ytick_pi2`, `xtick_sci`, `ytick_sci`,
`ytick_sci2`, and — only if the figure has no `legend` key — its own `legend`.

Colors are assigned consistently across all panels: the same series `label`
always gets the same color everywhere in the figure.

```yaml
figures:
  - name: overview
    rows: 1
    cols: 2
    width: 7.0
    height: 3.0
    sharex: true
    legend:
      loc: "outside right"
    panels:
      - xlabel: "z (m)"
        ylabel: "p (Pa)"
        series:
          - label: "Pressure"
            file:  rdeturb/line.csv
            x: Points_2
            y: p
      - xlabel: "z (m)"
        ylabel: "Mach (-)"
        series:
          - label: "Mach"
            file:  rdeturb/line.csv
            x: Points_2
            y: Ma
```

---

## Full key cheat-sheet

```yaml
project: <string>
latex: <bool>

plots:
  - name: <string>
    xlabel: <string>
    ylabel: <string>
    ylabel2: <string>          # right axis, dual-axis plots only
    title: <string>
    width: <float>
    height: <float>
    xlim: [<min>, <max>]
    ylim: [<min>, <max>]
    ylim2: [<min>, <max>]      # right axis
    grid: <bool>
    fontsize: <number|dict>
    legend: <bool|dict|false>
    xtick_pi: <true|int>       # ticks as multiples of pi (int = denominator)
    ytick_pi: <true|int>
    ytick_pi2: <true|int>      # right axis
    xtick_sci: <true|int>      # ticks in scientific notation (int = decimal places)
    ytick_sci: <true|int>
    ytick_sci2: <true|int>     # right axis
    zoom: <dict>
    series:
      - file: <string>          # required
        x: <string>              # required
        y: <string>              # required
        format: csv|dat
        label: <string>
        style: line|scatter
        axis: left|right
        color: <string>
        linestyle: <string>
        linewidth: <float>
        marker: <string>
        markersize: <float>
        rotate: <float>
        smooth: <int|dict>
        group: <string>           # split-legend color group (default: parsed from label)
        variant: <string>         # split-legend style group  (default: parsed from label)

figures:
  - name: <string>
    rows: <int>
    cols: <int>
    width: <float>
    height: <float>
    sharex: <bool>
    sharey: <bool>
    fontsize: <number|dict>
    legend:                      # shared across all panels; omit for per-panel legends
      loc: <string>
      ncol: <int>
      title: <string>
      split: <bool>              # true = color legend + line-style legend side by side
      color_title: <string>
      style_title: <string>
      color_ncol: <int>
      style_ncol: <int>
      gap: <float>
    panels:
      - <same keys as a plot, except top-level name/width/height>
      - null                    # empty cell
```
