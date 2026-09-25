"""Live matplotlib preview: renders the real Figure plotter.py would export.

Two render entry points:
  render_now()      - immediate, used on tree selection (feels instant).
  request_render()  - 200ms debounced, used while typing in the inspector.

Both end up in _do_render(), which is the one place that must get two
subtle things right (see plotter.py's own comments on the same points):

  1. Render a deep copy of the node, never the live document — plotter's
     color auto-assignment writes colors back into the dicts it's given,
     and doing that to the live document would bake auto-colors into the
     user's YAML on the next save.
  2. Any draw of the figure (not just plotter's own savefig) must happen
     under the same fontsize rc_context used to build it, or matplotlib's
     "auto" tick-count locator silently reads the wrong tick-label size and
     picks a different number of ticks. See plotter.build_plot's comment.

There's a third thing specific to on-screen display: plotter.py sets
savefig.bbox: "tight" globally, so the exported SVG always auto-expands to
fit content that sits outside the nominal figure box — most visibly a
`legend: {loc: outside right}` (or any other "outside ..." placement).
FigureCanvasQTAgg.draw() has no such concept; left alone, it clips exactly
that content at the nominal figure edge, so the preview would show
something the export doesn't. _expand_to_tight_bbox reproduces savefig's
own tight-bbox pass (matplotlib._tight_bbox, the same private call
print_figure makes internally) so the on-screen canvas grows to match what
gets exported. It degrades to the nominal (possibly clipped) size if that
private API ever changes shape, rather than crashing the app over a
preview nicety.

A fourth thing, not about rendering but about the toolbar above the
preview: plotter.render_plot/render_figure build every figure via
plt.subplots(), and with PyQt6 installed matplotlib auto-selects the
interactive "qtagg" backend for pyplot — so *every single render* was
silently also constructing a whole separate FigureManagerQT (its own
canvas + its own NavigationToolbar2QT + an unshown window) that we then
discarded via fig.set_canvas(our_canvas) without ever closing. Discarding
it doesn't disconnect its event callbacks, which is why the toolbar
buttons never worked — clicks were reaching a hidden, inert toolbar
instance, not the one on screen — and it leaked a Qt canvas/toolbar/manager
on every render besides. Fixed at the source in plotter.py
(matplotlib.use("Agg"), before pyplot is ever imported there) rather than
here, since plotter.py is the first thing in this app's import graph to
touch matplotlib.pyplot — by the time this module runs, pyplot's backend
would already be locked in. It has no effect on
FigureCanvasQTAgg/NavigationToolbar2QT here, which are imported and
constructed directly, never through pyplot.
"""

import matplotlib
import matplotlib.pyplot as plt
from matplotlib.backend_bases import _Mode
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from PyQt6.QtCore import QEvent, QTimer, Qt
from PyQt6.QtGui import QDoubleValidator
from PyQt6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy,
    QToolBar, QVBoxLayout, QWidget,
)

import plotter
from . import settings

ZOOM_LEVELS = [("Fit", None), ("50%", 0.5), ("75%", 0.75), ("100%", 1.0),
               ("150%", 1.5), ("200%", 2.0)]
BASE_DPI = 100
MIN_ZOOM = 0.05
MAX_ZOOM = 6.0


def _expand_to_tight_bbox(fig):
    """Grow `fig` in place to its tight bounding box — see module docstring.

    `_tight_bbox.adjust_bbox` rewires `fig.bbox` to a *separate* transform
    frozen at the dpi passed in (`fixed_dpi`), disconnected from
    `fig.dpi_scale_trans` — the same thing `fig.set_dpi()` updates. Call
    this once and never touch it again and you're fine (that's the
    savefig(bbox_inches="tight") use case, which always restores
    afterward). But this app changes dpi again later, for zoom — and once
    `fig.bbox` is frozen, a later `set_dpi()` changes `fig.dpi` while the
    actual renderer buffer size (which comes from `fig.bbox`, see
    get_renderer()) doesn't move at all. That desync between the widget's
    (correctly resized) pixel geometry and the renderer's (stale) buffer
    size is exactly what produces the scrambled/striped garbage — Qt asks
    to paint a region the buffer was never sized for.

    Fix: undo any adjustment left over from a previous call on this same
    figure (`fig._plotcraft_restore_bbox`) before measuring/reapplying, so
    each call starts from the figure's normal dpi_scale_trans-linked state
    and `fixed_dpi` (always `fig.dpi` at call time) never drifts out of
    sync with it. Callers must set `fig.dpi` to its FINAL value before
    calling this — see _apply_zoom, the only place dpi changes.
    """
    try:
        restore = getattr(fig, "_plotcraft_restore_bbox", None)
        if restore is not None:
            restore()
        from matplotlib import _tight_bbox
        renderer = fig._get_renderer()
        pad = matplotlib.rcParams["savefig.pad_inches"]
        bbox = fig.get_tightbbox(renderer).padded(pad, pad)
        fig._plotcraft_restore_bbox = _tight_bbox.adjust_bbox(fig, bbox, renderer, fig.dpi)
        fig.canvas.draw()
    except Exception:
        pass


def resolve_renderable(node_path, node_kind):
    """Walk up from whatever's selected to the nearest top-level plots[]/
    figures[] entry — that's the unit plotter.py actually knows how to
    render. Selecting a series highlights its parent plot/panel."""
    if node_path is None or len(node_path) < 2:
        return None, None
    top, idx = node_path[0], node_path[1]
    if top == "plots":
        return ("plots", idx), "plot"
    if top == "figures":
        return ("figures", idx), "figure"
    return None, None


class PreviewCanvas(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._doc = None
        self._current_fig = None
        self._current_fontsize_cfg = None
        self._last_rendered_path = None   # renderable_path currently on screen
        self._pending = None
        self._zoom_mode = None  # None = Fit
        self._last_zoom = 1.0   # actual numeric zoom _apply_zoom last used (incl. resolved Fit)
        self._panning = False
        self._pan_start_pos = None
        self._pan_start_scroll = (0, 0)

        self._mpl_figure_canvas = FigureCanvasQTAgg(plt.figure())
        self._toolbar = NavigationToolbar2QT(self._mpl_figure_canvas, self)

        self._zoom_combo = QComboBox()
        for label, _ in ZOOM_LEVELS:
            self._zoom_combo.addItem(label)
        self._zoom_combo.setEditable(True)
        self._zoom_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._zoom_combo.lineEdit().setValidator(QDoubleValidator(1.0, 600.0, 0, self))
        self._zoom_combo.activated.connect(self._on_zoom_changed)
        self._zoom_combo.lineEdit().returnPressed.connect(self._on_zoom_text_entered)

        self._size_label = QLabel("")
        self._size_label.setStyleSheet("color: gray;")

        self._reset_view_button = QPushButton("Reset view")
        self._reset_view_button.setToolTip("Back to Fit zoom, scrolled to top-left")
        self._reset_view_button.clicked.connect(self.reset_view)

        top_bar = QHBoxLayout()
        top_bar.addWidget(self._toolbar)
        top_bar.addStretch(1)
        top_bar.addWidget(QLabel("Zoom:"))
        top_bar.addWidget(self._zoom_combo)
        top_bar.addWidget(self._size_label)
        top_bar.addWidget(self._reset_view_button)

        self._error_label = QLabel("")
        self._error_label.setWordWrap(True)
        self._error_label.setStyleSheet(
            "background: #fff3cd; color: #664d03; padding: 6px; border: 1px solid #ffe69c;")
        self._error_label.setVisible(False)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(False)
        self._scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._scroll.setWidget(self._mpl_figure_canvas)
        self._mpl_figure_canvas.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        # Plain wheel zooms anywhere over the preview. Installed on BOTH the
        # viewport (covers the whitespace margin around a smaller-than-
        # viewport figure) AND the canvas itself — FigureCanvasQT overrides
        # wheelEvent() to emit its own scroll_event and never lets it bubble
        # to the parent, so without a filter on the canvas too, wheeling
        # over the actual rendered plot (most of the visible area) would
        # never reach us. Panning a zoomed-in figure is via the scrollbars
        # or the toolbar's pan tool, not the wheel.
        self._scroll.viewport().installEventFilter(self)
        self._mpl_figure_canvas.installEventFilter(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(top_bar)
        layout.addWidget(self._error_label)
        layout.addWidget(self._scroll, 1)

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(200)
        self._debounce.timeout.connect(self._flush_pending)

    # -- public API -----------------------------------------------------

    def set_document(self, doc):
        self._doc = doc
        self.clear()

    def clear(self):
        self._pending = None
        self._last_rendered_path = None
        self._debounce.stop()
        self._show_placeholder("Select a plot or figure to preview it.")

    def render_now(self, node_path, node_kind):
        self._debounce.stop()
        self._pending = (node_path, node_kind)
        self._flush_pending(skip_if_unchanged=True)

    def request_render(self, node_path, node_kind):
        self._pending = (node_path, node_kind)
        self._debounce.start()

    # -- rendering --------------------------------------------------------

    def _flush_pending(self, skip_if_unchanged=False):
        if self._pending is None or self._doc is None:
            return
        node_path, node_kind = self._pending
        renderable_path, renderable_kind = resolve_renderable(node_path, node_kind)
        if renderable_path is None:
            self._show_placeholder("Select a plot or figure to preview it.")
            return
        if skip_if_unchanged and renderable_path == self._last_rendered_path:
            # Selecting a sibling series/panel under the same plot/figure
            # that's already on screen changes nothing about what needs
            # rendering — a full re-render (hundreds of ms on a complex
            # multi-panel figure) would just redraw the exact same thing.
            # Edits (request_render) never take this path, so real changes
            # to the CURRENTLY shown figure still always re-render.
            return
        self._do_render(renderable_path, renderable_kind)

    def _do_render(self, renderable_path, renderable_kind):
        self._last_rendered_path = renderable_path
        cfg = self._doc.render_copy(renderable_path)   # deep copy — see module docstring
        plotter._apply_latex_settings(self._doc.doc)

        old_data_dir = plotter.DATA_DIR
        plotter.set_data_dir(self._doc.data_dir)
        try:
            if renderable_kind == "plot":
                fig = plotter.render_plot(cfg)
            else:
                fig = plotter.render_figure(cfg)
        except Exception as exc:
            self._show_error(f"{type(exc).__name__}: {exc}")
            return
        finally:
            plotter.set_data_dir(old_data_dir)

        self._error_label.setVisible(False)
        self._show_figure(fig, cfg.get("fontsize"))

    def _show_figure(self, fig, fontsize_cfg):
        if self._current_fig is not None and self._current_fig is not fig:
            plt.close(self._current_fig)
        self._current_fig = fig
        self._current_fontsize_cfg = fontsize_cfg
        fig.set_facecolor("white")
        fig.set_canvas(self._mpl_figure_canvas)
        self._mpl_figure_canvas.figure = fig
        # FigureCanvasBase.callbacks is a *property* — `property(lambda
        # self: self.figure._canvas_callbacks)` — so the event registry
        # toolbar clicks/drags fire through actually lives on the Figure,
        # not the canvas widget. NavigationToolbar2QT.__init__ connects its
        # press/release/drag handlers once, against whatever figure was
        # attached at construction time (our placeholder). Every render
        # here swaps in a brand-new Figure — render_plot/render_figure
        # always build one from scratch — which has its own, separate,
        # freshly-created registry the toolbar was never connected to. Left
        # alone, that means real mouse events for Pan/Zoom-rect/drag-to-
        # coordinates never reach the toolbar at all for anything actually
        # rendered — it looks present but silently does nothing, on any
        # figure except the one that existed when it was constructed.
        # _rewire_toolbar_events reconnects the same three handlers
        # NavigationToolbar2.__init__ makes, against the new figure's
        # registry; the old connections die naturally with the old figure
        # (nothing else references its registry once it's closed below),
        # no explicit disconnect needed.
        self._rewire_toolbar_events()
        # Home/Back/Forward are driven entirely by the toolbar's own
        # _nav_stack, which it never updates on its own just because
        # canvas.figure changed — left alone the stack stays permanently
        # empty (or references a stale figure's axes) and those three
        # buttons silently do nothing either. update() clears out the old
        # figure's now-defunct entries; push_current() (below, after
        # _apply_zoom has settled the final axes layout) records this
        # figure's initial view as the "home" position.
        self._toolbar.update()
        # _apply_zoom owns the draw/expand/resize sequence — dpi has to be
        # set to its final (zoom-dependent) value before the tight-bbox
        # expansion runs, or it freezes the renderer buffer at the wrong
        # size. See _expand_to_tight_bbox's docstring.
        self._apply_zoom()
        self._toolbar.push_current()

    def _rewire_toolbar_events(self):
        tb = self._toolbar
        canvas = self._mpl_figure_canvas
        tb._id_press = canvas.mpl_connect("button_press_event", tb._zoom_pan_handler)
        tb._id_release = canvas.mpl_connect("button_release_event", tb._zoom_pan_handler)
        tb._id_drag = canvas.mpl_connect("motion_notify_event", tb.mouse_move)

    def _show_error(self, message):
        self._error_label.setText(f"⚠ {message}")
        self._error_label.setVisible(True)
        # Keep the last good figure on screen — do not touch _current_fig/canvas.

    def _show_placeholder(self, message):
        if self._current_fig is not None:
            plt.close(self._current_fig)
        self._current_fig = None
        self._error_label.setVisible(False)
        blank = plt.figure(figsize=(3, 2))
        blank.text(0.5, 0.5, message, ha="center", va="center", color="gray", wrap=True)
        self._show_figure(blank, None)

    # -- zoom / true size ---------------------------------------------------

    def eventFilter(self, obj, event):
        if obj in (self._scroll.viewport(), self._mpl_figure_canvas):
            etype = event.type()
            if etype == QEvent.Type.Wheel:
                self._wheel_zoom(event)
                return True
            if etype == QEvent.Type.MouseButtonPress:
                if self._start_pan(event):
                    return True
            elif etype == QEvent.Type.MouseMove:
                if self._panning:
                    self._do_pan(event)
                    return True
            elif etype == QEvent.Type.MouseButtonRelease:
                if self._panning:
                    self._end_pan()
                    return True
        return super().eventFilter(obj, event)

    def _start_pan(self, event):
        # Only take over a plain left-drag when neither of the toolbar's own
        # Pan or Zoom-rect tools is active — those already use left-drag on
        # the canvas for data-space panning/zoom-rectangle, and stealing the
        # event here would break them.
        if (event.button() != Qt.MouseButton.LeftButton
                or self._toolbar.mode != _Mode.NONE
                or self._current_fig is None):
            return False
        self._panning = True
        self._pan_start_pos = event.globalPosition().toPoint()
        self._pan_start_scroll = (self._scroll.horizontalScrollBar().value(),
                                   self._scroll.verticalScrollBar().value())
        self._mpl_figure_canvas.setCursor(Qt.CursorShape.ClosedHandCursor)
        self._scroll.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
        return True

    def _do_pan(self, event):
        delta = event.globalPosition().toPoint() - self._pan_start_pos
        start_h, start_v = self._pan_start_scroll
        self._scroll.horizontalScrollBar().setValue(start_h - delta.x())
        self._scroll.verticalScrollBar().setValue(start_v - delta.y())

    def _end_pan(self):
        self._panning = False
        self._pan_start_pos = None
        self._mpl_figure_canvas.unsetCursor()
        self._scroll.viewport().unsetCursor()

    def reset_view(self):
        self._zoom_mode = None
        self._zoom_combo.blockSignals(True)
        self._zoom_combo.setCurrentIndex(0)
        self._zoom_combo.blockSignals(False)
        self._apply_zoom()
        self._scroll.horizontalScrollBar().setValue(0)
        self._scroll.verticalScrollBar().setValue(0)

    def _wheel_zoom(self, event):
        if self._current_fig is None:
            return
        delta = event.angleDelta().y()
        if delta == 0:
            return
        step = 1.0 + settings.wheel_zoom_step_pct() / 100.0
        factor = step if delta > 0 else (1 / step)
        new_zoom = max(MIN_ZOOM, min(self._last_zoom * factor, MAX_ZOOM))

        # Keep the point under the cursor stationary rather than re-centering
        # on every notch, which reads as jumpy at anything but tiny figures.
        # event.position() is relative to whichever widget received the
        # event (viewport or canvas — see the installEventFilter comment
        # above), so go through global coordinates to get a position that's
        # always relative to the viewport, regardless of the source.
        hbar, vbar = self._scroll.horizontalScrollBar(), self._scroll.verticalScrollBar()
        pos = self._scroll.viewport().mapFromGlobal(event.globalPosition().toPoint())
        anchor_x = hbar.value() + pos.x()
        anchor_y = vbar.value() + pos.y()
        ratio = new_zoom / self._last_zoom

        self._zoom_mode = new_zoom
        self._apply_zoom()

        hbar.setValue(round(anchor_x * ratio - pos.x()))
        vbar.setValue(round(anchor_y * ratio - pos.y()))

    def _on_zoom_changed(self, index):
        self._zoom_mode = ZOOM_LEVELS[index][1]
        self._apply_zoom()

    def _on_zoom_text_entered(self):
        text = self._zoom_combo.currentText().strip().rstrip("%")
        try:
            pct = float(text)
        except ValueError:
            self._sync_zoom_combo_text()
            return
        self._zoom_mode = max(MIN_ZOOM, min(pct / 100.0, MAX_ZOOM))
        self._apply_zoom()

    def _sync_zoom_combo_text(self):
        self._zoom_combo.blockSignals(True)
        self._zoom_combo.setCurrentText(f"{self._last_zoom * 100:.0f}%")
        self._zoom_combo.blockSignals(False)

    def _apply_zoom(self):
        if self._current_fig is None:
            return
        fig = self._current_fig

        with matplotlib.rc_context(plotter._fontsize_rcparams(self._current_fontsize_cfg)):
            # Undo any tight-bbox adjustment left over from a previous zoom
            # pass on this same figure, so both the Fit-mode measurement
            # below and _expand_to_tight_bbox start from the figure's
            # normal, dpi_scale_trans-linked state rather than compounding
            # on top of the last zoom's adjustment. See
            # _expand_to_tight_bbox's docstring for the full story.
            restore = getattr(fig, "_plotcraft_restore_bbox", None)
            if restore is not None:
                restore()
                fig._plotcraft_restore_bbox = None

            w_in, h_in = fig.get_size_inches()   # nominal (pre-tight-bbox) size
            zoom = self._zoom_mode
            if zoom is None:  # Fit
                viewport = self._scroll.viewport().size()
                zoom = min(viewport.width() / (w_in * BASE_DPI),
                           viewport.height() / (h_in * BASE_DPI), 1.0)
                zoom = max(zoom, 0.05)
            dpi = BASE_DPI * zoom

            # dpi must be set to its FINAL value before _expand_to_tight_bbox
            # runs, since that's what freezes the renderer buffer size.
            fig.set_dpi(dpi)
            self._mpl_figure_canvas.draw()
            _expand_to_tight_bbox(fig)   # ends with its own draw() at the final size/position

            w_in, h_in = fig.get_size_inches()   # now the tight, expanded size
            w_px, h_px = int(w_in * dpi), int(h_in * dpi)
            # No draw() here: get_renderer()/get_width_height() are driven
            # purely by fig.bbox (dpi * size_inches) — never by the Qt
            # widget's geometry — so setFixedSize() cannot invalidate the
            # renderer _expand_to_tight_bbox just built. A third full draw
            # of a complex figure (ticks, legends, text layout) measurably
            # added tens to hundreds of ms per click on multi-panel figures
            # for zero visual difference. Qt's own resize-triggered
            # draw_idle() still repaints the widget once the resize is
            # actually processed.
            self._mpl_figure_canvas.setFixedSize(w_px, h_px)

        self._last_zoom = zoom
        self._sync_zoom_combo_text()
        self._size_label.setText(
            f"{w_in:.2f}×{h_in:.2f} in  ·  {zoom * 100:.0f}%")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._zoom_mode is None:
            self._apply_zoom()
