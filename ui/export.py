"""Export the in-memory document to SVG, reusing plotter.build_plot /
build_figure exactly — so a GUI export is byte-identical to what the CLI
would produce from the same YAML, not a second rendering code path."""

import os

import plotter


def output_dir_for(doc):
    project = doc.doc.get("project", "default")
    return os.path.join(doc.project_dir, "output", project)


def export_document(doc, only_path=None):
    """Export all plots/figures, or just the one at `only_path`
    (e.g. ("plots", 2)) if given."""
    plotter._apply_latex_settings(doc.doc)
    old_data_dir = plotter.DATA_DIR
    plotter.set_data_dir(doc.data_dir)
    output_dir = output_dir_for(doc)
    os.makedirs(output_dir, exist_ok=True)
    try:
        for i in range(len(doc.doc.get("plots", []))):
            if only_path is not None and only_path != ("plots", i):
                continue
            plotter.build_plot(doc.render_copy(("plots", i)), output_dir)
        for i in range(len(doc.doc.get("figures", []))):
            if only_path is not None and only_path != ("figures", i):
                continue
            plotter.build_figure(doc.render_copy(("figures", i)), output_dir)
    finally:
        plotter.set_data_dir(old_data_dir)
    return output_dir
