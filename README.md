# plotter

A single-script, config-driven plotting tool for journal-quality figures.

## Why

Most plotting workflows end up as a pile of one-off Python scripts: one per
paper, one per figure, each rewritten from scratch and each with its own
half-remembered rcParams tweaks. The result is figures that don't quite match
each other, and a setup you have to reconstruct from memory every time you
need a new plot.

`plotter.py` is an attempt at something more consistent: a single script,
driven entirely by YAML config files, that produces publication-ready SVG
figures with the same fonts, colors, tick styles, and layout rules every
time — across different projects, papers, and datasets — without touching
the plotting code itself. Describe the plot in YAML, run the script, get a
consistent figure. No plotting logic to rewrite, no styling to remember.

Features include single- and dual-axis plots, multi-panel figures with
shared legends, a colorblind-safe palette with consistent color-per-label
assignment, zoom insets, smoothing (Savitzky-Golay / spline), π- and
scientific-notation tick formatting, and split color/line-style legends.

## Requirements

- Python 3
- `matplotlib`, `numpy`, `pandas`, `scipy`, `pyyaml`

```
pip install matplotlib numpy pandas scipy pyyaml
```

## Usage

```
python plotter.py <config.yaml> [config2.yaml ...]
```

- Data files referenced in a config are resolved under `data/<path>`.
- Output SVGs are written to `output/<project>/<name>.svg`.

See [`example_config.yaml`](example_config.yaml) for an annotated example
covering single-axis plots, dual-axis plots, zoom insets, smoothing, and
legend placement, and [`CONFIG.md`](CONFIG.md) for the full YAML reference.

## License

MIT — see [LICENSE](LICENSE).

---

*This project's code and documentation were developed with the assistance of AI (Claude).*
