# -*- coding: utf-8 -*-
import sys
import os
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QCheckBox, QTabWidget, QTableWidget,
    QTableWidgetItem, QFileDialog, QMessageBox, QGroupBox, QHeaderView, QLineEdit,
    QFrame
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from excel_processor import ExcelSetProcessor

class SetAnalyzerGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("엑셀 집합 분석 툴 - 클립보드 복사 전용 (Excel Set Analyzer)")
        self.resize(1100, 750)
        
        self.current_file = None
        self.processor = None
        self.analysis_result = None
        
        self.tab_keys = ['intersection', 'a_only', 'b_only', 'sym_diff', 'union']
        
        self.init_ui()
        self.apply_stylesheet()

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(16)
        
        # -------------------------------------------------------------
        # Left Panel: Controls
        # -------------------------------------------------------------
        left_panel = QFrame()
        left_panel.setFixedWidth(320)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(12, 12, 12, 12)
        left_layout.setSpacing(14)
        
        title_label = QLabel("📋 Excel Set Analyzer")
        title_label.setFont(QFont("맑은 고딕", 14, QFont.Bold))
        left_layout.addWidget(title_label)
        
        # File Selection Box
        file_group = QGroupBox("1. 파일 선택")
        file_layout = QVBoxLayout(file_group)
        self.btn_select_file = QPushButton("📁 엑셀 파일 열기 (.xlsx, .csv)")
        self.btn_select_file.clicked.connect(self.select_file)
        self.lbl_filename = QLabel("선택된 파일 없음")
        self.lbl_filename.setWordWrap(True)
        self.lbl_filename.setStyleSheet("color: #94a3b8; font-size: 11px;")
        file_layout.addWidget(self.btn_select_file)
        file_layout.addWidget(self.lbl_filename)
        left_layout.addWidget(file_group)
        
        # Target Columns Selection Box
        setup_group = QGroupBox("2. 시트 및 컬럼 선택")
        setup_layout = QVBoxLayout(setup_group)
        
        setup_layout.addWidget(QLabel("시트 선택:"))
        self.combo_sheet = QComboBox()
        self.combo_sheet.currentTextChanged.connect(self.on_sheet_changed)
        setup_layout.addWidget(self.combo_sheet)
        
        setup_layout.addWidget(QLabel("🔵 컬럼 A (기준 1):"))
        self.combo_col_a = QComboBox()
        setup_layout.addWidget(self.combo_col_a)
        
        setup_layout.addWidget(QLabel("🔴 컬럼 B (기준 2):"))
        self.combo_col_b = QComboBox()
        setup_layout.addWidget(self.combo_col_b)
        
        left_layout.addWidget(setup_group)
        
        # Preprocessing Options
        opt_group = QGroupBox("3. 전처리 옵션")
        opt_layout = QVBoxLayout(opt_group)
        self.chk_trim = QCheckBox("앞뒤 공백 자동 제거 (Trim)")
        self.chk_trim.setChecked(True)
        self.chk_case = QCheckBox("대소문자 엄격 구분 (Case-Sensitive)")
        self.chk_drop_empty = QCheckBox("빈 값 / N/A 제외")
        self.chk_drop_empty.setChecked(True)
        
        opt_layout.addWidget(self.chk_trim)
        opt_layout.addWidget(self.chk_case)
        opt_layout.addWidget(self.chk_drop_empty)
        left_layout.addWidget(opt_group)
        
        # Analyze Button
        self.btn_analyze = QPushButton("⚡ 집합 비교 분석 수행")
        self.btn_analyze.setFixedHeight(45)
        self.btn_analyze.setFont(QFont("맑은 고딕", 11, QFont.Bold))
        self.btn_analyze.setStyleSheet("background-color: #2563eb; color: white; border-radius: 6px;")
        self.btn_analyze.clicked.connect(self.run_analysis)
        left_layout.addWidget(self.btn_analyze)
        
        left_layout.addStretch()
        main_layout.addWidget(left_panel)
        
        # -------------------------------------------------------------
        # Right Panel: Results & Clipboard Copy
        # -------------------------------------------------------------
        right_panel = QVBoxLayout()
        
        # Clipboard Action Bar
        action_box = QFrame()
        action_box.setStyleSheet("background-color: #1e293b; border-radius: 8px; padding: 12px;")
        action_layout = QHBoxLayout(action_box)
        
        lbl_info = QLabel("📋 선택된 탭 데이터:")
        lbl_info.setFont(QFont("맑은 고딕", 10, QFont.Bold))
        
        self.btn_copy_vals = QPushButton("📋 데이터 값만 복사 (1줄 1개)")
        self.btn_copy_vals.setStyleSheet("background-color: #059669; color: white; font-weight: bold; padding: 8px 12px;")
        self.btn_copy_vals.clicked.connect(self.copy_values_only)
        
        self.btn_copy_table = QPushButton("📊 엑셀 표 형태 복사 (탭 구분)")
        self.btn_copy_table.setStyleSheet("background-color: #3b82f6; color: white; font-weight: bold; padding: 8px 12px;")
        self.btn_copy_table.clicked.connect(self.copy_table_tsv)
        
        action_layout.addWidget(lbl_info)
        action_layout.addWidget(self.btn_copy_vals)
        action_layout.addWidget(self.btn_copy_table)
        action_layout.addStretch()
        
        right_panel.addWidget(action_box)
        
        # Search Box
        search_layout = QHBoxLayout()
        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("🔍 결과 데이터 내 검색...")
        self.txt_search.textChanged.connect(self.filter_table)
        search_layout.addWidget(self.txt_search)
        right_panel.addLayout(search_layout)
        
        # Data Tabs
        self.tabs = QTabWidget()
        self.tables = {}
        for key in self.tab_keys:
            table = self.create_data_table()
            self.tables[key] = table
            
        self.tabs.addTab(self.tables['intersection'], "🔵 교집합 (0)")
        self.tabs.addTab(self.tables['a_only'], "🟡 A전용/차집합A (0)")
        self.tabs.addTab(self.tables['b_only'], "🔴 B전용/차집합B (0)")
        self.tabs.addTab(self.tables['sym_diff'], "🟣 통합 대칭차집합 (0)")
        self.tabs.addTab(self.tables['union'], "🟢 합집합 (0)")
        
        right_panel.addWidget(self.tabs)
        main_layout.addLayout(right_panel)

    def create_data_table(self):
        table = QTableWidget()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(["번호", "데이터 값", "구분 (출처)", "A컬럼 존재", "B컬럼 존재"])
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        table.setAlternatingRowColors(True)
        return table

    def apply_stylesheet(self):
        self.setStyleSheet("""
            QMainWindow { background-color: #0f172a; }
            QWidget { color: #f8fafc; font-family: '맑은 고딕'; }
            QGroupBox { font-weight: bold; border: 1px solid #334155; border-radius: 6px; margin-top: 10px; padding-top: 10px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; color: #94a3b8; }
            QPushButton { background-color: #334155; border: none; border-radius: 4px; padding: 8px; color: white; }
            QPushButton:hover { background-color: #475569; }
            QComboBox, QLineEdit { background-color: #1e293b; border: 1px solid #334155; border-radius: 4px; padding: 6px; color: white; }
            QTabWidget::pane { border: 1px solid #334155; background-color: #1e293b; }
            QTabBar::tab { background: #0f172a; padding: 10px 16px; border: 1px solid #334155; }
            QTabBar::tab:selected { background: #2563eb; color: white; font-weight: bold; }
            QTableWidget { background-color: #1e293b; gridline-color: #334155; border: none; }
            QHeaderView::section { background-color: #0f172a; color: #cbd5e1; font-weight: bold; border: 1px solid #334155; padding: 6px; }
        """)

    def select_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "엑셀 또는 CSV 파일 선택", "", "Excel/CSV Files (*.xlsx *.xls *.csv)")
        if path:
            self.current_file = path
            self.processor = ExcelSetProcessor(path)
            self.lbl_filename.setText(os.path.basename(path))
            
            sheets = self.processor.get_sheet_names()
            self.combo_sheet.clear()
            self.combo_sheet.addItems(sheets)

    def on_sheet_changed(self, sheet_name):
        if self.processor and sheet_name:
            cols = self.processor.get_columns(sheet_name)
            self.combo_col_a.clear()
            self.combo_col_b.clear()
            self.combo_col_a.addItems(cols)
            self.combo_col_b.addItems(cols)
            if len(cols) > 1:
                self.combo_col_b.setCurrentIndex(1)

    def run_analysis(self):
        if not self.processor:
            QMessageBox.warning(self, "경고", "먼저 엑셀 파일을 선택해주세요.")
            return

        sheet = self.combo_sheet.currentText()
        col_a = self.combo_col_a.currentText()
        col_b = self.combo_col_b.currentText()

        if not col_a or not col_b:
            QMessageBox.warning(self, "경고", "비교할 컬럼 A와 B를 지정해주세요.")
            return

        self.analysis_result = self.processor.analyze_sets(
            sheet_a=sheet,
            col_a=col_a,
            sheet_b=sheet,
            col_b=col_b,
            case_sensitive=self.chk_case.isChecked(),
            trim_space=self.chk_trim.isChecked(),
            drop_empty=self.chk_drop_empty.isChecked()
        )

        stats = self.analysis_result['stats']
        self.tabs.setTabText(0, f"🔵 교집합 ({stats['intersection_count']})")
        self.tabs.setTabText(1, f"🟡 A전용/차집합A ({stats['a_only_count']})")
        self.tabs.setTabText(2, f"🔴 B전용/차집합B ({stats['b_only_count']})")
        self.tabs.setTabText(3, f"🟣 통합 대칭차집합 ({stats['sym_diff_count']})")
        self.tabs.setTabText(4, f"🟢 합집합 ({stats['union_count']})")

        for key in self.tab_keys:
            self.populate_table(self.tables[key], self.analysis_result[key])

    def populate_table(self, table: QTableWidget, data_list: list):
        table.setRowCount(len(data_list))
        for idx, item in enumerate(data_list):
            table.setItem(idx, 0, QTableWidgetItem(str(idx + 1)))
            table.setItem(idx, 1, QTableWidgetItem(str(item['val'])))
            table.setItem(idx, 2, QTableWidgetItem(str(item['origin'])))
            
            item_a = QTableWidgetItem(item['in_a'])
            item_a.setTextAlignment(Qt.AlignCenter)
            table.setItem(idx, 3, item_a)

            item_b = QTableWidgetItem(item['in_b'])
            item_b.setTextAlignment(Qt.AlignCenter)
            table.setItem(idx, 4, item_b)

    def filter_table(self, query):
        query = query.strip().lower()
        current_table = self.tabs.currentWidget()
        if not current_table:
            return
        
        for row in range(current_table.rowCount()):
            val_item = current_table.item(row, 1)
            origin_item = current_table.item(row, 2)
            
            match = True
            if query:
                val_text = val_item.text().lower() if val_item else ""
                orig_text = origin_item.text().lower() if origin_item else ""
                match = (query in val_text or query in orig_text)
                
            current_table.setRowHidden(row, not match)

    def copy_values_only(self):
        curr_tab_idx = self.tabs.currentIndex()
        tab_key = self.tab_keys[curr_tab_idx]
        if not self.analysis_result or tab_key not in self.analysis_result:
            return

        items = self.analysis_result[tab_key]
        text = "\n".join(item['val'] for item in items)
        
        QApplication.clipboard().setText(text)
        QMessageBox.information(self, "클립보드 복사", f"📋 데이터 값 {len(items)}개가 클립보드에 복사되었습니다!\n(Ctrl+V로 엑셀에 붙여넣으세요)")

    def copy_table_tsv(self):
        curr_tab_idx = self.tabs.currentIndex()
        tab_key = self.tab_keys[curr_tab_idx]
        if not self.analysis_result or tab_key not in self.analysis_result:
            return

        items = self.analysis_result[tab_key]
        headers = ["번호", "데이터값", "구분(출처)", "A존재", "B존재"]
        rows = [f"{idx+1}\t{item['val']}\t{item['origin']}\t{item['in_a']}\t{item['in_b']}" for idx, item in enumerate(items)]
        text = "\n".join([ "\t".join(headers) ] + rows)
        
        QApplication.clipboard().setText(text)
        QMessageBox.information(self, "클립보드 복사", f"📊 표 데이터 {len(items)}행이 클립보드에 복사되었습니다!\n(Ctrl+V로 엑셀에 붙여넣으세요)")

def run_gui():
    app = QApplication(sys.argv)
    window = SetAnalyzerGUI()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    run_gui()
