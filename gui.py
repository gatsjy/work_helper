import sys
import os
import re
import time
import json
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QCheckBox, QTabWidget, QTableWidget,
    QTableWidgetItem, QFileDialog, QMessageBox, QGroupBox, QHeaderView, QLineEdit,
    QFrame, QTextEdit, QSplashScreen, QProgressBar, QAbstractItemView,
    QGraphicsOpacityEffect, QInputDialog, QSpinBox, QDateEdit, QDialog,
    QRadioButton, QButtonGroup, QFormLayout
)
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QSequentialAnimationGroup, Signal, QDate
from PySide6.QtGui import QFont, QKeySequence, QShortcut
from todo_manager import TodoManager


class CustomHeaderView(QHeaderView):
    """우클릭 컨텍스트 메뉴를 100% 확실하게 팝업시켜주는 QHeaderView 서브클래스"""
    right_clicked = Signal(int, object)

    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)

    def contextMenuEvent(self, event):
        logical_index = self.logicalIndexAt(event.pos())
        if logical_index >= 0:
            self.right_clicked.emit(logical_index, event.globalPos())
        event.accept()


class ToastNotification(QLabel):
    """화면 하단에 부드럽게 타올라 떴다가 사라지는 플로팅 토스트 알림 메시지"""
    def __init__(self, parent_widget, message: str, duration_ms: int = 1800):
        super().__init__(parent_widget)
        self.setText(message)
        self.setFont(QFont("맑은 고딕", 10, QFont.Bold))
        self.setStyleSheet("""
            QLabel {
                background-color: #0f172a;
                color: #38bdf8;
                border: 2px solid #0284c7;
                border-radius: 10px;
                padding: 10px 22px;
            }
        """)
        self.adjustSize()

        # Center horizontally at the bottom of parent widget
        parent_rect = parent_widget.rect()
        x = max(20, (parent_rect.width() - self.width()) // 2)
        y = max(20, parent_rect.height() - self.height() - 40)
        self.move(x, y)

        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)

        self.anim_fade_in = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.anim_fade_in.setDuration(250)
        self.anim_fade_in.setStartValue(0.0)
        self.anim_fade_in.setEndValue(1.0)
        self.anim_fade_in.setEasingCurve(QEasingCurve.OutCubic)

        self.anim_fade_out = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.anim_fade_out.setDuration(450)
        self.anim_fade_out.setStartValue(1.0)
        self.anim_fade_out.setEndValue(0.0)
        self.anim_fade_out.setEasingCurve(QEasingCurve.InCubic)

        self.group = QSequentialAnimationGroup(self)
        self.group.addAnimation(self.anim_fade_in)
        self.group.addPause(duration_ms)
        self.group.addAnimation(self.anim_fade_out)
        self.group.finished.connect(self.deleteLater)

        self.show()
        self.raise_()
        self.group.start()

    @staticmethod
    def show_toast(parent_widget, message: str, duration_ms: int = 1800):
        if parent_widget:
            ToastNotification(parent_widget, message, duration_ms)


class CopyableTableWidget(QTableWidget):
    """셀 드래그/선택 후 Ctrl+C 누를 때 선택된 셀 영역을 클립보드에 TSV 텍스트로 복사하는 QTableWidget"""
    cell_right_clicked = Signal(int, object)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)

    def contextMenuEvent(self, event):
        col_idx = self.columnAt(event.pos().x())
        if col_idx >= 0:
            self.cell_right_clicked.emit(col_idx, event.globalPos())
        super().contextMenuEvent(event)

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.Copy):
            self.copy_selection_to_clipboard()
            event.accept()
        else:
            super().keyPressEvent(event)

    def copy_selection_to_clipboard(self):
        selected_indexes = self.selectedIndexes()
        if not selected_indexes:
            return

        valid_indexes = [idx for idx in selected_indexes if not self.isRowHidden(idx.row())]
        if not valid_indexes:
            return

        rows = sorted(list(set(idx.row() for idx in valid_indexes)))
        cols = sorted(list(set(idx.column() for idx in valid_indexes)))

        lines = []
        for r in rows:
            row_vals = []
            for c in cols:
                item = self.item(r, c)
                row_vals.append(item.text() if item else "")
            lines.append("\t".join(row_vals))

        tsv_text = "\n".join(lines)
        if tsv_text:
            QApplication.clipboard().setText(tsv_text)
            ToastNotification.show_toast(self.window(), f"📋 선택된 {len(valid_indexes)}개 셀 데이터가 클립보드에 복사되었습니다!")


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
        left_panel.setFixedWidth(360)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(8, 8, 8, 8)
        left_layout.setSpacing(14)

        title_box = QHBoxLayout()
        title_label = QLabel("📋 Excel Set Analyzer")
        title_label.setFont(QFont("맑은 고딕", 13, QFont.Bold))
        self.btn_sample = QPushButton("💡 샘플 채우기")
        self.btn_sample.setStyleSheet("background-color: #334155; color: #94a3b8; font-size: 11px; padding: 4px 6px;")
        self.btn_sample.clicked.connect(self.fill_sample_data)
        title_box.addWidget(title_label)
        title_box.addStretch()
        title_box.addWidget(self.btn_sample)
        left_layout.addLayout(title_box)

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

        # Default sample fill
        self.fill_sample_data()

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
        table = CopyableTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["데이터 값", "구분 (출처)", "A컬럼 존재", "B컬럼 존재"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        table.setAlternatingRowColors(True)
        return table

    def fill_sample_data(self):
        sample_a = "USR001\nUSR002\nUSR003\nUSR004\nUSR005"
        sample_b = "USR003\nUSR004\nUSR005\nUSR006\nUSR007"
        self.txt_paste_a.setPlainText(sample_a)
        self.txt_paste_b.setPlainText(sample_b)

    def run_analysis(self):
        raw_text_a = self.txt_paste_a.toPlainText()
        raw_text_b = self.txt_paste_b.toPlainText()

        if not raw_text_a.strip() and not raw_text_b.strip():
            self.analysis_result = None
            for idx, key in enumerate(self.tab_keys):
                self.tables[key].setRowCount(0)
            return

        from excel_processor import ExcelSetProcessor
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
            table.setItem(idx, 0, QTableWidgetItem(str(item['val'])))
            table.setItem(idx, 1, QTableWidgetItem(str(item['origin'])))

            item_a = QTableWidgetItem(item['in_a'])
            item_a.setTextAlignment(Qt.AlignCenter)
            table.setItem(idx, 2, item_a)

            item_b = QTableWidgetItem(item['in_b'])
            item_b.setTextAlignment(Qt.AlignCenter)
            table.setItem(idx, 3, item_b)

    def filter_table(self, query):
        query = query.strip().lower()
        current_table = self.tabs.currentWidget()
        if not current_table:
            return

        for row in range(current_table.rowCount()):
            val_item = current_table.item(row, 0)
            origin_item = current_table.item(row, 1)

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
        ToastNotification.show_toast(self.window(), f"📋 데이터 값 {len(items)}개가 클립보드에 복사되었습니다!")

    def copy_table_tsv(self):
        curr_tab_idx = self.tabs.currentIndex()
        tab_key = self.tab_keys[curr_tab_idx]
        if not self.analysis_result or tab_key not in self.analysis_result:
            return

        items = self.analysis_result[tab_key]
        headers = ["데이터값", "구분(출처)", "A존재", "B존재"]
        rows = [f"{item['val']}\t{item['origin']}\t{item['in_a']}\t{item['in_b']}" for item in items]
        text = "\n".join([ "\t".join(headers) ] + rows)

        QApplication.clipboard().setText(text)
        ToastNotification.show_toast(self.window(), f"📊 표 데이터 {len(items)}행이 클립보드에 복사되었습니다!")


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
        self.btn_sample = QPushButton("💡 샘플 채우기")
        self.btn_sample.setStyleSheet("background-color: #334155; color: #94a3b8; font-size: 11px; padding: 4px 6px;")
        self.btn_sample.clicked.connect(self.fill_sample_data)
        self.btn_clear = QPushButton("초기화")
        self.btn_clear.clicked.connect(self.clear_data)
        btn_box.addWidget(self.btn_sample)
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
            "없음 (\"\")",
            "하이픈 (\"-\")",
            "언더바 (\"_\")",
            "콤마 (\", \")",
            "슬래시 (\"/\")",
            "사용자 지정..."
        ])
        self.combo_delim.currentIndexChanged.connect(self.on_delim_changed)
        opt_layout.addWidget(self.combo_delim)

        self.txt_custom_delim = QLineEdit()
        self.txt_custom_delim.setPlaceholderText("사용자 지정 구분자 입력...")
        self.txt_custom_delim.setVisible(False)
        self.txt_custom_delim.textChanged.connect(self.compute_and_render)
        opt_layout.addWidget(self.txt_custom_delim)

        opt_layout.addWidget(QLabel("고정 접두사 (Prefix):"))
        self.txt_prefix = QLineEdit()
        self.txt_prefix.setPlaceholderText("예: SELECT * FROM  또는  '")
        self.txt_prefix.textChanged.connect(self.compute_and_render)
        self.txt_prefix.textChanged.connect(self.auto_copy_results)
        opt_layout.addWidget(self.txt_prefix)

        opt_layout.addWidget(QLabel("고정 접미사 (Suffix):"))
        self.txt_suffix = QLineEdit()
        self.txt_suffix.setPlaceholderText("예: ;  또는  ',")
        self.txt_suffix.textChanged.connect(self.compute_and_render)
        self.txt_suffix.textChanged.connect(self.auto_copy_results)
        opt_layout.addWidget(self.txt_suffix)

        # SQL Presets
        preset_box = QHBoxLayout()
        btn_preset_select = QPushButton("SQL SELECT")
        btn_preset_select.setStyleSheet("background-color: #1e3a8a; color: #93c5fd; font-size: 11px; padding: 4px;")
        btn_preset_select.clicked.connect(lambda: self.apply_preset("SELECT * FROM ", ";"))

        btn_preset_in = QPushButton("SQL IN ('v',)")
        btn_preset_in.setStyleSheet("background-color: #1e3a8a; color: #93c5fd; font-size: 11px; padding: 4px;")
        btn_preset_in.clicked.connect(lambda: self.apply_preset("'", "',"))

        btn_preset_semi = QPushButton("; 세미콜론")
        btn_preset_semi.setStyleSheet("background-color: #1e3a8a; color: #93c5fd; font-size: 11px; padding: 4px;")
        btn_preset_semi.clicked.connect(lambda: self.apply_preset("", ";"))

        preset_box.addWidget(btn_preset_select)
        preset_box.addWidget(btn_preset_in)
        preset_box.addWidget(btn_preset_semi)
        opt_layout.addLayout(preset_box)

        self.chk_trim = QCheckBox("각 데이터 앞뒤 공백 제거 (Trim)")
        self.chk_trim.setChecked(True)
        self.chk_trim.toggled.connect(self.compute_and_render)
        opt_layout.addWidget(self.chk_trim)

        self.chk_skip_empty = QCheckBox("빈 셀(Empty)은 구분자 없이 생략")
        self.chk_skip_empty.toggled.connect(self.compute_and_render)
        opt_layout.addWidget(self.chk_skip_empty)

        self.chk_drop_duplicates = QCheckBox("중복 행 제거 (Drop Duplicates)")
        self.chk_drop_duplicates.toggled.connect(self.compute_and_render)
        opt_layout.addWidget(self.chk_drop_duplicates)
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

        # Interactive Data table
        self.table = CopyableTableWidget()
        self.table.setAlternatingRowColors(True)

        self.header_view = CustomHeaderView(Qt.Horizontal, self.table)
        self.header_view.setSectionResizeMode(QHeaderView.Interactive)
        self.header_view.sectionClicked.connect(self.on_table_header_clicked)
        self.header_view.right_clicked.connect(self.popup_column_context_menu)
        self.table.setHorizontalHeader(self.header_view)
        self.table.cell_right_clicked.connect(self.popup_column_context_menu)
        right_panel.addWidget(self.table)

        main_layout.addLayout(right_panel)

        # Default sample fill
        self.fill_sample_data()

    def popup_column_context_menu(self, logical_index: int, global_pos):
        menu = QMenu(self)
        act_autofit = menu.addAction("📐 전체 열 너비 내용에 맞게 자동 조절")
        menu.addSeparator()

        if logical_index == 0:
            act_copy = menu.addAction("📋 병합 결과 전체 복사 (Ctrl+C)")
            act = menu.exec(global_pos)
            if act == act_autofit:
                self.table.resizeColumnsToContents()
            elif act == act_copy:
                self.copy_results()
        else:
            col_idx = logical_index - 1
            h_name = self.concat_headers[col_idx] if col_idx < len(self.concat_headers) else f"열 {col_idx}"

            act_insert = menu.addAction(f"➕ [{h_name}] 우측에 새 열 삽입")
            act_delete = menu.addAction(f"🗑️ [{h_name}] 열 삭제")

            act = menu.exec(global_pos)
            if act == act_autofit:
                self.table.resizeColumnsToContents()
            elif act == act_insert:
                self.insert_column_right(col_idx)
            elif act == act_delete:
                self.delete_column_at(col_idx)

    def insert_column_right(self, col_idx: int):
        if col_idx >= len(self.concat_headers):
            return

        new_header_name = f"새 열_{len(self.concat_headers)+1}"

        insert_idx = col_idx + 1
        self.concat_headers.insert(insert_idx, new_header_name)
        for row in self.concat_raw_rows:
            row.insert(insert_idx, "")

        new_seq = []
        for idx in self.selected_indices:
            if idx >= insert_idx:
                new_seq.append(idx + 1)
            else:
                new_seq.append(idx)
        new_seq.append(insert_idx)
        self.selected_indices = new_seq

        self.render_column_chips()
        self.update_sequence_label()
        self.compute_and_render()
        self.auto_copy_results()
        ToastNotification.show_toast(self.window(), f"➕ '{new_header_name}' 열이 우측에 삽입되었습니다.")

    def delete_column_at(self, col_idx: int):
        if col_idx >= len(self.concat_headers):
            return

        del_name = self.concat_headers[col_idx]
        del self.concat_headers[col_idx]
        for row in self.concat_raw_rows:
            if col_idx < len(row):
                del row[col_idx]

        new_seq = []
        for idx in self.selected_indices:
            if idx < col_idx:
                new_seq.append(idx)
            elif idx > col_idx:
                new_seq.append(idx - 1)
        self.selected_indices = new_seq

        self.render_column_chips()
        self.update_sequence_label()
        self.compute_and_render()
        self.auto_copy_results()
        ToastNotification.show_toast(self.window(), f"🗑️ '{del_name}' 열이 삭제되었습니다.")

    def prompt_add_column(self):
        if not self.concat_headers:
            QMessageBox.warning(self, "경고", "먼저 데이터를 붙여넣으세요.")
            return
        items = [f"[{i+1}] {h}" for i, h in enumerate(self.concat_headers)]
        item, ok = QInputDialog.getItem(self, "열 추가", "어느 컬럼 우측에 새 열을 추가할까요?:", items, len(items)-1, False)
        if ok and item:
            idx = items.index(item)
            self.insert_column_right(idx)

    def prompt_delete_column(self):
        if not self.concat_headers:
            return
        items = [f"[{i+1}] {h}" for i, h in enumerate(self.concat_headers)]
        item, ok = QInputDialog.getItem(self, "열 삭제", "삭제할 컬럼 선택:", items, 0, False)
        if ok and item:
            idx = items.index(item)
            self.delete_column_at(idx)

    def on_table_header_clicked(self, logical_index: int):
        # Click header to add column to sequence
        if logical_index >= 1:
            col_idx = logical_index - 1
            self.add_column_to_seq(col_idx)

    def on_paste_text_changed(self):
        text = self.txt_paste.toPlainText()
        if not text.strip():
            self.clear_data()
            return

        lines = [line for line in text.splitlines() if line.strip()]
        if not lines:
            self.clear_data()
            return

        first_10_lines = lines[:10]
        has_tabs = any('\t' in line for line in first_10_lines)
        has_commas = any(',' in line for line in first_10_lines)

        if has_tabs or has_commas:
            sep = '\t' if has_tabs else ','
            parsed = [line.split(sep) for line in lines]
        else:
            # Smart 1D Vertical Stream Auto-Detection
            num_lines = len(lines)
            detected_k = 0
            for k in range(2, 31):
                if num_lines >= k * 2:
                    matches = 0
                    checks = 0
                    for idx in range(k, num_lines - k, k):
                        checks += 1
                        if lines[idx] == lines[idx + k]:
                            matches += 1
                    if checks >= 2 and (matches / checks) >= 0.5:
                        detected_k = k
                        break

            if detected_k >= 2:
                parsed = []
                for i in range(0, num_lines, detected_k):
                    chunk = lines[i:i + detected_k]
                    if len(chunk) < detected_k:
                        chunk.extend([""] * (detected_k - len(chunk)))
                    parsed.append(chunk)
            else:
                multi_space_lines = [l for l in lines[:20] if re.search(r'\s{2,}', l)]
                if len(multi_space_lines) >= min(len(lines), 4):
                    parsed = [re.split(r'\s{2,}', line) for line in lines]
                else:
                    parsed = [[line] for line in lines]

        max_cols = max((len(r) for r in parsed), default=1)

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

        self.selected_indices = list(range(len(self.concat_headers)))
        self.is_custom_sequence = False

        self.render_column_chips()
        self.update_sequence_label()
        self.compute_and_render()
        self.auto_copy_results()

    def render_column_chips(self):
        while self.chips_layout.count():
            item = self.chips_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        if not self.concat_headers:
            self.lbl_chips_hint = QLabel("붙여넣은 데이터가 없습니다.")
            self.lbl_chips_hint.setStyleSheet("color: #94a3b8;")
            self.chips_layout.addWidget(self.lbl_chips_hint)
            return

        def get_col_letter(idx):
            res = ""
            while idx >= 0:
                res = chr((idx % 26) + 65) + res
                idx = (idx // 26) - 1
            return res

        chips_sub_layout = QVBoxLayout()
        chips_sub_layout.setSpacing(6)

        for col_idx, h_name in enumerate(self.concat_headers):
            col_let = get_col_letter(col_idx)
            is_selected = col_idx in self.selected_indices
            if is_selected:
                seq_pos = self.selected_indices.index(col_idx) + 1
                btn_text = f"✓ [{seq_pos}] [{col_let}] {h_name}"
                btn_style = """
                    QPushButton {
                        background-color: #2563eb;
                        color: #ffffff;
                        border: 1px solid #3b82f6;
                        border-radius: 6px;
                        padding: 6px 12px;
                        text-align: left;
                        font-weight: bold;
                    }
                    QPushButton:hover {
                        background-color: #1d4ed8;
                    }
                """
            else:
                btn_text = f"+ [{col_let}] {h_name}"
                btn_style = """
                    QPushButton {
                        background-color: #1e293b;
                        color: #94a3b8;
                        border: 1px solid #334155;
                        border-radius: 6px;
                        padding: 6px 12px;
                        text-align: left;
                    }
                    QPushButton:hover {
                        background-color: #334155;
                        color: #ffffff;
                    }
                """
            btn = QPushButton(btn_text)
            btn.setStyleSheet(btn_style)
            btn.clicked.connect(lambda _, c=col_idx: self.add_column_to_seq(c))
            btn.setContextMenuPolicy(Qt.CustomContextMenu)
            btn.customContextMenuRequested.connect(lambda pos, c=col_idx, b=btn: self.popup_column_context_menu(c + 1, b.mapToGlobal(pos)))
            chips_sub_layout.addWidget(btn)

        self.chips_layout.addLayout(chips_sub_layout)

    def add_column_to_seq(self, col_idx: int):
        if not self.is_custom_sequence:
            self.selected_indices = [col_idx]
            self.is_custom_sequence = True
        else:
            if col_idx in self.selected_indices:
                self.selected_indices.remove(col_idx)
            else:
                self.selected_indices.append(col_idx)

        self.render_column_chips()
        self.update_sequence_label()
        self.compute_and_render()
        self.auto_copy_results()

    def reset_sequence(self):
        self.selected_indices = []
        self.is_custom_sequence = True
        self.render_column_chips()
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
        self.auto_copy_results()

    def fill_sample_data(self):
        sample_text = (
            "RCPTSTAT\tUNCORCPTFLAG\n"
            "Y\t1C\n"
            "Y\t1C\n"
            "Y\t1C\n"
            "Y\t1C\n"
            "Y\t1C\n"
            "Y\t1C\n"
            "Y\t1C\n"
            "Y\t1C\n"
            "Y\t1C\n"
            "Y\t1C"
        )
        self.txt_paste.setPlainText(sample_text)

    def get_delimiter(self):
        idx = self.combo_delim.currentIndex()
        delims = [" ", "", "-", "_", ", ", "/", self.txt_custom_delim.text()]
        return delims[idx] if idx < len(delims) else " "

    def apply_preset(self, pref: str, suff: str):
        self.txt_prefix.setText(pref)
        self.txt_suffix.setText(suff)
        self.compute_and_render()
        self.auto_copy_results()

    def compute_and_render(self):
        if not self.concat_raw_rows or not self.selected_indices:
            self.concat_results = []
            self.table.setRowCount(0)
            self.lbl_result_count.setText("🔗 병합 결과: 0행")
            return

        delim = self.get_delimiter()
        do_trim = self.chk_trim.isChecked()
        skip_empty = self.chk_skip_empty.isChecked()
        drop_duplicates = self.chk_drop_duplicates.isChecked()
        prefix = self.txt_prefix.text()
        suffix = self.txt_suffix.text()

        def get_col_letter(idx):
            res = ""
            while idx >= 0:
                res = chr((idx % 26) + 65) + res
                idx = (idx // 26) - 1
            return res

        seen_results = set()
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

            concat_val = prefix + delim.join(vals) + suffix
            if drop_duplicates:
                if concat_val in seen_results:
                    continue
                seen_results.add(concat_val)

            results.append((r_idx, concat_val, row))

        self.concat_results = results
        self.lbl_result_count.setText(f"🔗 병합 결과: {len(results)}행")
        self.render_table()

    def render_table(self):
        def get_col_letter(idx):
            res = ""
            while idx >= 0:
                res = chr((idx % 26) + 65) + res
                idx = (idx // 26) - 1
            return res

        # Table headers: 0: 병합 결과 (Concat Output), 1..N: Original Source Columns
        headers = ["✨ 병합 결과 (Concat Output)"]
        for idx, h_name in enumerate(self.concat_headers):
            col_let = get_col_letter(idx)
            # Add sequence tag if selected
            seq_order = [i+1 for i, s in enumerate(self.selected_indices) if s == idx]
            seq_prefix = f"[{','.join(map(str, seq_order))}] " if seq_order else "+ "
            headers.append(f"{seq_prefix}[{col_let}] {h_name}")

        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(False)

        query = self.txt_search.text().strip().lower()
        filtered_results = self.concat_results
        if query:
            filtered_results = [
                res for res in self.concat_results
                if query in res[1].lower() or any(query in str(c).lower() for c in res[2])
            ]

        preview_results = filtered_results[:500]
        self.table.setRowCount(len(preview_results))

        for row_i, (orig_r_idx, concat_val, raw_row) in enumerate(preview_results):
            val_item = QTableWidgetItem(concat_val)
            val_item.setFont(QFont("맑은 고딕", 10, QFont.Bold))
            val_item.setForeground(Qt.GlobalColor.cyan)
            self.table.setItem(row_i, 0, val_item)

            for c_i, h_name in enumerate(self.concat_headers):
                cell_val = raw_row[c_i] if c_i < len(raw_row) else ""
                cell_item = QTableWidgetItem(cell_val)
                if c_i in self.selected_indices:
                    cell_item.setBackground(Qt.GlobalColor.darkBlue)
                self.table.setItem(row_i, 1 + c_i, cell_item)

    def filter_results(self):
        self.render_table()

    def auto_copy_results(self):
        if self.concat_results:
            text = "\n".join(item[1] for item in self.concat_results)
            QApplication.clipboard().setText(text)
            self.lbl_result_count.setText(f"🔗 병합 결과: {len(self.concat_results)}행 (📋 클립보드 자동 복사 완료!)")
            ToastNotification.show_toast(self.window(), f"🔗 병합 결과 {len(self.concat_results)}행이 클립보드에 복사되었습니다!")

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
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["✨ 병합 결과 (Concat Output)", "원본 소스 데이터 요약"])
        self.lbl_result_count.setText("🔗 병합 결과: 0행")

    def copy_results(self):
        if not self.concat_results:
            QMessageBox.warning(self, "경고", "복사할 병합 결과 데이터가 없습니다.")
            return

        text = "\n".join(item[1] for item in self.concat_results)
        QApplication.clipboard().setText(text)
        ToastNotification.show_toast(self.window(), f"📋 병합 결과 {len(self.concat_results)}행이 클립보드에 복사되었습니다!")


class TodoListWidget(QWidget):
    """스마트 Todo List & 자동 일일 이월 (Daily Rollover) GUI 위젯 (gatsjy/todolist 소스 충실 반영)"""
    def __init__(self):
        super().__init__()
        self.manager = TodoManager()
        self.current_filter = "today"
        self.init_ui()
        self.load_and_render()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(16, 16, 16, 16)

        # 1. Top Banner Box
        banner_box = QGroupBox("📝 스마트 Todo List & 자동 일일 이월 (Daily Rollover)")
        banner_layout = QHBoxLayout(banner_box)

        info_layout = QVBoxLayout()
        lbl_subtitle = QLabel("미완료된 할 일은 하루가 지나면 자동으로 오늘 날짜로 이월되며 '🔄 N일 이월됨' 뱃지가 표시됩니다.")
        lbl_subtitle.setStyleSheet("color: #94a3b8; font-size: 11px;")
        info_layout.addWidget(lbl_subtitle)

        stats_sub_layout = QHBoxLayout()
        self.lbl_stats_today = QLabel("🔵 오늘 할 일: 0개")
        self.lbl_stats_today.setStyleSheet("color: #60a5fa; font-weight: bold; font-size: 12px;")

        self.lbl_stats_rolled = QLabel("🔄 이월된 항목: 0개")
        self.lbl_stats_rolled.setStyleSheet("color: #f59e0b; font-weight: bold; font-size: 12px;")

        self.lbl_stats_pending = QLabel("⏳ 미완료: 0개")
        self.lbl_stats_pending.setStyleSheet("color: #ef4444; font-weight: bold; font-size: 12px;")

        stats_sub_layout.addWidget(self.lbl_stats_today)
        stats_sub_layout.addWidget(self.lbl_stats_rolled)
        stats_sub_layout.addWidget(self.lbl_stats_pending)
        stats_sub_layout.addStretch()
        info_layout.addLayout(stats_sub_layout)

        self.lbl_progress = QLabel("오늘 달성률: 0% (0/0 완료)")
        self.lbl_progress.setStyleSheet("color: #34d399; font-size: 11px; font-weight: bold;")
        info_layout.addWidget(self.lbl_progress)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(10)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar { background-color: #0f172a; border: 1px solid #334155; border-radius: 5px; }
            QProgressBar::chunk { background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #10b981, stop:1 #3b82f6); border-radius: 4px; }
        """)
        info_layout.addWidget(self.progress_bar)
        banner_layout.addLayout(info_layout, stretch=3)

        sim_layout = QVBoxLayout()
        btn_simulate = QPushButton("⚡ 다음날로 시뮬레이션\n(이월 테스트)")
        btn_simulate.setStyleSheet("background-color: #d97706; color: white; font-weight: bold; padding: 10px 14px; font-size: 11px;")
        btn_simulate.setToolTip("미완료 항목의 마감일을 어제로 변경하여 다음날 실행 시 이월 동작을 즉시 테스트합니다.")
        btn_simulate.clicked.connect(self.simulate_rollover)
        sim_layout.addWidget(btn_simulate)
        banner_layout.addLayout(sim_layout, stretch=1)

        main_layout.addWidget(banner_box)

        # 2. Add Task Row
        add_box = QGroupBox("➕ 새 할 일 추가")
        add_layout = QHBoxLayout(add_box)

        self.txt_title = QLineEdit()
        self.txt_title.setPlaceholderText("새로운 할 일을 입력하세요... (Enter키 누르면 추가)")
        self.txt_title.returnPressed.connect(self.add_task)

        self.combo_category = QComboBox()
        self.combo_category.addItems(["일반", "업무", "개인", "공부", "기타"])

        self.combo_priority = QComboBox()
        self.combo_priority.addItems(["보통", "높음", "낮음"])

        btn_add = QPushButton("➕ 추가")
        btn_add.setStyleSheet("background-color: #2563eb; color: white; font-weight: bold; padding: 6px 16px;")
        btn_add.clicked.connect(self.add_task)

        add_layout.addWidget(self.txt_title, stretch=3)
        add_layout.addWidget(QLabel("카테고리:"))
        add_layout.addWidget(self.combo_category)
        add_layout.addWidget(QLabel("우선순위:"))
        add_layout.addWidget(self.combo_priority)
        add_layout.addWidget(btn_add)
        main_layout.addWidget(add_box)

        # 3. Filter & Search Bar
        filter_box = QHBoxLayout()

        self.btn_filter_today = QPushButton("📅 오늘 할 일")
        self.btn_filter_rollover = QPushButton("🔄 이월된 항목")
        self.btn_filter_pending = QPushButton("⏳ 미완료")
        self.btn_filter_completed = QPushButton("✅ 완료됨")
        self.btn_filter_all = QPushButton("📋 전체")

        self.filter_buttons = {
            "today": self.btn_filter_today,
            "rollover": self.btn_filter_rollover,
            "pending": self.btn_filter_pending,
            "completed": self.btn_filter_completed,
            "all": self.btn_filter_all
        }

        for f_key, btn in self.filter_buttons.items():
            btn.setCheckable(True)
            btn.clicked.connect(lambda _, key=f_key: self.set_filter(key))
            filter_box.addWidget(btn)

        self.btn_filter_today.setChecked(True)
        filter_box.addSpacing(20)

        self.combo_filter_cat = QComboBox()
        self.combo_filter_cat.addItems(["전체 카테고리", "일반", "업무", "개인", "공부", "기타"])
        self.combo_filter_cat.currentTextChanged.connect(lambda _: self.load_and_render())
        filter_box.addWidget(self.combo_filter_cat)

        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("🔍 검색어 입력...")
        self.txt_search.textChanged.connect(lambda _: self.load_and_render())
        filter_box.addWidget(self.txt_search)

        main_layout.addLayout(filter_box)

        # 4. Tasks Table View
        self.table = CopyableTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["선택/완료", "우선순위", "카테고리", "할 일 내용", "마감일 / 이월 뱃지", "관리"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.setAlternatingRowColors(True)

        main_layout.addWidget(self.table)
        self.update_filter_button_styles()

    def set_filter(self, filter_key):
        self.current_filter = filter_key
        for f_key, btn in self.filter_buttons.items():
            btn.setChecked(f_key == filter_key)
        self.update_filter_button_styles()
        self.load_and_render()

    def update_filter_button_styles(self):
        for f_key, btn in self.filter_buttons.items():
            if f_key == self.current_filter:
                btn.setStyleSheet("background-color: #2563eb; color: white; font-weight: bold; border-radius: 4px; padding: 6px 12px;")
            else:
                btn.setStyleSheet("background-color: #1e293b; color: #94a3b8; border: 1px solid #334155; border-radius: 4px; padding: 6px 12px;")

    def add_task(self):
        title = self.txt_title.text().strip()
        if not title:
            return

        cat = self.combo_category.currentText()
        priority = self.combo_priority.currentText()

        self.manager.add_task(title=title, category=cat, priority=priority)
        self.txt_title.clear()
        ToastNotification.show_toast(self.window(), f"➕ '{title}' 할 일이 추가되었습니다.")
        self.load_and_render()

    def toggle_task(self, task_id):
        task = self.manager.toggle_complete(task_id)
        if task:
            msg = "✅ 할 일이 완료 처리되었습니다." if task["completed"] else "↩️ 완료 해제되었습니다."
            ToastNotification.show_toast(self.window(), msg)
        self.load_and_render()

    def delete_task(self, task_id, title):
        reply = QMessageBox.question(self, "할 일 삭제", f"'{title}' 할 일을 정말 삭제하시겠습니까?", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.manager.delete_task(task_id)
            ToastNotification.show_toast(self.window(), f"🗑️ '{title}' 할 일이 삭제되었습니다.")
            self.load_and_render()

    def simulate_rollover(self):
        count = self.manager.simulate_next_day()
        if count > 0:
            ToastNotification.show_toast(self.window(), f"⚡ {count}개 미완료 항목이 어제 날짜로 설정된 후 오늘 날짜로 이월되었습니다!")
        else:
            ToastNotification.show_toast(self.window(), "⚡ 이월할 미완료 항목이 없습니다.")
        self.load_and_render()

    def load_and_render(self):
        cat_filter = self.combo_filter_cat.currentText()
        query = self.txt_search.text().strip()

        tasks = self.manager.get_filtered_tasks(self.current_filter, cat_filter, query)
        stats = self.manager.get_stats()

        self.lbl_stats_today.setText(f"🔵 오늘 할 일: {stats['total_today']}개 (완료 {stats['completed_today']}개)")
        self.lbl_stats_rolled.setText(f"🔄 이월된 항목: {stats['total_rolled_over']}개")
        self.lbl_stats_pending.setText(f"⏳ 미완료: {stats['total_pending']}개")

        pct = stats["progress_pct"]
        self.lbl_progress.setText(f"오늘 달성률: {pct}% ({stats['completed_today']}/{stats['total_today']} 완료)")
        self.progress_bar.setValue(pct)

        self.table.setRowCount(len(tasks))
        for row_i, task in enumerate(tasks):
            # Col 0: Checkbox
            chk = QCheckBox()
            chk.setChecked(task.get("completed", False))
            chk.setStyleSheet("margin-left: 10px;")
            chk.toggled.connect(lambda _, t_id=task["id"]: self.toggle_task(t_id))

            chk_widget = QWidget()
            c_layout = QHBoxLayout(chk_widget)
            c_layout.addWidget(chk)
            c_layout.setAlignment(Qt.AlignCenter)
            c_layout.setContentsMargins(0, 0, 0, 0)
            self.table.setIndexWidget(self.table.model().index(row_i, 0), chk_widget)

            # Col 1: Priority Badge
            p = task.get("priority", "보통")
            p_text = f"🔥 {p}" if p == "높음" else (f"🌱 {p}" if p == "낮음" else f"⚡ {p}")
            item_p = QTableWidgetItem(p_text)
            item_p.setTextAlignment(Qt.AlignCenter)
            if p == "높음":
                item_p.setForeground(Qt.GlobalColor.red)
            elif p == "낮음":
                item_p.setForeground(Qt.GlobalColor.green)
            else:
                item_p.setForeground(Qt.GlobalColor.yellow)
            self.table.setItem(row_i, 1, item_p)

            # Col 2: Category Badge
            cat = task.get("category", "일반")
            item_c = QTableWidgetItem(f"🏷️ {cat}")
            item_c.setTextAlignment(Qt.AlignCenter)
            item_c.setForeground(Qt.GlobalColor.cyan)
            self.table.setItem(row_i, 2, item_c)

            # Col 3: Title
            title = task.get("title", "")
            item_t = QTableWidgetItem(title)
            if task.get("completed", False):
                font = item_t.font()
                font.setStrikeOut(True)
                item_t.setFont(font)
                item_t.setForeground(Qt.GlobalColor.gray)
            else:
                font = item_t.font()
                font.setBold(True)
                item_t.setFont(font)
            self.table.setItem(row_i, 3, item_t)

            # Col 4: Due Date & Rollover Badge
            due = task.get("due_date", "")
            roll_cnt = task.get("rollover_count", 0)
            roll_badge = f" 🔄 {roll_cnt}일 이월됨" if roll_cnt > 0 and not task.get("completed", False) else ""
            item_d = QTableWidgetItem(f"{due}{roll_badge}")
            item_d.setTextAlignment(Qt.AlignCenter)
            if roll_cnt > 0 and not task.get("completed", False):
                item_d.setForeground(Qt.GlobalColor.magenta)
            self.table.setItem(row_i, 4, item_d)

            # Col 5: Delete Action
            act_widget = QWidget()
            act_layout = QHBoxLayout(act_widget)
            act_layout.setContentsMargins(2, 2, 2, 2)
            act_layout.setAlignment(Qt.AlignCenter)

            btn_del = QPushButton("🗑️ 삭제")
            btn_del.setStyleSheet("background-color: #991b1b; color: #fca5a5; font-size: 11px; padding: 2px 8px;")
            btn_del.clicked.connect(lambda _, t_id=task["id"], t_title=task["title"]: self.delete_task(t_id, t_title))

            act_layout.addWidget(btn_del)
            self.table.setIndexWidget(self.table.model().index(row_i, 5), act_widget)

        self.table.resizeColumnsToContents()


class SetAnalyzerGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("엑셀 집합 분석 & 컬럼 Concat 병합 & Todo List 툴 (Excel Helper)")
        self.resize(1180, 800)

        self.init_ui()
        self.apply_stylesheet()

    def init_ui(self):
        self.main_tab_widget = QTabWidget()
        self.setCentralWidget(self.main_tab_widget)

        self.set_analyzer_widget = SetAnalyzerWidget()
        self.column_concat_widget = ColumnConcatWidget()
        self.todo_list_widget = TodoListWidget()

        self.main_tab_widget.addTab(self.set_analyzer_widget, "📊 엑셀 집합 분석 (F1)")
        self.main_tab_widget.addTab(self.column_concat_widget, "🔗 컬럼 Concat / SQL 쿼리 생성기 (F2)")
        self.main_tab_widget.addTab(self.todo_list_widget, "📝 스마트 Todo List (F3)")

        # Program Close / Exit Button on top right corner of Tab Widget
        btn_exit = QPushButton("❌ 프로그램 종료")
        btn_exit.setStyleSheet("""
            QPushButton {
                background-color: #dc2626;
                color: white;
                font-weight: bold;
                padding: 6px 14px;
                font-size: 12px;
                border-radius: 4px;
                margin-right: 6px;
            }
            QPushButton:hover {
                background-color: #b91c1c;
            }
        """)
        btn_exit.setToolTip("프로그램을 종료합니다 (Ctrl+Q)")
        btn_exit.clicked.connect(self.close_application)
        self.main_tab_widget.setCornerWidget(btn_exit, Qt.TopRightCorner)

        # Keyboard Shortcuts: F1 -> Tab 0, F2 -> Tab 1, F3 -> Tab 2, Ctrl+Q -> Exit
        self.shortcut_f1 = QShortcut(QKeySequence("F1"), self)
        self.shortcut_f1.activated.connect(lambda: self.main_tab_widget.setCurrentIndex(0))

        self.shortcut_f2 = QShortcut(QKeySequence("F2"), self)
        self.shortcut_f2.activated.connect(lambda: self.main_tab_widget.setCurrentIndex(1))

        self.shortcut_f3 = QShortcut(QKeySequence("F3"), self)
        self.shortcut_f3.activated.connect(lambda: self.main_tab_widget.setCurrentIndex(2))

        self.shortcut_exit = QShortcut(QKeySequence("Ctrl+Q"), self)
        self.shortcut_exit.activated.connect(self.close_application)

    def close_application(self):
        reply = QMessageBox.question(self, "프로그램 종료", "ExcelSetAnalyzer 프로그램을 종료하시겠습니까?", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            QApplication.quit()

    def apply_stylesheet(self):
        self.setStyleSheet("""
            QMainWindow { background-color: #0f172a; }
            QWidget { color: #f8fafc; font-family: '맑은 고딕'; }
            QGroupBox { font-weight: bold; border: 1px solid #334155; border-radius: 6px; margin-top: 10px; padding-top: 10px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; color: #94a3b8; }
            QPushButton { background-color: #334155; border: none; border-radius: 4px; padding: 8px; color: white; }
            QPushButton:hover { background-color: #475569; }
            QComboBox, QLineEdit, QTextEdit { background-color: #1e293b; border: 1px solid #334155; border-radius: 4px; padding: 6px; color: #f8fafc; }
            QComboBox QAbstractItemView { background-color: #1e293b; color: #f8fafc; selection-background-color: #2563eb; selection-color: #ffffff; border: 1px solid #334155; }
            QComboBox QAbstractItemView::item { background-color: #1e293b; color: #f8fafc; padding: 6px; }
            QComboBox QAbstractItemView::item:selected { background-color: #2563eb; color: #ffffff; }
            QSpinBox { background-color: #1e293b; border: 1px solid #334155; border-radius: 4px; padding: 4px 6px; color: #f8fafc; font-weight: bold; }
            QSpinBox::up-button, QSpinBox::down-button { background-color: #334155; border: 1px solid #475569; border-radius: 2px; }
            QSpinBox::up-button:hover, QSpinBox::down-button:hover { background-color: #2563eb; }

            QTabWidget::pane { border: 1px solid #334155; background-color: #1e293b; }
            QTabBar::tab { background: #0f172a; padding: 10px 18px; border: 1px solid #334155; font-size: 13px; font-weight: bold; color: #cbd5e1; }
            QTabBar::tab:selected { background: #2563eb; color: #ffffff; font-weight: bold; }

            /* Table & Corner Styling (Fix Gray Corner Bug) */
            QTableWidget { background-color: #1e293b; gridline-color: #334155; border: none; color: #f8fafc; }
            QTableWidget::item:selected { background-color: #2563eb; color: #ffffff; }
            QTableCornerButton::section { background-color: #0f172a; border: 1px solid #334155; }
            QHeaderView { background-color: #0f172a; border: none; }
            QHeaderView::section { background-color: #0f172a; color: #cbd5e1; font-weight: bold; border: 1px solid #334155; padding: 6px; }

            /* QMessageBox, QDialog & ToolTip Styling */
            QMessageBox, QDialog, QMenu { background-color: #1e293b; color: #f8fafc; border: 1px solid #334155; }
            QMenu::item { padding: 8px 20px; border-radius: 4px; }
            QMenu::item:selected { background-color: #2563eb; color: #ffffff; }
            QMessageBox QLabel, QDialog QLabel { color: #f8fafc; font-size: 10pt; font-weight: bold; background-color: transparent; }
            QMessageBox QPushButton, QDialog QPushButton { background-color: #2563eb; color: #ffffff; font-weight: bold; border-radius: 4px; padding: 6px 18px; min-width: 65px; }
            QMessageBox QPushButton:hover, QDialog QPushButton:hover { background-color: #1d4ed8; }
            QToolTip { background-color: #0f172a; color: #f8fafc; border: 1px solid #334155; padding: 4px; }
        """)


class AppSplashScreen(QSplashScreen):
    """프로그램 기동 시 로딩 프로그래스 바를 화면 맨 앞에 보여주는 스플래시 화면"""
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.SplashScreen)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.resize(440, 240)

        # Center on primary screen
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background-color: #0f172a;
                border: 2px solid #2563eb;
                border-radius: 12px;
            }
        """)
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(24, 24, 24, 24)
        frame_layout.setSpacing(10)

        title_lbl = QLabel("📊 Excel Set Analyzer")
        title_lbl.setFont(QFont("맑은 고딕", 16, QFont.Bold))
        title_lbl.setStyleSheet("color: #f8fafc; border: none;")
        title_lbl.setAlignment(Qt.AlignCenter)
        frame_layout.addWidget(title_lbl)

        sub_lbl = QLabel("엑셀 집합 분석 & 컬럼 Concat 병합 툴")
        sub_lbl.setFont(QFont("맑은 고딕", 10))
        sub_lbl.setStyleSheet("color: #94a3b8; border: none;")
        sub_lbl.setAlignment(Qt.AlignCenter)
        frame_layout.addWidget(sub_lbl)

        frame_layout.addStretch()

        self.lbl_status = QLabel("프로그램을 초기화하는 중...")
        self.lbl_status.setFont(QFont("맑은 고딕", 9))
        self.lbl_status.setStyleSheet("color: #60a5fa; border: none;")
        self.lbl_status.setAlignment(Qt.AlignLeft)
        frame_layout.addWidget(self.lbl_status)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(12)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #1e293b;
                border: 1px solid #334155;
                border-radius: 6px;
            }
            QProgressBar::chunk {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2563eb, stop:1 #059669);
                border-radius: 5px;
            }
        """)
        frame_layout.addWidget(self.progress_bar)

        layout.addWidget(frame)

    def set_progress(self, val: int, message: str):
        self.progress_bar.setValue(val)
        self.lbl_status.setText(message)
        QApplication.processEvents()


def run_gui():
    app = QApplication(sys.argv)

    # Launch Splash Screen (force foreground popup)
    splash = AppSplashScreen()
    splash.show()
    splash.raise_()
    splash.activateWindow()

    steps = [
        (20, "코어 분석 엔진 및 패키지 로딩 중..."),
        (45, "PySide6 GUI 컴포넌트 구성 중..."),
        (70, "클립보드 및 집합 연산 엔진 준비 중..."),
        (90, "샘플 데이터 및 테마 초기화 중..."),
        (100, "준비 완료! 메인 화면으로 이동합니다.")
    ]

    for progress, msg in steps:
        splash.set_progress(progress, msg)
        for _ in range(4):
            QApplication.processEvents()
            time.sleep(0.04)

    window = SetAnalyzerGUI()
    # Bring main window to absolute front of screen on launch
    window.setWindowFlags(window.windowFlags() | Qt.WindowStaysOnTopHint)
    window.show()
    window.raise_()
    window.activateWindow()
    splash.finish(window)

    # Reset WindowStaysOnTopHint after 600ms so user can use window normally
    def reset_top_hint():
        window.setWindowFlags(window.windowFlags() & ~Qt.WindowStaysOnTopHint)
        window.show()
        window.raise_()
        window.activateWindow()

    QTimer.singleShot(600, reset_top_hint)

    sys.exit(app.exec())

if __name__ == "__main__":
    run_gui()
