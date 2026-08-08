# ⚠️ Agent Guidelines for work_helper

> **IMPORTANT**: This repository is strictly a **Windows Desktop GUI Application** built with **PySide6 (Qt for Python)**.

## 🛑 CRITICAL ARCHITECTURE & UI DESIGN RULES
1. **NO WEB APPLICATIONS**: Do NOT introduce web servers (HTTP server, Flask, FastAPI), HTML/CSS/JS frontend files, or `web/` directories.
2. **GUI ENTRY POINT**: The primary entry point is `gui.py`.
3. **STRICT DARK THEME STYLING & ZERO CONTRAST BUGS**:
   - Every dialog (`QMessageBox`, `QDialog`), popup menu, tooltip, dropdown (`QComboBox`), and input MUST be explicitly styled with dark background (`#1e293b`/`#0f172a`) and bright text (`#f8fafc`/`#ffffff`).
   - NEVER leave native Windows default popups or un-styled dialogs that cause white-on-white or truncated text bugs.
   - Always ensure table selection (`QTableWidget::item:selected`) has explicit high-contrast highlight background (`#2563eb`) and text (`#ffffff`).
4. **EXECUTABLE PACKAGING**: PyInstaller. `configs/` must be shipped via `--add-data "configs;configs"` — it is read at runtime. See README for the full command.

## 🧱 Module layout

| File | Responsibility |
|------|---------------|
| `gui.py` | Entry point, main window, Todo / Set Analyzer / Concat tabs |
| `deid_widget.py` | De-identification tab UI + `QThread` worker |
| `deid_service.py` | Adapter over vendored `hkdeid/` — key path, progress, cancel, structured report |
| `log_widget.py` | Log analysis tab UI + `QThread` worker |
| `log_analyzer.py` | Log engine — encoding detection, multi-line folding, Drain template mining |
| `clipboard_parser.py` | Shared paste-table parsing |
| `excel_processor.py` | Set operations + styled Excel report export |
| `todo_manager.py` | Todo persistence (atomic writes, corruption recovery) |
| `hkdeid/`, `configs/` | **Vendored from [HKDeID](https://github.com/gatsjy/HKDeID) — keep unmodified** |

### Rules for the vendored `hkdeid/` package
- **Do not edit files under `hkdeid/`.** Upstream fixes should be pulled in wholesale.
- Behaviour that must differ for this app is adapted in `deid_service.py` (e.g. the secret-key path is patched there for frozen builds, and `get_secret_key` is wrapped with a cache).
- If you patch a name that `hkdeid` imports with `from ... import x`, patch **both** namespaces — the importing module holds its own binding.

## 🖥️ Application Features (`gui.py`)
- **100% Clipboard (`Ctrl+V`) Operation** for tabs 2 and 3.
- **Startup Splash Screen**: progress reflects real work — do not reintroduce `time.sleep()` fake progress.
- **Shortcuts**: `F1`–`F5` switch tabs, one per tab. Todo refresh is `Ctrl+R` (it used to own `F5`, which collided with the tab numbering). Any new tab takes the next function key and must be added to `closeEvent`'s shutdown list if it owns a thread.
- **Floating Toast Notifications** (`ToastNotification`), stacked so concurrent toasts do not overlap.
- **Tab 1 — 📝 Smart Todo List (`F1`)**: daily rollover, progress bar, filters. `F5` refreshes.
- **Tab 2 — 📊 Set Analyzer (`F2`)**: intersection / A-only / B-only / symmetric difference / union.
- **Tab 3 — 🔗 Column Concat & SQL Generator (`F3`)**: prefix/suffix wrapping, SQL presets, header right-click column insert/delete.
- **Tab 4 — 🛡️ De-identification (`F4`)**: HKDeID-powered Excel PII masking with dry-run preview.
- **Tab 5 — 📄 Log Analysis (`F5`)**: Drain-style template mining that surfaces rare / new / bursting log patterns.

### Rules for the log analyzer
- `log_analyzer.py` must stay **free of Qt imports** — it is the testable core; all UI lives in `log_widget.py`.
- The value of this tab is *surfacing what grep buries*. Any change must keep `test_log_analyzer.py::TestEndToEnd::test_buried_signals_are_surfaced` and `test_dominant_noise_is_not_in_rare` passing — those encode the whole point.
- Masking order in `_MASKS` matters: broad patterns before narrow ones will swallow them. Unit-suffixed numbers (`300s`, `1.5MB`) must be masked **before** the bare-number pattern, or templates degrade into `<*>`.
- Multi-line folding is stateful for Python tracebacks (the terminating `ValueError: ...` line sits at column 0 and is indistinguishable per-line). Do not "simplify" it back to a pure per-line regex.

## 🧨 Regressions that were fixed — do not reintroduce

These were real bugs. Each has a test guarding it.

1. **`QMenu` was used but never imported** — every column right-click raised `NameError`, and PySide6 aborts the process on an unhandled slot exception, so the `--noconsole` exe just vanished. Keep `install_exception_hook()` wired up in `run_gui()`.
2. **Comma splitting corrupted data** — `"Kim, John"` silently became `"Kim"`. Excel copies as **TAB**. Only treat commas as a delimiter for genuine CSV (consistent field count, ≥3 fields). All paste parsing goes through `clipboard_parser.py`.
3. **Separator sniffed from the first line only** — later tab-delimited lines were kept whole. Sniff across all lines.
4. **Todo file was written non-atomically** — a crash mid-write left broken JSON, which loaded as an empty list and was then overwritten, silently destroying every task. `save_data()` writes to a temp file, fsyncs, and `os.replace()`s; a corrupt file is quarantined, never overwritten.
5. **Clipboard hijacking** — typing one character into prefix/suffix overwrote the user's OS clipboard and fired a toast. Auto-copy only on explicit actions; recomputation is debounced.
6. **Copy ignored the search filter** — users copied unfiltered data believing it was filtered. Copy paths use `visible_items()` / `visible_results()`.
7. **`rollover_count` counted app launches, not days** — opening the app 3× in a day showed "3일 이월됨". It now counts real elapsed days and is idempotent within a day.
8. **`simulate_next_day()` destroyed future due dates** — it forced *every* pending task to yesterday. It now only touches tasks due today or earlier.
9. **Secret key regenerated every run when frozen** — `hkdeid/security.py` resolves the key relative to `__file__`, which under `--onefile` is a temp dir deleted on exit. Pseudonyms changed every run, silently breaking cross-file linkage. `deid_service.resolve_key_file()` pins it next to the exe.
10. **Key file was re-read for every masked cell** — one disk read per cell. `deid_service` caches it.

## 🔐 Security rules
- **Never commit `.secret.key`.** It is in `.gitignore`. Anyone with the key plus a candidate value can confirm whether that value maps to a given pseudonym.
- **Never commit patient data** — `*_deid.xlsx` and `dist/` are gitignored.
- When the de-identifier detects **zero** PII columns it must warn loudly. A silently-unmasked file that the user believes is safe is the worst failure mode this app has.

## 🧪 Testing
```bash
python -m pytest -q
```
Add a regression test with any bug fix. Tests must assert — the original `test_processor.py` only printed, so it passed no matter what the code did.
