"""Regression tests for lab_data_plotter.

Covers the four bugs fixed alongside the Line/Bar toggle refinement:

  1. ScrollableFrame hijacked the mouse wheel application-wide.
  2. A degenerate dataset put "nan" into the plot-range fields, which later
     crashed Axes.set_ylim.
  3. Per-series styles leaked from one loaded dataset into the next.
  4. update_plot / save_figure mutated the process-wide matplotlib font size
     and never restored it.

Run from the project root:

    python3 -m unittest -v test_lab_data_plotter
"""

import math
import os
import tkinter as tk
import unittest
from unittest import mock

import matplotlib
import numpy as np

import lab_data_plotter as m

TESTDATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "testdata")

# A single hidden Tk interpreter for the whole module — creating many Tk()
# roots in one process is unstable.
_ROOT = None


def setUpModule():
    global _ROOT
    try:
        _ROOT = tk.Tk()
    except tk.TclError as exc:  # headless environment without a display
        raise unittest.SkipTest(f"Tk is unavailable: {exc}")
    _ROOT.withdraw()


def tearDownModule():
    global _ROOT
    if _ROOT is not None:
        _ROOT.destroy()
        _ROOT = None


# ---------------------------------------------------------------------------
# Bug 2 — _finite_float helper (pure function)
# ---------------------------------------------------------------------------
class FiniteFloatTests(unittest.TestCase):
    def test_accepts_real_numbers(self):
        self.assertEqual(m._finite_float("3.5", 0.0), 3.5)
        self.assertEqual(m._finite_float(2, 9.0), 2.0)
        self.assertEqual(m._finite_float(-1.25, 9.0), -1.25)

    def test_rejects_non_finite(self):
        self.assertEqual(m._finite_float(float("nan"), 7.0), 7.0)
        self.assertEqual(m._finite_float(float("inf"), 7.0), 7.0)
        self.assertEqual(m._finite_float(float("-inf"), 7.0), 7.0)
        self.assertEqual(m._finite_float("nan", 7.0), 7.0)

    def test_rejects_unparseable(self):
        self.assertEqual(m._finite_float("abc", 1.0), 1.0)
        self.assertEqual(m._finite_float(None, 1.0), 1.0)


class AppTestCase(unittest.TestCase):
    """Base class that builds a hidden LabDataPlotterApp per test."""

    def setUp(self):
        self.win = tk.Toplevel(_ROOT)
        self.win.withdraw()
        self.app = m.LabDataPlotterApp(self.win)

    def tearDown(self):
        self.win.destroy()

    def open(self, *names):
        paths = tuple(os.path.join(TESTDATA, n) for n in names)
        with mock.patch.object(
            m.filedialog, "askopenfilenames", return_value=paths
        ):
            self.app.open_files()
        self.win.update_idletasks()


# ---------------------------------------------------------------------------
# Bug 2 — NaN never reaches the range fields or set_ylim
# ---------------------------------------------------------------------------
class PlotRangeTests(AppTestCase):
    def _assert_all_ranges_finite(self):
        for key in ("x_min", "x_max", "y_min", "y_max"):
            raw = self.app.range_vars[key].get()
            self.assertNotIn("nan", raw.lower(), f"{key} = {raw!r}")
            self.assertTrue(math.isfinite(float(raw)), f"{key} = {raw!r}")

    def test_constant_dataset_keeps_ranges_finite(self):
        # No Y column is auto-detected for all-constant data.
        self.open("constant_signal.csv")
        self.assertEqual(self.app._selected_y_cols(), [])
        self._assert_all_ranges_finite()

    def test_constant_dataset_can_enable_range_without_crashing(self):
        self.open("constant_signal.csv")
        self.app.use_range_var.set(True)
        self.app.update_plot()  # must not raise ValueError from set_ylim
        self.win.update_idletasks()

    def test_text_y_column_reset_range_stays_finite(self):
        self.open("categories.csv")
        cols = list(self.app.df.columns)
        idx = cols.index("category")  # non-numeric column
        self.app.y_listbox.selection_clear(0, "end")
        self.app.y_listbox.selection_set(idx)
        self.app._on_y_selection_changed()
        self.app.reset_range()
        self._assert_all_ranges_finite()

    def test_get_range_sanitises_manual_nan_entry(self):
        self.open("experiment.csv")
        self.app.range_vars["y_max"].set("nan")
        for value in self.app._get_range():
            self.assertTrue(math.isfinite(value))
        self.app.use_range_var.set(True)
        self.app.update_plot()  # must not raise
        self.win.update_idletasks()


# ---------------------------------------------------------------------------
# Bug 3 — series styles do not survive a new file load
# ---------------------------------------------------------------------------
class SeriesStyleLeakTests(AppTestCase):
    def test_reload_same_columns_resets_style(self):
        self.open("experiment.csv")
        style = self.app._series_style("signal_a")
        style["color"] = "#ff0000"
        style["name"] = "Custom Label"

        self.open("experiment_run2.csv")  # identical column names

        fresh = self.app._series_style("signal_a")
        self.assertIsNone(fresh["color"])
        self.assertEqual(fresh["name"], "")

    def test_reload_different_columns_drops_old_keys(self):
        self.open("experiment.csv")
        self.app._series_style("signal_b")["color"] = "#00ff00"

        self.open("assay.csv")

        self.assertNotIn("signal_b", self.app.series_styles)

    def test_unloading_last_file_clears_styles(self):
        self.open("experiment.csv")
        self.app._series_style("signal_a")["color"] = "#0000ff"
        self.app.unload_file(self.app.files[0])
        self.assertEqual(self.app.series_styles, {})


# ---------------------------------------------------------------------------
# Bug 4 — matplotlib's global font size is left untouched
# ---------------------------------------------------------------------------
class FontRcParamTests(AppTestCase):
    def test_update_plot_restores_global_font_size(self):
        self.open("experiment.csv")
        before = matplotlib.rcParams["font.size"]
        self.app.figure_vars["font_size"].set("22")
        self.app.update_plot()
        self.win.update_idletasks()
        self.assertEqual(matplotlib.rcParams["font.size"], before)

    def test_save_figure_restores_global_font_size(self):
        self.open("experiment.csv")
        before = matplotlib.rcParams["font.size"]
        out = os.path.join(TESTDATA, "_tmp_test_figure.png")
        self.addCleanup(lambda: os.path.exists(out) and os.remove(out))
        self.app.figure_vars["font_size"].set("18")
        with mock.patch.object(
            m.filedialog, "asksaveasfilename", return_value=out
        ):
            self.app.save_figure()
        self.assertTrue(os.path.exists(out))
        self.assertEqual(matplotlib.rcParams["font.size"], before)


# ---------------------------------------------------------------------------
# Bug 5 — smoothing a short series (e.g. messy data after dropping invalid
# rows) must not blank the plot
# ---------------------------------------------------------------------------
class SmoothingTests(AppTestCase):
    def _first_line_finite_count(self):
        ax = self.app.figure.axes[0]
        return max(
            int(np.isfinite(np.asarray(line.get_ydata(), dtype=float)).sum())
            for line in ax.get_lines()
        )

    def test_smoothing_messy_short_series_stays_visible(self):
        # messy.csv drops to ~5 usable points once invalid rows are removed,
        # which a plain rolling(5) turned into a single non-NaN sample.
        self.open("messy.csv")
        self.app.smooth_var.set(True)
        self.app.update_plot()
        self.win.update_idletasks()

        records = self.app._plotted_data
        self.assertTrue(records)
        for rec in records:
            y = np.asarray(rec["y"], dtype=float)
            self.assertTrue(
                np.isfinite(y).all(),
                f"{rec['y_col']} still has NaNs after smoothing: {y}",
            )
        self.assertGreaterEqual(self._first_line_finite_count(), 2)

    def test_smoothing_changes_values_but_keeps_length(self):
        self.open("experiment.csv")
        self.app.update_plot()
        raw = np.asarray(self.app._plotted_data[0]["y"], dtype=float).copy()

        self.app.smooth_var.set(True)
        self.app.update_plot()
        smoothed = np.asarray(self.app._plotted_data[0]["y"], dtype=float)

        self.assertEqual(len(raw), len(smoothed))
        self.assertTrue(np.isfinite(smoothed).all())
        self.assertFalse(np.allclose(raw, smoothed))


# ---------------------------------------------------------------------------
# Bug 1 — the controls-panel wheel handler only acts over the panel
# ---------------------------------------------------------------------------
class ScrollableFrameWheelTests(unittest.TestCase):
    def setUp(self):
        self.win = tk.Toplevel(_ROOT)
        self.win.withdraw()
        self.frame = m.ScrollableFrame(self.win, width=200)
        self.frame.pack(fill="both", expand=True)
        self.panel_canvas = next(
            w for w in self.frame.winfo_children() if isinstance(w, tk.Canvas)
        )
        # Record panel-scroll requests instead of depending on real geometry.
        self.scroll_calls = []
        self.panel_canvas.yview_scroll = lambda *a, **k: self.scroll_calls.append(a)

        self.outside = tk.Frame(self.win)  # stands in for the figure area
        self.outside.pack()
        self.inside_label = tk.Label(self.frame.inner, text="row")
        self.inside_label.pack()
        self.inside_listbox = tk.Listbox(self.frame.inner, height=3)
        for i in range(20):
            self.inside_listbox.insert("end", f"item {i}")
        self.inside_listbox.pack()
        self.win.update_idletasks()

    def tearDown(self):
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.panel_canvas.unbind_all(seq)
        self.win.destroy()

    def _panel_scrolled_from(self, widget):
        self.scroll_calls.clear()
        widget.event_generate("<MouseWheel>", delta=-120, x=1, y=1, when="now")
        return bool(self.scroll_calls)

    def test_wheel_over_panel_content_scrolls_panel(self):
        self.assertTrue(self._panel_scrolled_from(self.inside_label))

    def test_wheel_outside_panel_does_not_scroll_panel(self):
        self.assertFalse(self._panel_scrolled_from(self.outside))

    def test_wheel_over_inner_listbox_does_not_scroll_panel(self):
        self.assertFalse(self._panel_scrolled_from(self.inside_listbox))


if __name__ == "__main__":
    unittest.main()
