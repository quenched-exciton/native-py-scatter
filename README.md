# 📊 Lab Data Plotter (Native)

A simple plotting tool to make standardized images with easy customization
options. This is a native desktop version of the Lab Data Plotter, ported from
Streamlit to Tkinter — everything runs locally in a single window, no browser
or web server.

## Features

- Open one or more **CSV / JSON** files (first valid file drives column choices)
- **Data preview** of the first rows
- **Auto-detection** of the X column (`time` / `wavelength` / `x`, then first
  monotonic numeric column) and of meaningful Y columns
- **Overlay** or **Multi-panel** plot modes
- Optional **smoothing** (rolling mean), **normalization**, and per-series
  **vertical offset** (overlay mode)
- **Plot range limits** with one-click reset to full range
- Custom **title, axis labels, and units**
- Interactive matplotlib toolbar (pan / zoom)
- **Save figure** as PNG, PDF, or TIFF at 600 dpi

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

## Building a standalone executable (optional)

```bash
pip install pyinstaller
pyinstaller --onefile --windowed lab_data_plotter.py
```

The executable is produced in `dist/`.

---
Developed by Cristian J. Aviles-Martin Ph.D.
