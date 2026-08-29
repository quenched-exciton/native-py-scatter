# Test data fixtures

Reusable sample files for manual exploration and for the automated suite
(`test_lab_data_plotter.py`). Open them from the app with **Open CSV / JSON files…**.

| File | Shape | Exercises |
| --- | --- | --- |
| `experiment.csv` | `time`, `signal_a`, `signal_b` | Baseline line plot; `time` auto-detected as X, both signals as Y |
| `experiment_run2.csv` | same columns as `experiment.csv` | Overlay a second run; per-file legend rename; verifying styles do **not** leak between loads |
| `experiment.json` | same rows as `experiment.csv` | JSON loader path |
| `assay.csv` | `sample`, `mean_intensity`, `std_error` | Bar chart with a text X axis; pick `std_error` as the per-series Error column |
| `constant_signal.csv` | `x`, `level_a`, `level_b` (both constant) | Degenerate data — no Y column is auto-detected, so default plot range must not become `nan` |
| `categories.csv` | `idx`, `category` (text), `count` | Selecting a non-numeric column as Y; range reset must stay finite |
| `messy.csv` | blanks + `not_a_number` in numeric columns | Row-dropping / `to_numeric` coercion, the "Dropped N invalid rows" message, and smoothing a short series (only ~5 rows survive) without blanking the plot |

Run the suite from the project root:

```
python3 -m unittest -v test_lab_data_plotter
```
