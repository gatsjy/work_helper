# ⚠️ Agent Guidelines for work_helper

> **IMPORTANT**: This repository is strictly a **Windows Desktop GUI Application** built with **PySide6 (Qt for Python)**.

## 🛑 CRITICAL ARCHITECTURE RULES
1. **DO NOT CREATE WEB APPLICATIONS**: Do NOT introduce web servers (HTTP server, Flask, FastAPI), HTML/CSS/JS frontend files, or `web/` directories.
2. **GUI ENTRY POINT**: The primary entry point for this application is [gui.py](file:///c:/Users/KNUH/work_helper/gui.py).
3. **EXECUTABLE PACKAGING**: The standalone Windows executable is built using PyInstaller:
   ```bash
   pyinstaller --noconsole --onefile --name "ExcelSetAnalyzer" gui.py
   ```
   Target binary: `dist/ExcelSetAnalyzer.exe`.

## 🖥️ Application Features (`gui.py`)
- **100% Clipboard (`Ctrl+V`) Operation**: All operations accept data pasted directly from Excel.
- **Tab 1: 📊 엑셀 집합 분석 (Set Analyzer)**: Dual clipboard text paste areas for calculating Intersection, A Only, B Only, Symmetric Difference, and Union.
- **Tab 2: 🔗 컬럼 Concat / 병합 (Column Concat)**: Clipboard TSV table parsing and interactive column chip clicking for row-by-row string concatenation.
