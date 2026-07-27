# -*- coding: utf-8 -*-
import sys
import os
import re
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QCheckBox, QTabWidget, QTableWidget,
    QTableWidgetItem, QFileDialog, QMessageBox, QGroupBox, QHeaderView, QLineEdit,
    QFrame, QTextEdit
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from excel_processor import ExcelSetProcessor

class SetAnalyzerWidget(QWidget):
    """기존 집합 분석(교집합/차집합/대칭차집합/합집합) 위젯"""
    def __init__(self):
        super().__init__()
        self.current_file = None
        self.processor = None
        self.analysis_result = None
        self.tab_keys = ['intersection', 'a_only', 'b_only', 'sym_diff', 'union']
        self.init_ui()

    def init_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(16)

        # -------------------------------------------------------------
        # Left Panel: Controls
        # -------------------------------------------------------------
        left_panel = QFrame()
        left_panel.setFixedWidth(320)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(8, 8, 8, 8)
        left_layout.setSpacing(14)

        title_label = QLabel("📋 Excel Set Analyzer")
        title_label.setFont(QFont("맑은 고딕", 14, QFont.Bold))
        left_layout.addWidget(title_label)

        # Group 1: Data A Paste
        group_a = QGroupBox("1. 데이터 A 붙여넣기 (Ctrl+V)")
        layout_a = QVBoxLayout(group_a)
        self.txt_paste_a = QTextEdit()
        self.txt_paste_a.setPlaceholderText("엑셀에서 복사(Ctrl+C)한 1번째 데이터를 붙여넣으세요 (Ctrl+V)...")
        self.txt_paste_a.textChanged.connect(self.run_analysis)
        layout_a.addWidget(self.txt_paste_a)
        left_layout.addWidget(group_a)

        # Group 2: Data B Paste
        group_b = QGroupBox("2. 데이터 B 붙여넣기 (Ctrl+V)")
        layout_b = QVBoxLayout(group_b)
        self.txt_paste_b = QTextEdit()
        self.txt_paste_b.setPlaceholderText("엑셀에서 복사(Ctrl+C)한 2번째 데이터를 붙여넣으세요 (Ctrl+V)...")
        self.txt_paste_b.textChanged.connect(self.run_analysis)
        layout_b.addWidget(self.txt_paste_b)
        left_layout.addWidget(group_b)

        # Preprocessing Options
        opt_group = QGroupBox("3. 전처리 옵션")
        opt_layout = QVBoxLayout(opt_group)
        self.chk_header = QCheckBox("첫행 헤더 제외 (1행 이름 제외)")
        self.chk_header.toggled.connect(self.run_analysis)
        self.chk_trim = QCheckBox("앞뒤 공백 자동 제거 (Trim)")
        self.chk_trim.setChecked(True)
        self.chk_trim.toggled.connect(self.run_analysis)
        self.chk_case = QCheckBox("대소문자 엄격 구분 (Case-Sensitive)")
        self.chk_case.toggled.connect(self.run_analysis)
        self.chk_drop_empty = QCheckBox("빈 값 / N/A 제외")
        self.chk_drop_empty.setChecked(True)
        self.chk_drop_empty.toggled.connect(self.run_analysis)

        opt_layout.addWidget(self.chk_header)
        opt_layout.addWidget(self.chk_trim)
        opt_layout.addWidget(self.chk_case)
        opt_layout.addWidget(self.chk_drop_empty)
        left_layout.addWidget(opt_group)

        # Analyze Button
        self.btn_analyze = QPushButton("⚡ 실시간 집합 비교 분석")
        self.btn_analyze.setFixedHeight(40)
        self.btn_analyze.setFont(QFont("맑은 고딕", 10, QFont.Bold))
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

    def read_clip_a(self):
        text = QApplication.clipboard().text()
        if text:
            self.txt_paste_a.setPlainText(text)

    def read_clip_b(self):
        text = QApplication.clipboard().text()
        if text:
            self.txt_paste_b.setPlainText(text)

    def run_analysis(self):
        raw_text_a = self.txt_paste_a.toPlainText()
        raw_text_b = self.txt_paste_b.toPlainText()

        if not raw_text_a.strip() and not raw_text_b.strip():
            self.analysis_result = None
            for idx, key in enumerate(self.tab_keys):
                self.tables[key].setRowCount(0)
            return

        self.analysis_result = ExcelSetProcessor.analyze_raw_text_sets(
            raw_text_a=raw_text_a,
            raw_text_b=raw_text_b,
            has_header_a=self.chk_header.isChecked(),
            has_header_b=self.chk_header.isChecked(),
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


class ColumnConcatWidget(QWidget):
    """신규: 클립보드 붙여넣기 기반 컬럼 Concat(병합) 위젯"""
    def __init__(self):
        super().__init__()
        self.concat_raw_rows = []
        self.concat_headers = []
        self.selected_indices = []
        self.concat_results = []

        self.init_ui()

    def init_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(16)

        # -------------------------------------------------------------
        # Left Panel: Controls
        # -------------------------------------------------------------
        left_panel = QFrame()
        left_panel.setFixedWidth(340)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(8, 8, 8, 8)
        left_layout.setSpacing(12)

        # Group 1: Paste Area
        paste_group = QGroupBox("1. 클립보드 데이터 붙여넣기 (Ctrl+V)")
        paste_layout = QVBoxLayout(paste_group)
        self.txt_paste = QTextEdit()
        self.txt_paste.setPlaceholderText("엑셀에서 복사(Ctrl+C)한 표 데이터를 여기에 붙여넣으세요 (Ctrl+V)...")
        self.txt_paste.textChanged.connect(self.on_paste_text_changed)
        paste_layout.addWidget(self.txt_paste)

        btn_box = QHBoxLayout()
        self.btn_clear = QPushButton("초기화")
        self.btn_clear.clicked.connect(self.clear_data)
        btn_box.addStretch()
        btn_box.addWidget(self.btn_clear)
        paste_layout.addLayout(btn_box)
        left_layout.addWidget(paste_group)

        # Group 2: Header & Options
        opt_group = QGroupBox("2. 옵션 및 구분자 설정")
        opt_layout = QVBoxLayout(opt_group)

        self.chk_header = QCheckBox("첫번째 행을 컬럼 헤더로 사용")
        self.chk_header.setChecked(True)
        self.chk_header.toggled.connect(self.on_paste_text_changed)
        opt_layout.addWidget(self.chk_header)

        opt_layout.addWidget(QLabel("열 간 구분자 (Separator):"))
        self.combo_delim = QComboBox()
        self.combo_delim.addItems([
            "공백 (\" \")",
            "하이픈 (\"-\")",
            "언더바 (\"_\")",
            "콤마 (\", \")",
            "슬래시 (\"/\")",
            "없음 (\"\")",
            "사용자 지정..."
        ])
        self.combo_delim.currentIndexChanged.connect(self.on_delim_changed)
        opt_layout.addWidget(self.combo_delim)

        self.txt_custom_delim = QLineEdit()
        self.txt_custom_delim.setPlaceholderText("사용자 지정 구분자 입력...")
        self.txt_custom_delim.setVisible(False)
        self.txt_custom_delim.textChanged.connect(self.compute_and_render)
        opt_layout.addWidget(self.txt_custom_delim)

        self.chk_trim = QCheckBox("각 데이터 앞뒤 공백 제거 (Trim)")
        self.chk_trim.setChecked(True)
        self.chk_trim.toggled.connect(self.compute_and_render)
        opt_layout.addWidget(self.chk_trim)

        self.chk_skip_empty = QCheckBox("빈 셀(Empty)은 구분자 없이 생략")
        self.chk_skip_empty.toggled.connect(self.compute_and_render)
        opt_layout.addWidget(self.chk_skip_empty)
        left_layout.addWidget(opt_group)

        # Group 3: Detected Column Chips
        chips_group = QGroupBox("3. 감지된 컬럼 (클릭하여 병합 순서에 추가)")
        self.chips_layout = QVBoxLayout(chips_group)
        self.lbl_chips_hint = QLabel("붙여넣은 데이터가 없습니다.")
        self.lbl_chips_hint.setStyleSheet("color: #94a3b8;")
        self.chips_layout.addWidget(self.lbl_chips_hint)
        left_layout.addWidget(chips_group)

        # Group 4: Selected Sequence
        seq_group = QGroupBox("4. 선택된 병합 순서")
        seq_layout = QVBoxLayout(seq_group)
        self.lbl_seq_text = QLabel("컬럼을 클릭하여 병합 순서를 지정하세요.")
        self.lbl_seq_text.setWordWrap(True)
        self.lbl_seq_text.setStyleSheet("color: #fbbf24; font-weight: bold;")
        seq_layout.addWidget(self.lbl_seq_text)

        self.btn_reset_seq = QPushButton("순서 초기화")
        self.btn_reset_seq.clicked.connect(self.reset_sequence)
        seq_layout.addWidget(self.btn_reset_seq)
        left_layout.addWidget(seq_group)

        left_layout.addStretch()
        main_layout.addWidget(left_panel)

        # -------------------------------------------------------------
        # Right Panel: Results & Clipboard Copy
        # -------------------------------------------------------------
        right_panel = QVBoxLayout()

        action_box = QFrame()
        action_box.setStyleSheet("background-color: #1e293b; border-radius: 8px; padding: 12px;")
        action_layout = QHBoxLayout(action_box)

        self.lbl_result_count = QLabel("🔗 병합 결과: 0행")
        self.lbl_result_count.setFont(QFont("맑은 고딕", 10, QFont.Bold))

        self.btn_copy = QPushButton("📋 병합 결과 클립보드 복사 (Ctrl+V Ready)")
        self.btn_copy.setStyleSheet("background-color: #059669; color: white; font-weight: bold; padding: 10px 16px; font-size: 13px;")
        self.btn_copy.clicked.connect(self.copy_results)

        action_layout.addWidget(self.lbl_result_count)
        action_layout.addStretch()
        action_layout.addWidget(self.btn_copy)
        right_panel.addWidget(action_box)

        # Search box
        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("🔍 결과 미리보기 내 검색...")
        self.txt_search.textChanged.connect(self.filter_results)
        right_panel.addWidget(self.txt_search)

        # Data table
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["번호", "병합된 결과 값 (Concat Output)", "원본 소스 데이터 요약"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setAlternatingRowColors(True)
        right_panel.addWidget(self.table)

        main_layout.addLayout(right_panel)

    def on_paste_text_changed(self):
        text = self.txt_paste.toPlainText()
        if not text.strip():
            self.clear_data()
            return

        lines = [line for line in text.splitlines() if line.strip()]
        if not lines:
            self.clear_data()
            return

        first_line = lines[0]
        sep = '\t' if '\t' in first_line else (',' if ',' in first_line else None)

        if sep:
            parsed = [line.split(sep) for line in lines]
        else:
            parsed = [re.split(r'\s{2,}', line) for line in lines]

        max_cols = max(len(r) for r in parsed)

        def get_col_letter(idx):
            res = ""
            while idx >= 0:
                res = chr((idx % 26) + 65) + res
                idx = (idx // 26) - 1
            return res

        if self.chk_header.isChecked() and len(parsed) > 0:
            header_row = parsed[0]
            self.concat_headers = [
                (header_row[i].strip() if i < len(header_row) and header_row[i].strip() else f"열 {get_col_letter(i)}")
                for i in range(max_cols)
            ]
            self.concat_raw_rows = parsed[1:]
        else:
            self.concat_headers = [f"열 {get_col_letter(i)}" for i in range(max_cols)]
            self.concat_raw_rows = parsed

        # Clear existing chip buttons
        while self.chips_layout.count():
            item = self.chips_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        # Add chip buttons
        for idx, h_name in enumerate(self.concat_headers):
            col_let = get_col_letter(idx)
            btn = QPushButton(f"+ [{col_let}] {h_name}")
            btn.setStyleSheet("background-color: #1e3a8a; color: #93c5fd; text-align: left; padding: 6px;")
            btn.clicked.connect(lambda checked=False, col_idx=idx: self.add_column_to_seq(col_idx))
            self.chips_layout.addWidget(btn)

        if not self.selected_indices and len(self.concat_headers) > 0:
            self.selected_indices = [0, 1] if len(self.concat_headers) > 1 else [0]

        self.update_sequence_label()
        self.compute_and_render()

    def add_column_to_seq(self, col_idx):
        self.selected_indices.append(col_idx)
        self.update_sequence_label()
        self.compute_and_render()

    def reset_sequence(self):
        self.selected_indices = []
        self.update_sequence_label()
        self.compute_and_render()

    def update_sequence_label(self):
        def get_col_letter(idx):
            res = ""
            while idx >= 0:
                res = chr((idx % 26) + 65) + res
                idx = (idx // 26) - 1
            return res

        if not self.selected_indices:
            self.lbl_seq_text.setText("선택된 컬럼이 없습니다.")
            return

        parts = []
        for seq_i, col_idx in enumerate(self.selected_indices):
            h_name = self.concat_headers[col_idx] if col_idx < len(self.concat_headers) else f"열 {col_idx}"
            col_let = get_col_letter(col_idx)
            parts.append(f"{seq_i+1}. [{col_let}] {h_name}")

        self.lbl_seq_text.setText(" ➔ ".join(parts))

    def on_delim_changed(self, idx):
        self.txt_custom_delim.setVisible(idx == 6)
        self.compute_and_render()

    def get_delimiter(self):
        idx = self.combo_delim.currentIndex()
        delims = [" ", "-", "_", ", ", "/", "", self.txt_custom_delim.text()]
        return delims[idx] if idx < len(delims) else " "

    def compute_and_render(self):
        if not self.concat_raw_rows or not self.selected_indices:
            self.concat_results = []
            self.table.setRowCount(0)
            self.lbl_result_count.setText("🔗 병합 결과: 0행")
            return

        delim = self.get_delimiter()
        do_trim = self.chk_trim.isChecked()
        skip_empty = self.chk_skip_empty.isChecked()

        def get_col_letter(idx):
            res = ""
            while idx >= 0:
                res = chr((idx % 26) + 65) + res
                idx = (idx // 26) - 1
            return res

        results = []
        for r_idx, row in enumerate(self.concat_raw_rows):
            vals = []
            summary_parts = []
            for col_idx in self.selected_indices:
                val = row[col_idx] if col_idx < len(row) else ""
                if do_trim:
                    val = val.strip()
                if not skip_empty or val != "":
                    vals.append(val)

                h_name = self.concat_headers[col_idx] if col_idx < len(self.concat_headers) else get_col_letter(col_idx)
                summary_parts.append(f"{h_name}: \"{val}\"")

            concat_val = delim.join(vals)
            results.append((r_idx + 1, concat_val, " | ".join(summary_parts)))

        self.concat_results = results
        self.lbl_result_count.setText(f"🔗 병합 결과: {len(results)}행")
        self.render_table()

    def render_table(self):
        query = self.txt_search.text().strip().lower()
        filtered = self.concat_results
        if query:
            filtered = [item for item in self.concat_results if query in item[1].lower() or query in item[2].lower()]

        preview_items = filtered[:100]
        self.table.setRowCount(len(preview_items))
        for row_i, (idx_num, val_str, summary_str) in enumerate(preview_items):
            self.table.setItem(row_i, 0, QTableWidgetItem(str(idx_num)))

            val_item = QTableWidgetItem(val_str)
            val_item.setFont(QFont("맑은 고딕", 10, QFont.Bold))
            val_item.setForeground(Qt.GlobalColor.cyan)
            self.table.setItem(row_i, 1, val_item)

            self.table.setItem(row_i, 2, QTableWidgetItem(summary_str))

    def filter_results(self):
        self.render_table()

    def read_from_clipboard(self):
        text = QApplication.clipboard().text()
        if text:
            self.txt_paste.setPlainText(text)
        else:
            QMessageBox.information(self, "안내", "클립보드에 텍스트 데이터가 없습니다.")

    def clear_data(self):
        self.txt_paste.blockSignals(True)
        self.txt_paste.clear()
        self.txt_paste.blockSignals(False)
        self.concat_raw_rows = []
        self.concat_headers = []
        self.selected_indices = []
        self.concat_results = []
        self.lbl_seq_text.setText("선택된 컬럼이 없습니다.")

        while self.chips_layout.count():
            item = self.chips_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        self.lbl_chips_hint = QLabel("붙여넣은 데이터가 없습니다.")
        self.lbl_chips_hint.setStyleSheet("color: #94a3b8;")
        self.chips_layout.addWidget(self.lbl_chips_hint)
        self.table.setRowCount(0)
        self.lbl_result_count.setText("🔗 병합 결과: 0행")

    def copy_results(self):
        if not self.concat_results:
            QMessageBox.warning(self, "경고", "복사할 병합 결과 데이터가 없습니다.")
            return

        text = "\n".join(item[1] for item in self.concat_results)
        QApplication.clipboard().setText(text)
        QMessageBox.information(
            self, "클립보드 복사",
            f"📋 병합 결과 {len(self.concat_results)}행이 클립보드에 복사되었습니다!\n(Ctrl+V로 엑셀에 붙여넣으세요)"
        )


class SetAnalyzerGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("엑셀 집합 분석 & 컬럼 Concat 병합 툴 (Excel Helper)")
        self.resize(1150, 780)

        self.init_ui()
        self.apply_stylesheet()

    def init_ui(self):
        main_tab_widget = QTabWidget()
        self.setCentralWidget(main_tab_widget)

        self.set_analyzer_widget = SetAnalyzerWidget()
        self.column_concat_widget = ColumnConcatWidget()

        main_tab_widget.addTab(self.set_analyzer_widget, "📊 엑셀 집합 분석 (Set Analyzer)")
        main_tab_widget.addTab(self.column_concat_widget, "🔗 컬럼 Concat / 병합 (Ctrl+V)")

    def apply_stylesheet(self):
        self.setStyleSheet("""
            QMainWindow { background-color: #0f172a; }
            QWidget { color: #f8fafc; font-family: '맑은 고딕'; }
            QGroupBox { font-weight: bold; border: 1px solid #334155; border-radius: 6px; margin-top: 10px; padding-top: 10px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; color: #94a3b8; }
            QPushButton { background-color: #334155; border: none; border-radius: 4px; padding: 8px; color: white; }
            QPushButton:hover { background-color: #475569; }
            QComboBox, QLineEdit, QTextEdit { background-color: #1e293b; border: 1px solid #334155; border-radius: 4px; padding: 6px; color: white; }
            QComboBox QAbstractItemView { background-color: #1e293b; color: white; selection-background-color: #2563eb; selection-color: white; border: 1px solid #334155; }
            QTabWidget::pane { border: 1px solid #334155; background-color: #1e293b; }
            QTabBar::tab { background: #0f172a; padding: 10px 18px; border: 1px solid #334155; font-size: 13px; font-weight: bold; }
            QTabBar::tab:selected { background: #2563eb; color: white; font-weight: bold; }
            QTableWidget { background-color: #1e293b; gridline-color: #334155; border: none; }
            QHeaderView::section { background-color: #0f172a; color: #cbd5e1; font-weight: bold; border: 1px solid #334155; padding: 6px; }
        """)


def run_gui():
    app = QApplication(sys.argv)
    window = SetAnalyzerGUI()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    run_gui()
