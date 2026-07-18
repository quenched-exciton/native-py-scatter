# 📊 Lab Data Plotter (Native)

A simple plotting tool to make standardized images with easy customization
options. This is a native desktop version of the Lab Data Plotter, ported from
Streamlit to Tkinter — everything runs locally in a single window, no browser
or web server.

## Features

- Open one or more **CSV / JSON** files (first valid file drives column choices)
- **Per-file toggling and unloading**: include/exclude any loaded file from the
  plot, unload a file selected by mistake, and give each file a custom legend
  name — all without re-opening dialogs
- **Data preview** of the first rows
- **Auto-detection** of the X column (`time` / `wavelength` / `x`, then first
  monotonic numeric column) and of meaningful Y columns
- **Line or Bar charts**: bar mode draws grouped bars and treats the X column
  as categories (text labels work)
- **Error bars**: pick an error column per series — drawn as caps on bars and
  as error bars on line plots
- **Overlay** or **Multi-panel** plot modes
- **Per-series styling**: custom legend name, color, line style, line width,
  and marker for each plotted column
- Optional **smoothing** (rolling mean), **normalization**, and per-series
  **vertical offset** (overlay mode)
- **Plot range limits** with one-click reset to full range
- Custom **title, axis labels, and units**
- Interactive matplotlib toolbar (pan / zoom)
- **Publication figure options**: exact export size in inches, font size, and
  export DPI
- **Save figure** as PNG, PDF, or TIFF
- **Export plotted data** to a tidy CSV — the numbers exactly as drawn, after
  range limiting, smoothing, normalization, and offset

## Example data

Save this as `experiment.csv` and open it in the app — `time` is auto-detected
as the X axis and both signals as Y series:

```csv
time,signal_a,signal_b
0.0,0.02,1.95
0.5,0.48,1.72
1.0,0.84,1.08
1.5,1.00,0.31
2.0,0.91,-0.42
2.5,0.60,-1.02
3.0,0.14,-1.63
3.5,-0.35,-1.94
```

Open a second file with the same columns to overlay runs, then use the Loaded
Files panel to rename, hide, or unload either one.

For a bar chart with error bars, save this as `assay.csv`, switch **Chart
Type** to *Bar*, set X to `sample`, Y to `mean_intensity`, and in **Series
Styles** choose `std_error` as the Error column:

```csv
sample,mean_intensity,std_error
Control,12.4,0.8
Treated A,18.9,1.1
Treated B,15.2,0.9
Blank,2.1,0.3
```

## Running

```bash
pip install -r requirements.txt
python lab_data_plotter.py
```

Tkinter ships with the standard CPython installers on Windows and macOS. On
Debian/Ubuntu Linux you may need `sudo apt install python3-tk`.

### Portable setup

Like the original app, `lab_data_plotter.py` prepends a local `libs/` folder to
`sys.path`. To run on a machine without installing packages system-wide, place
dependencies there:

```bash
pip install --target libs pandas numpy matplotlib
```

## Building a portable app folder (optional)

Place your icon file as `app.ico` next to `lab_data_plotter.py` — it becomes
both the `.exe` icon and the window (title bar) icon. Then, on Windows:

```bash
pip install pyinstaller
pyinstaller --noconfirm --clean --onedir --windowed --name LabDataPlotter --icon app.ico --add-data "app.ico;." --hidden-import PIL._tkinter_finder lab_data_plotter.py
```

The portable app is produced at `dist/LabDataPlotter/` — zip that folder and
run `LabDataPlotter.exe` inside it on any Windows machine, no Python needed.

On macOS/Linux the `--add-data` separator is `:` instead of `;`
(`--add-data "app.ico:."`).

---
Developed by Cristian J. Aviles-Martin Ph.D.
