"""Lab Data Plotter — native desktop version.

A Tkinter port of the original Streamlit app. Loads CSV/JSON lab data,
auto-detects X/Y columns, and plots with matplotlib embedded in the window.

Developed by Cristian J. Aviles-Martin Ph.D.
"""

import os
import sys

# --- Local package support (for portable setup) ---
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "libs"))

import tkinter as tk
from tkinter import colorchooser, filedialog, ttk

import matplotlib

matplotlib.use("TkAgg")

import numpy as np
import pandas as pd
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure


# -------------------------
# AUTO-DETECTION FUNCTIONS
# -------------------------
def detect_x_column(df):
    cols = {col.lower(): col for col in df.columns}

    for key in ["time", "wavelength", "x"]:
        if key in cols:
            return cols[key]

    for col in df.select_dtypes(include=[np.number]).columns:
        series = df[col].dropna()
        # A constant (or empty) column is technically monotonic but is
        # never a meaningful axis, so require at least two distinct values.
        if series.nunique() > 1 and series.is_monotonic_increasing:
            return col

    numeric_cols = df.select_dtypes(include=[np.number]).columns
    if len(numeric_cols) > 0:
        return numeric_cols[0]

    return df.columns[0]


def detect_y_columns(df, x_col):
    y_cols = []

    for col in df.select_dtypes(include=[np.number]).columns:
        if col == x_col:
            continue

        series = df[col].dropna()

        if series.nunique() <= 1:
            continue

        if np.isclose(series.std(), 0):
            continue

        y_cols.append(col)

    return y_cols


def resource_path(name):
    """Path to a bundled resource, both in source checkouts and in
    PyInstaller bundles (where data files land in sys._MEIPASS)."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def load_dataframe(path):
    if path.lower().endswith(".csv"):
        # utf-8-sig strips Excel's BOM; skipinitialspace handles "a, b" headers
        df = pd.read_csv(path, encoding="utf-8-sig", skipinitialspace=True)
    else:
        df = pd.read_json(path)
    # Invisible whitespace in headers makes identically-formatted files
    # mismatch the selected columns, so normalize names on load.
    df.columns = [str(c).strip() for c in df.columns]
    return df


class ScrollableFrame(ttk.Frame):
    """A vertical scrollable container for the controls panel."""

    def __init__(self, parent, width=340):
        super().__init__(parent)
        canvas = tk.Canvas(self, width=width, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self.inner = ttk.Frame(canvas)

        self.inner.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=self.inner, anchor="nw", width=width)
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        def _on_mousewheel(event):
            if event.num == 4 or event.delta > 0:
                canvas.yview_scroll(-1, "units")
            elif event.num == 5 or event.delta < 0:
                canvas.yview_scroll(1, "units")

        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            canvas.bind_all(seq, _on_mousewheel)


class LabDataPlotterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Lab Data Plotter")
        self.root.geometry("1200x800")

        icon_path = resource_path("app.ico")
        if os.path.exists(icon_path):
            try:
                self.root.iconbitmap(icon_path)
            except tk.TclError:
                pass  # .ico window icons are Windows-only

        # Each loaded file: {"name", "df", "enabled_var", "display_var"}
        self.files = []
        self.df = None  # first valid file, drives column choices

        # Per-column style overrides: {"name", "color", "linestyle", "width", "marker"}
        self.series_styles = {}

        self._redraw_job = None
        self._loading_style = False

        # Data exactly as drawn by the last update_plot (after range limiting,
        # smoothing, normalization, and offset) — the source for CSV export.
        self._plotted_data = []
        self._plotted_x_col = None

        self._build_ui()

    # -------------------------
    # UI CONSTRUCTION
    # -------------------------
    def _build_ui(self):
        # Left: controls (scrollable). Right: figure.
        left = ScrollableFrame(self.root, width=340)
        left.pack(side="left", fill="y", padx=(8, 0), pady=8)
        controls = left.inner

        right = ttk.Frame(self.root)
        right.pack(side="right", fill="both", expand=True, padx=8, pady=8)

        ttk.Label(controls, text="Lab Data Plotter", font=("TkDefaultFont", 14, "bold")).pack(
            anchor="w", pady=(0, 8)
        )

        ttk.Button(controls, text="Open CSV / JSON files…", command=self.open_files).pack(
            fill="x", pady=(0, 8)
        )

        self.files_label = ttk.Label(controls, text="No files loaded", wraplength=320)
        self.files_label.pack(anchor="w", pady=(0, 8))

        # Loaded files: include/exclude toggle + editable legend name per file
        self.files_frame = ttk.LabelFrame(controls, text="Loaded Files")
        self.files_frame.pack(fill="x", pady=(0, 8))
        ttk.Label(
            self.files_frame, text="Open files to list them here.", foreground="gray"
        ).pack(anchor="w", padx=4, pady=2)

        # Data preview
        preview_frame = ttk.LabelFrame(controls, text="Data Preview")
        preview_frame.pack(fill="x", pady=(0, 8))
        self.preview = ttk.Treeview(preview_frame, show="headings", height=5)
        self.preview.pack(side="left", fill="x", expand=True)
        preview_scroll = ttk.Scrollbar(
            preview_frame, orient="horizontal", command=self.preview.xview
        )
        # Horizontal scrollbar goes under the tree
        self.preview.configure(xscrollcommand=preview_scroll.set)
        preview_scroll.pack(side="bottom", fill="x")

        self.autodetect_label = ttk.Label(controls, text="", wraplength=320, foreground="#1a6fb5")
        self.autodetect_label.pack(anchor="w", pady=(0, 8))

        # Axis selection
        axis_frame = ttk.LabelFrame(controls, text="Axes")
        axis_frame.pack(fill="x", pady=(0, 8))

        ttk.Label(axis_frame, text="X-axis").pack(anchor="w", padx=4)
        self.x_var = tk.StringVar()
        self.x_combo = ttk.Combobox(axis_frame, textvariable=self.x_var, state="readonly")
        self.x_combo.pack(fill="x", padx=4, pady=(0, 4))
        self.x_combo.bind("<<ComboboxSelected>>", lambda e: self.schedule_redraw())

        ttk.Label(axis_frame, text="Y-axis (select one or more)").pack(anchor="w", padx=4)
        self.y_listbox = tk.Listbox(axis_frame, selectmode="multiple", height=6, exportselection=False)
        self.y_listbox.pack(fill="x", padx=4, pady=(0, 4))
        self.y_listbox.bind("<<ListboxSelect>>", self._on_y_selection_changed)

        # Series styles: per-column name, color, line style, width, marker
        style_frame = ttk.LabelFrame(controls, text="Series Styles")
        style_frame.pack(fill="x", pady=(0, 8))

        ttk.Label(style_frame, text="Series").pack(anchor="w", padx=4)
        self.style_series_var = tk.StringVar()
        self.style_series_combo = ttk.Combobox(
            style_frame, textvariable=self.style_series_var, state="readonly"
        )
        self.style_series_combo.pack(fill="x", padx=4, pady=(0, 4))
        self.style_series_combo.bind("<<ComboboxSelected>>", lambda e: self._load_style_editor())

        style_grid = ttk.Frame(style_frame)
        style_grid.pack(fill="x", padx=4, pady=(0, 4))
        style_grid.columnconfigure(1, weight=1)

        ttk.Label(style_grid, text="Legend name").grid(row=0, column=0, sticky="w")
        self.style_name_var = tk.StringVar()
        name_entry = ttk.Entry(style_grid, textvariable=self.style_name_var)
        name_entry.grid(row=0, column=1, sticky="ew", padx=(4, 0), pady=1)
        name_entry.bind("<Return>", lambda e: self._apply_style_editor())
        name_entry.bind("<FocusOut>", lambda e: self._apply_style_editor())

        ttk.Label(style_grid, text="Color").grid(row=1, column=0, sticky="w")
        color_row = ttk.Frame(style_grid)
        color_row.grid(row=1, column=1, sticky="ew", padx=(4, 0), pady=1)
        self.color_swatch = tk.Label(color_row, text="auto", width=8, relief="groove")
        self.color_swatch.pack(side="left")
        ttk.Button(color_row, text="Pick…", width=6, command=self._pick_series_color).pack(
            side="left", padx=(4, 0)
        )
        ttk.Button(color_row, text="Auto", width=6, command=self._reset_series_color).pack(
            side="left", padx=(4, 0)
        )

        ttk.Label(style_grid, text="Line style").grid(row=2, column=0, sticky="w")
        self.style_linestyle_var = tk.StringVar(value="solid")
        linestyle_combo = ttk.Combobox(
            style_grid, textvariable=self.style_linestyle_var, state="readonly",
            values=["solid", "dashed", "dotted", "dashdot"],
        )
        linestyle_combo.grid(row=2, column=1, sticky="ew", padx=(4, 0), pady=1)
        linestyle_combo.bind("<<ComboboxSelected>>", lambda e: self._apply_style_editor())

        ttk.Label(style_grid, text="Line width").grid(row=3, column=0, sticky="w")
        self.style_width_var = tk.StringVar(value="1.5")
        width_spin = ttk.Spinbox(
            style_grid, textvariable=self.style_width_var, from_=0.5, to=10.0,
            increment=0.5, command=self._apply_style_editor,
        )
        width_spin.grid(row=3, column=1, sticky="ew", padx=(4, 0), pady=1)
        width_spin.bind("<Return>", lambda e: self._apply_style_editor())
        width_spin.bind("<FocusOut>", lambda e: self._apply_style_editor())

        ttk.Label(style_grid, text="Marker").grid(row=4, column=0, sticky="w")
        self.style_marker_var = tk.StringVar(value="none")
        marker_combo = ttk.Combobox(
            style_grid, textvariable=self.style_marker_var, state="readonly",
            values=["none", "o", "s", "^", "v", "D", "x", "+", "*"],
        )
        marker_combo.grid(row=4, column=1, sticky="ew", padx=(4, 0), pady=1)
        marker_combo.bind("<<ComboboxSelected>>", lambda e: self._apply_style_editor())

        # Plot mode
        mode_frame = ttk.LabelFrame(controls, text="Plot Mode")
        mode_frame.pack(fill="x", pady=(0, 8))
        self.mode_var = tk.StringVar(value="Overlay")
        for mode in ("Overlay", "Multi-panel"):
            ttk.Radiobutton(
                mode_frame, text=mode, value=mode, variable=self.mode_var,
                command=self.schedule_redraw,
            ).pack(anchor="w", padx=4)

        # Options
        options_frame = ttk.LabelFrame(controls, text="Options")
        options_frame.pack(fill="x", pady=(0, 8))

        self.smooth_var = tk.BooleanVar(value=False)
        self.normalize_var = tk.BooleanVar(value=False)
        self.include_filename_var = tk.BooleanVar(value=False)

        ttk.Checkbutton(
            options_frame, text="Apply smoothing (rolling mean)",
            variable=self.smooth_var, command=self.schedule_redraw,
        ).pack(anchor="w", padx=4)
        ttk.Checkbutton(
            options_frame, text="Normalize signal",
            variable=self.normalize_var, command=self.schedule_redraw,
        ).pack(anchor="w", padx=4)
        ttk.Checkbutton(
            options_frame, text="Include filename in legend",
            variable=self.include_filename_var, command=self.schedule_redraw,
        ).pack(anchor="w", padx=4)

        # Range controls
        range_frame = ttk.LabelFrame(controls, text="Plot Range")
        range_frame.pack(fill="x", pady=(0, 8))

        self.use_range_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            range_frame, text="Limit plot range",
            variable=self.use_range_var, command=self.schedule_redraw,
        ).pack(anchor="w", padx=4)

        grid = ttk.Frame(range_frame)
        grid.pack(fill="x", padx=4, pady=(0, 4))

        self.range_vars = {}
        for row, (key, text) in enumerate(
            [("x_min", "X min"), ("x_max", "X max"), ("y_min", "Y min"), ("y_max", "Y max")]
        ):
            ttk.Label(grid, text=text).grid(row=row, column=0, sticky="w")
            var = tk.StringVar(value="0")
            entry = ttk.Entry(grid, textvariable=var, width=14)
            entry.grid(row=row, column=1, sticky="ew", padx=(4, 0), pady=1)
            entry.bind("<Return>", lambda e: self.schedule_redraw())
            entry.bind("<FocusOut>", lambda e: self.schedule_redraw())
            self.range_vars[key] = var
        grid.columnconfigure(1, weight=1)

        ttk.Button(range_frame, text="🔄 Reset to Full Range", command=self.reset_range).pack(
            fill="x", padx=4, pady=(0, 4)
        )

        # Offset (overlay only)
        offset_frame = ttk.LabelFrame(controls, text="Vertical Offset (overlay only)")
        offset_frame.pack(fill="x", pady=(0, 8))

        self.use_offset_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            offset_frame, text="Apply vertical offset",
            variable=self.use_offset_var, command=self.schedule_redraw,
        ).pack(anchor="w", padx=4)

        offset_row = ttk.Frame(offset_frame)
        offset_row.pack(fill="x", padx=4, pady=(0, 4))
        ttk.Label(offset_row, text="Offset amount").pack(side="left")
        self.offset_var = tk.StringVar(value="0.0")
        offset_spin = ttk.Spinbox(
            offset_row, textvariable=self.offset_var, from_=0.0, to=1e9,
            increment=0.05, width=10, command=self.schedule_redraw,
        )
        offset_spin.pack(side="right")
        offset_spin.bind("<Return>", lambda e: self.schedule_redraw())
        offset_spin.bind("<FocusOut>", lambda e: self.schedule_redraw())

        # Labels
        labels_frame = ttk.LabelFrame(controls, text="📝 Customize Plot Labels")
        labels_frame.pack(fill="x", pady=(0, 8))

        self.label_vars = {}
        for key, text in [
            ("title", "Plot Title (optional)"),
            ("x_label", "X-axis Label"),
            ("x_unit", "X-axis Units"),
            ("y_label", "Y-axis Label"),
            ("y_unit", "Y-axis Units"),
        ]:
            ttk.Label(labels_frame, text=text).pack(anchor="w", padx=4)
            var = tk.StringVar()
            entry = ttk.Entry(labels_frame, textvariable=var)
            entry.pack(fill="x", padx=4, pady=(0, 4))
            entry.bind("<Return>", lambda e: self.schedule_redraw())
            entry.bind("<FocusOut>", lambda e: self.schedule_redraw())
            self.label_vars[key] = var

        # Figure options for publication-quality export
        figure_frame = ttk.LabelFrame(controls, text="Figure Options (export)")
        figure_frame.pack(fill="x", pady=(0, 8))

        figure_grid = ttk.Frame(figure_frame)
        figure_grid.pack(fill="x", padx=4, pady=(2, 4))
        figure_grid.columnconfigure(1, weight=1)

        self.figure_vars = {}
        for row, (key, text, default, lo, hi, step) in enumerate([
            ("fig_width", "Width (inches)", "6.0", 1.0, 30.0, 0.5),
            ("fig_height", "Height (inches)", "4.0", 1.0, 30.0, 0.5),
            ("font_size", "Font size (pt)", "10", 4, 32, 1),
            ("dpi", "Export DPI", "600", 50, 1200, 50),
        ]):
            ttk.Label(figure_grid, text=text).grid(row=row, column=0, sticky="w")
            var = tk.StringVar(value=default)
            spin = ttk.Spinbox(
                figure_grid, textvariable=var, from_=lo, to=hi, increment=step,
                width=10, command=self.schedule_redraw,
            )
            spin.grid(row=row, column=1, sticky="ew", padx=(4, 0), pady=1)
            spin.bind("<Return>", lambda e: self.schedule_redraw())
            spin.bind("<FocusOut>", lambda e: self.schedule_redraw())
            self.figure_vars[key] = var

        # Actions
        ttk.Button(controls, text="Update Plot", command=self.update_plot).pack(
            fill="x", pady=(0, 4)
        )
        ttk.Button(controls, text="💾 Save Figure…", command=self.save_figure).pack(
            fill="x", pady=(0, 4)
        )
        ttk.Button(controls, text="📄 Export Plotted Data…", command=self.export_data).pack(
            fill="x", pady=(0, 8)
        )

        # Messages log (replaces st.warning / st.error)
        log_frame = ttk.LabelFrame(controls, text="Messages")
        log_frame.pack(fill="both", pady=(0, 8))
        self.log = tk.Text(log_frame, height=6, wrap="word", state="disabled")
        self.log.pack(fill="both", expand=True, padx=4, pady=4)

        ttk.Label(
            controls, text="Developed by Cristian J. Aviles-Martin Ph.D.",
            foreground="gray",
        ).pack(anchor="w", pady=(0, 8))

        # Figure area
        self.figure = Figure(figsize=(6, 4), dpi=100)
        self.canvas = FigureCanvasTkAgg(self.figure, master=right)
        toolbar = NavigationToolbar2Tk(self.canvas, right)
        toolbar.update()
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

    # -------------------------
    # LOGGING
    # -------------------------
    def clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def log_message(self, message):
        self.log.configure(state="normal")
        self.log.insert("end", message + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    # -------------------------
    # FILE LOADING
    # -------------------------
    def open_files(self):
        paths = filedialog.askopenfilenames(
            title="Upload CSV or JSON files",
            filetypes=[("Data files", "*.csv *.json"), ("CSV", "*.csv"), ("JSON", "*.json")],
        )
        if not paths:
            return

        self.clear_log()
        self.files = []
        for path in paths:
            name = os.path.basename(path)
            try:
                df = load_dataframe(path)
            except Exception as e:
                self.log_message(f"{name}: {e}")
                continue
            self.files.append({
                "name": name,
                "df": df,
                "enabled_var": tk.BooleanVar(value=True),
                "display_var": tk.StringVar(value=name),
            })

        # First valid (non-empty) file drives column choices
        self.df = None
        for f in self.files:
            if not f["df"].empty:
                self.df = f["df"]
                break

        self._rebuild_files_panel()

        if self.df is None:
            self.files_label.config(text="No valid files could be loaded.")
            self.log_message("No valid files could be loaded.")
            return

        self.files_label.config(text=f"{len(self.files)} file(s) loaded")
        self._populate_controls()
        self.update_plot()

    def _rebuild_files_panel(self):
        for child in self.files_frame.winfo_children():
            child.destroy()

        if not self.files:
            ttk.Label(
                self.files_frame, text="Open files to list them here.", foreground="gray"
            ).pack(anchor="w", padx=4, pady=2)
            return

        for f in self.files:
            row = ttk.Frame(self.files_frame)
            row.pack(fill="x", padx=4, pady=1)
            ttk.Checkbutton(
                row, variable=f["enabled_var"], command=self.schedule_redraw
            ).pack(side="left")
            entry = ttk.Entry(row, textvariable=f["display_var"])
            entry.pack(side="left", fill="x", expand=True)
            entry.bind("<Return>", lambda e: self.schedule_redraw())
            entry.bind("<FocusOut>", lambda e: self.schedule_redraw())
        ttk.Label(
            self.files_frame,
            text="Uncheck to hide a file; edit its legend name inline.",
            foreground="gray", wraplength=300,
        ).pack(anchor="w", padx=4, pady=(2, 2))

    def _populate_controls(self):
        df = self.df

        # Data preview (first 5 rows)
        self.preview.delete(*self.preview.get_children())
        columns = df.columns.tolist()
        self.preview["columns"] = columns
        for col in columns:
            self.preview.heading(col, text=str(col))
            self.preview.column(col, width=90, stretch=False)
        for _, row in df.head().iterrows():
            self.preview.insert("", "end", values=[str(v) for v in row.tolist()])

        # Auto-detection
        auto_x = detect_x_column(df)
        auto_y = detect_y_columns(df, auto_x)
        self.autodetect_label.config(
            text=f"Auto-detected X: {auto_x} | Y: {', '.join(auto_y[:5])}"
        )

        self.x_combo["values"] = columns
        self.x_var.set(auto_x)

        self.y_listbox.delete(0, "end")
        for col in columns:
            self.y_listbox.insert("end", col)
        for i, col in enumerate(columns):
            if col in auto_y:
                self.y_listbox.selection_set(i)

        self._refresh_series_selector()
        self._set_default_range()

    def _selected_y_cols(self):
        return [self.y_listbox.get(i) for i in self.y_listbox.curselection()]

    def _on_y_selection_changed(self, event=None):
        self._refresh_series_selector()
        self.schedule_redraw()

    # -------------------------
    # SERIES STYLES
    # -------------------------
    def _series_style(self, col):
        return self.series_styles.setdefault(
            col, {"name": "", "color": None, "linestyle": "solid", "width": 1.5, "marker": "none"}
        )

    def _refresh_series_selector(self):
        y_cols = self._selected_y_cols()
        self.style_series_combo["values"] = y_cols
        if y_cols and self.style_series_var.get() not in y_cols:
            self.style_series_var.set(y_cols[0])
        elif not y_cols:
            self.style_series_var.set("")
        self._load_style_editor()

    def _load_style_editor(self):
        """Show the selected series' style in the editor widgets."""
        col = self.style_series_var.get()
        self._loading_style = True
        try:
            if not col:
                self.style_name_var.set("")
                self.color_swatch.config(text="auto", background=self.root.cget("background"))
                self.style_linestyle_var.set("solid")
                self.style_width_var.set("1.5")
                self.style_marker_var.set("none")
                return
            style = self._series_style(col)
            self.style_name_var.set(style["name"])
            if style["color"]:
                self.color_swatch.config(text="", background=style["color"])
            else:
                self.color_swatch.config(text="auto", background=self.root.cget("background"))
            self.style_linestyle_var.set(style["linestyle"])
            self.style_width_var.set(str(style["width"]))
            self.style_marker_var.set(style["marker"])
        finally:
            self._loading_style = False

    def _apply_style_editor(self):
        """Store the editor widgets' values on the selected series."""
        if self._loading_style:
            return
        col = self.style_series_var.get()
        if not col:
            return
        style = self._series_style(col)
        style["name"] = self.style_name_var.get()
        style["linestyle"] = self.style_linestyle_var.get()
        try:
            style["width"] = max(0.1, float(self.style_width_var.get()))
        except ValueError:
            style["width"] = 1.5
        style["marker"] = self.style_marker_var.get()
        self.schedule_redraw()

    def _pick_series_color(self):
        col = self.style_series_var.get()
        if not col:
            return
        style = self._series_style(col)
        _, hex_color = colorchooser.askcolor(
            color=style["color"] or "#1f77b4", title=f"Color for {col}"
        )
        if hex_color:
            style["color"] = hex_color
            self.color_swatch.config(text="", background=hex_color)
            self.schedule_redraw()

    def _reset_series_color(self):
        col = self.style_series_var.get()
        if not col:
            return
        self._series_style(col)["color"] = None
        self.color_swatch.config(text="auto", background=self.root.cget("background"))
        self.schedule_redraw()

    def _series_display_name(self, col):
        name = self._series_style(col)["name"].strip()
        return name if name else col

    def _plot_kwargs(self, col):
        style = self._series_style(col)
        kwargs = {"linestyle": style["linestyle"], "linewidth": style["width"]}
        if style["color"]:
            kwargs["color"] = style["color"]
        if style["marker"] and style["marker"] != "none":
            kwargs["marker"] = style["marker"]
        return kwargs

    def _set_default_range(self):
        df = self.df
        x_col = self.x_var.get()
        y_cols = self._selected_y_cols()

        try:
            x_default_min = float(df[x_col].min())
            x_default_max = float(df[x_col].max())
        except Exception:
            x_default_min, x_default_max = 0, 1

        try:
            y_default_min = float(df[y_cols].min().min())
            y_default_max = float(df[y_cols].max().max())
        except Exception:
            y_default_min, y_default_max = 0, 1

        self.range_vars["x_min"].set(str(x_default_min))
        self.range_vars["x_max"].set(str(x_default_max))
        self.range_vars["y_min"].set(str(y_default_min))
        self.range_vars["y_max"].set(str(y_default_max))

    def reset_range(self):
        if self.df is not None:
            self._set_default_range()
            self.schedule_redraw()

    def _figure_option(self, key, fallback):
        try:
            return float(self.figure_vars[key].get())
        except ValueError:
            return fallback

    def _get_range(self):
        values = {}
        for key, fallback in [("x_min", 0.0), ("x_max", 1.0), ("y_min", 0.0), ("y_max", 1.0)]:
            try:
                values[key] = float(self.range_vars[key].get())
            except ValueError:
                values[key] = fallback
        return values["x_min"], values["x_max"], values["y_min"], values["y_max"]

    # -------------------------
    # PLOTTING
    # -------------------------
    def schedule_redraw(self):
        # Coalesce rapid UI events into a single redraw
        if self._redraw_job is not None:
            self.root.after_cancel(self._redraw_job)
        self._redraw_job = self.root.after(150, self.update_plot)

    def update_plot(self):
        self._redraw_job = None
        if self.df is None:
            return

        self.clear_log()

        x_col = self.x_var.get()
        y_cols = self._selected_y_cols()
        plot_mode = self.mode_var.get()
        smooth = self.smooth_var.get()
        normalize = self.normalize_var.get()
        include_filename = self.include_filename_var.get()
        use_range = self.use_range_var.get()
        x_min, x_max, y_min, y_max = self._get_range()

        use_offset = False
        offset_value = 0.0
        if plot_mode == "Overlay" and len(y_cols) > 1 and self.use_offset_var.get():
            use_offset = True
            try:
                offset_value = float(self.offset_var.get())
            except ValueError:
                offset_value = 0.0

        # -------------------------
        # CREATE FIGURE
        # -------------------------
        # Artists pick up font.size at creation, so set it before rebuilding
        matplotlib.rcParams["font.size"] = self._figure_option("font_size", 10)

        self._plotted_data = []
        self._plotted_x_col = x_col

        fig = self.figure
        fig.clf()

        if not y_cols:
            self.canvas.draw()
            return

        if plot_mode == "Multi-panel":
            axes = fig.subplots(len(y_cols), 1, sharex=True)
            if len(y_cols) == 1:
                axes = [axes]
        else:
            ax = fig.add_subplot(111)

        # -------------------------
        # PROCESS FILES
        # -------------------------
        for f in self.files:
            if not f["enabled_var"].get():
                continue

            name = f["name"]
            display_name = f["display_var"].get().strip() or name
            try:
                df = f["df"].copy()

                if df.empty:
                    self.log_message(f"{name}: File is empty — skipped")
                    continue

                if x_col not in df.columns:
                    found = ", ".join(str(c) for c in df.columns)
                    self.log_message(
                        f"{name}: Missing X column '{x_col}' (file has: {found})"
                    )
                    continue

                # Coerce X before range filtering: comparing a text column
                # against the numeric limits would raise and skip the file.
                df[x_col] = pd.to_numeric(df[x_col], errors="coerce")

                if use_range:
                    df = df[(df[x_col] >= x_min) & (df[x_col] <= x_max)]

                for i, y_col in enumerate(y_cols):
                    if y_col not in df.columns:
                        self.log_message(f"{name}: Missing Y column '{y_col}' — skipped")
                        continue

                    # --- VALIDATION ---
                    df[y_col] = pd.to_numeric(df[y_col], errors="coerce")

                    original_len = len(df)
                    df_clean = df[[x_col, y_col]].dropna()

                    removed = original_len - len(df_clean)
                    if removed > 0:
                        self.log_message(f"{name} ({y_col}): Dropped {removed} invalid rows")

                    if df_clean.empty:
                        continue

                    x_data = df_clean[x_col]
                    y_data = df_clean[y_col]

                    if smooth:
                        y_data = y_data.rolling(5).mean()

                    if normalize:
                        y_data = y_data / y_data.max()

                    series_name = self._series_display_name(y_col)
                    plot_kwargs = self._plot_kwargs(y_col)

                    if plot_mode == "Overlay":
                        if use_offset:
                            y_data = y_data + i * offset_value

                        label = (
                            f"{display_name} | {series_name}"
                            if include_filename else series_name
                        )
                        ax.plot(x_data, y_data, label=label, **plot_kwargs)
                    else:
                        axes[i].plot(x_data, y_data, **plot_kwargs)

                    self._plotted_data.append(
                        {"file": display_name, "series": series_name,
                         "x": x_data, "y": y_data}
                    )

            except Exception as e:
                self.log_message(f"{name}: {e}")

        # -------------------------
        # LABELING
        # -------------------------
        x_label = self.label_vars["x_label"].get()
        x_unit = self.label_vars["x_unit"].get()
        y_label = self.label_vars["y_label"].get()
        y_unit = self.label_vars["y_unit"].get()
        custom_title = self.label_vars["title"].get()

        final_xlabel = x_label if x_label else x_col
        if x_unit:
            final_xlabel += f" ({x_unit})"

        if plot_mode == "Overlay":
            if use_range:
                ax.set_ylim(y_min, y_max)

            final_ylabel = y_label if y_label else "Signal"
            if y_unit:
                final_ylabel += f" ({y_unit})"

            if custom_title:
                ax.set_title(custom_title)

            ax.set_xlabel(final_xlabel)
            ax.set_ylabel(final_ylabel)
            if ax.get_legend_handles_labels()[0]:
                ax.legend()

        else:
            for i, y_col in enumerate(y_cols):
                axes[i].set_ylabel(self._series_display_name(y_col))
                if use_range:
                    axes[i].set_ylim(y_min, y_max)

            axes[-1].set_xlabel(final_xlabel)

            if custom_title:
                fig.suptitle(custom_title)

        fig.tight_layout()
        self.canvas.draw()

    # -------------------------
    # SAVE / DOWNLOAD
    # -------------------------
    def save_figure(self):
        if self.df is None:
            self.log_message("Load data before saving a figure.")
            return

        path = filedialog.asksaveasfilename(
            title="Save Figure",
            defaultextension=".png",
            filetypes=[("PNG", "*.png"), ("PDF", "*.pdf"), ("TIFF", "*.tiff")],
            initialfile="plot.png",
        )
        if not path:
            return

        ext = os.path.splitext(path)[1].lstrip(".").lower() or "png"
        if ext == "tif":
            ext = "tiff"

        width = self._figure_option("fig_width", 6.0)
        height = self._figure_option("fig_height", 4.0)
        dpi = self._figure_option("dpi", 600)

        # The embedded canvas dictates the on-screen size, so the export size
        # is applied only for savefig and restored afterwards.
        original_size = self.figure.get_size_inches().copy()
        try:
            self.figure.set_size_inches(width, height)
            self.figure.tight_layout()
            self.figure.savefig(path, format=ext, dpi=dpi)
            self.log_message(f"Figure saved to {path} ({width}x{height} in, {dpi:g} dpi)")
        except Exception as e:
            self.log_message(f"Could not save figure: {e}")
        finally:
            self.figure.set_size_inches(*original_size)
            self.figure.tight_layout()
            self.canvas.draw()

    def export_data(self):
        """Export the data exactly as plotted (range-limited, smoothed,
        normalized, offset) to a tidy CSV."""
        if not self._plotted_data:
            self.log_message("Nothing plotted yet — load data before exporting.")
            return

        path = filedialog.asksaveasfilename(
            title="Export Plotted Data",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
            initialfile="plotted_data.csv",
        )
        if not path:
            return

        x_name = str(self._plotted_x_col)
        if x_name in ("file", "series", "value"):
            x_name = f"x_{x_name}"
        frames = [
            pd.DataFrame({
                "file": rec["file"],
                "series": rec["series"],
                x_name: rec["x"].to_numpy(),
                "value": rec["y"].to_numpy(),
            })
            for rec in self._plotted_data
        ]

        try:
            pd.concat(frames, ignore_index=True).to_csv(path, index=False)
            self.log_message(f"Plotted data exported to {path}")
        except Exception as e:
            self.log_message(f"Could not export data: {e}")


def main():
    root = tk.Tk()
    LabDataPlotterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
