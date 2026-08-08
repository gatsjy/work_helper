# -*- coding: utf-8 -*-
"""
📄 로그 분석 탭

핵심 화면은 '주목할 로그'다. 템플릿 전체 목록이 아니라, 시스템이 골라낸
소수의 항목이 먼저 보여야 "한눈에 파악"이 된다.
전체 목록은 그 다음 탭으로 밀어 둔다.
"""
import os
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QGroupBox,
    QLineEdit, QSpinBox, QComboBox, QFileDialog, QMessageBox, QProgressBar,
    QTextEdit, QTableWidget, QTableWidgetItem, QHeaderView, QTabWidget,
    QSplitter, QFormLayout, QCheckBox, QApplication,
)
from PySide6.QtCore import Qt, QObject, QThread, Signal
from PySide6.QtGui import QFont, QColor

import log_analyzer as la


LEVEL_COLORS = {
    "FATAL": "#f87171",
    "ERROR": "#fb923c",
    "WARN": "#fbbf24",
    "INFO": "#60a5fa",
    "DEBUG": "#94a3b8",
    "TRACE": "#64748b",
    "UNKNOWN": "#cbd5e1",
}

KIND_LABELS = {
    "problem": ("🔴 문제", "#fb923c"),
    "rare": ("🔍 드묾", "#a78bfa"),
    "newcomer": ("🆕 신규", "#34d399"),
    "burst": ("📈 급증", "#f472b6"),
}

KIND_HINTS = {
    "problem": "가장 많이 터진 오류. 지금 무너지고 있는 것.",
    "rare": "몇 번 안 나온 로그. 노이즈에 파묻혀 안 보이던 진짜 신호일 가능성이 높다.",
    "newcomer": "로그 후반부에 처음 나타난 패턴. 새로 생긴 고장.",
    "burst": "문제 로그가 평소보다 크게 튄 구간.",
}


class LogWorker(QObject):
    progress = Signal(int, str)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, path, max_lines, encoding, threshold):
        super().__init__()
        self.path = path
        self.max_lines = max_lines
        self.encoding = encoding
        self.threshold = threshold

    def run(self):
        try:
            report = la.analyze_log(
                self.path,
                max_lines=self.max_lines,
                encoding=self.encoding,
                progress=lambda p, m: self.progress.emit(p, m),
                similarity_threshold=self.threshold,
            )
            self.finished.emit(report)
        except MemoryError:
            self.failed.emit(
                "파일이 너무 커서 메모리에 올릴 수 없습니다.\n"
                "'최대 읽을 줄 수'를 낮춰서 다시 시도하세요."
            )
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class LogAnalyzerWidget(QWidget):

    def __init__(self):
        super().__init__()
        self.report = None
        self.thread = None
        self.worker = None
        self.log_path = None
        self.init_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(16)
        layout.addWidget(self._build_left())
        layout.addWidget(self._build_right(), stretch=1)

    def _build_left(self):
        panel = QWidget()
        panel.setFixedWidth(340)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)

        title = QLabel("📄 로그 분석")
        title.setFont(QFont("맑은 고딕", 13, QFont.Bold))
        layout.addWidget(title)

        desc = QLabel(
            "같은 모양의 로그를 <b>템플릿</b>으로 묶어 수천 줄을 몇 개로 접고, "
            "그중 <b>드물거나 새로 생긴 것</b>을 골라 보여줍니다."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #94a3b8; font-size: 11px;")
        layout.addWidget(desc)

        file_group = QGroupBox("1. 로그 파일")
        file_layout = QVBoxLayout(file_group)
        self.lbl_file = QLabel("선택된 파일이 없습니다.")
        self.lbl_file.setWordWrap(True)
        self.lbl_file.setStyleSheet("color: #fbbf24; font-weight: bold;")
        file_layout.addWidget(self.lbl_file)

        btn_browse = QPushButton("📂 로그 파일 선택...")
        btn_browse.setStyleSheet(
            "background-color: #2563eb; color: white; font-weight: bold; padding: 8px;"
        )
        btn_browse.clicked.connect(self.browse_file)
        file_layout.addWidget(btn_browse)
        layout.addWidget(file_group)

        opt_group = QGroupBox("2. 분석 옵션")
        opt_layout = QFormLayout(opt_group)

        self.combo_encoding = QComboBox()
        self.combo_encoding.addItems(
            ["자동 감지", "utf-8", "cp949", "euc-kr", "utf-8-sig", "utf-16", "latin-1"]
        )
        self.combo_encoding.setToolTip(
            "국내 윈도우 로그는 CP949 인 경우가 많습니다.\n"
            "글자가 깨져 보이면 여기서 직접 지정하세요."
        )
        opt_layout.addRow("인코딩:", self.combo_encoding)

        self.spin_max_lines = QSpinBox()
        self.spin_max_lines.setRange(0, 100_000_000)
        self.spin_max_lines.setSingleStep(50_000)
        self.spin_max_lines.setValue(500_000)
        self.spin_max_lines.setSpecialValueText("제한 없음")
        self.spin_max_lines.setToolTip("0 이면 전체를 읽습니다. 거대한 파일은 제한을 두세요.")
        opt_layout.addRow("최대 줄 수:", self.spin_max_lines)

        self.spin_threshold = QSpinBox()
        self.spin_threshold.setRange(10, 90)
        self.spin_threshold.setValue(40)
        self.spin_threshold.setSuffix(" %")
        self.spin_threshold.setToolTip(
            "템플릿을 같은 것으로 볼 유사도 기준.\n"
            "낮추면 더 크게 뭉치고, 높이면 더 잘게 나뉩니다."
        )
        opt_layout.addRow("템플릿 유사도:", self.spin_threshold)
        layout.addWidget(opt_group)

        self.btn_run = QPushButton("🔍 분석 실행")
        self.btn_run.setFixedHeight(42)
        self.btn_run.setFont(QFont("맑은 고딕", 10, QFont.Bold))
        self.btn_run.setStyleSheet(
            "background-color: #059669; color: white; border-radius: 6px;"
        )
        self.btn_run.clicked.connect(self.start_analysis)
        layout.addWidget(self.btn_run)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setFixedHeight(10)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar { background-color: #0f172a; border: 1px solid #334155; border-radius: 5px; }
            QProgressBar::chunk {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                                  stop:0 #10b981, stop:1 #3b82f6);
                border-radius: 4px;
            }
        """)
        layout.addWidget(self.progress_bar)

        self.lbl_status = QLabel("대기 중 — 로그 파일을 선택하세요.")
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setStyleSheet("color: #38bdf8; font-weight: bold;")
        layout.addWidget(self.lbl_status)

        summary_group = QGroupBox("3. 요약")
        summary_layout = QVBoxLayout(summary_group)
        self.lbl_summary = QLabel("—")
        self.lbl_summary.setWordWrap(True)
        self.lbl_summary.setTextFormat(Qt.RichText)
        self.lbl_summary.setStyleSheet("color: #cbd5e1; font-size: 11px;")
        summary_layout.addWidget(self.lbl_summary)
        layout.addWidget(summary_group)

        layout.addStretch()

        self.btn_copy = QPushButton("📋 분석 요약 복사")
        self.btn_copy.setEnabled(False)
        self.btn_copy.clicked.connect(self.copy_summary)
        layout.addWidget(self.btn_copy)

        return panel

    def _build_right(self):
        splitter = QSplitter(Qt.Vertical)

        self.tabs = QTabWidget()

        # --- 주목할 로그 (핵심 화면) ---
        self.table_highlights = QTableWidget()
        self.table_highlights.setColumnCount(4)
        self.table_highlights.setHorizontalHeaderLabels(
            ["구분", "요약", "로그 패턴", "줄 번호"]
        )
        self.table_highlights.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_highlights.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_highlights.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table_highlights.setAlternatingRowColors(True)
        self.table_highlights.itemSelectionChanged.connect(self.on_highlight_selected)
        self.tabs.addTab(self.table_highlights, "⚠️ 주목할 로그")

        # --- 템플릿 전체 ---
        template_page = QWidget()
        template_layout = QVBoxLayout(template_page)
        template_layout.setContentsMargins(0, 6, 0, 0)

        filter_bar = QHBoxLayout()
        self.txt_filter = QLineEdit()
        self.txt_filter.setPlaceholderText("🔍 템플릿 검색...")
        self.txt_filter.textChanged.connect(self.render_templates)
        filter_bar.addWidget(self.txt_filter)

        self.chk_problems_only = QCheckBox("문제 레벨만 (FATAL/ERROR/WARN)")
        self.chk_problems_only.toggled.connect(self.render_templates)
        filter_bar.addWidget(self.chk_problems_only)
        template_layout.addLayout(filter_bar)

        self.table_templates = QTableWidget()
        self.table_templates.setColumnCount(6)
        self.table_templates.setHorizontalHeaderLabels(
            ["레벨", "건수", "비중", "로그 템플릿", "첫 줄", "마지막 줄"]
        )
        self.table_templates.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_templates.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_templates.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table_templates.setAlternatingRowColors(True)
        self.table_templates.itemSelectionChanged.connect(self.on_template_selected)
        template_layout.addWidget(self.table_templates)
        self.tabs.addTab(template_page, "📋 템플릿 전체")

        # --- 타임라인 ---
        self.table_timeline = QTableWidget()
        self.table_timeline.setColumnCount(4)
        self.table_timeline.setHorizontalHeaderLabels(
            ["시각", "전체", "문제", "분포"]
        )
        self.table_timeline.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_timeline.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table_timeline.setAlternatingRowColors(True)
        self.tabs.addTab(self.table_timeline, "⏱ 타임라인")

        splitter.addWidget(self.tabs)

        detail_group = QGroupBox("선택한 항목의 원본 로그")
        detail_layout = QVBoxLayout(detail_group)
        self.txt_detail = QTextEdit()
        self.txt_detail.setReadOnly(True)
        self.txt_detail.setLineWrapMode(QTextEdit.NoWrap)
        self.txt_detail.setStyleSheet(
            "background-color: #0f172a; color: #cbd5e1;"
            "font-family: Consolas, 'D2Coding', monospace; font-size: 12px;"
        )
        detail_layout.addWidget(self.txt_detail)
        splitter.addWidget(detail_group)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        return splitter

    # ------------------------------------------------------------------
    # 동작
    # ------------------------------------------------------------------
    def browse_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "분석할 로그 파일 선택", "",
            "로그/텍스트 파일 (*.log *.txt *.out *.err);;모든 파일 (*.*)"
        )
        if not path:
            return
        self.log_path = path
        size_mb = os.path.getsize(path) / (1024 * 1024)
        self.lbl_file.setText(f"📄 {Path(path).name}  ({size_mb:,.1f} MB)")
        self.lbl_file.setToolTip(path)
        self.lbl_status.setText("파일 선택됨 — [분석 실행]을 누르세요.")

    def start_analysis(self):
        if self.thread is not None:
            QMessageBox.information(self, "안내", "이미 분석이 실행 중입니다.")
            return
        if not self.log_path:
            QMessageBox.warning(self, "파일 없음", "먼저 로그 파일을 선택하세요.")
            return
        if not os.path.exists(self.log_path):
            QMessageBox.warning(
                self, "파일 없음", "선택한 파일이 더 이상 존재하지 않습니다."
            )
            return

        encoding = self.combo_encoding.currentText()
        encoding = None if encoding == "자동 감지" else encoding

        self.btn_run.setEnabled(False)
        self.progress_bar.setValue(0)
        self.lbl_status.setText("분석 시작...")

        self.worker = LogWorker(
            self.log_path,
            self.spin_max_lines.value(),
            encoding,
            self.spin_threshold.value() / 100.0,
        )
        self.thread = QThread(self)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self.on_progress)
        self.worker.finished.connect(self.on_finished)
        self.worker.failed.connect(self.on_failed)
        self.thread.start()

    def cleanup_thread(self):
        if self.thread:
            self.thread.quit()
            self.thread.wait()
            self.thread.deleteLater()
        if self.worker:
            self.worker.deleteLater()
        self.thread = None
        self.worker = None
        self.btn_run.setEnabled(True)

    def on_progress(self, value, message):
        self.progress_bar.setValue(value)
        self.lbl_status.setText(message)

    def on_failed(self, message):
        self.cleanup_thread()
        self.progress_bar.setValue(0)
        self.lbl_status.setText("❌ 분석 실패")
        QMessageBox.critical(self, "분석 실패", message)

    def on_finished(self, report):
        self.cleanup_thread()
        self.report = report
        self.btn_copy.setEnabled(True)

        self.render_summary()
        self.render_highlights()
        self.render_templates()
        self.render_timeline()

        self.lbl_status.setText(
            f"✅ 완료 — {report.parsed_entries:,}건을 템플릿 "
            f"{len(report.templates):,}개로 요약"
        )
        self.tabs.setCurrentIndex(0)

        if report.truncated:
            QMessageBox.information(
                self, "일부만 읽음",
                f"'최대 줄 수' 제한({self.spin_max_lines.value():,}줄)에 걸려 "
                "파일 앞부분만 분석했습니다.\n"
                "전체를 보려면 제한을 0(제한 없음)으로 두세요."
            )

    # ------------------------------------------------------------------
    # 렌더링
    # ------------------------------------------------------------------
    def render_summary(self):
        report = self.report
        parts = [
            f"<b>줄 수</b> {report.total_lines:,} → <b>사건</b> {report.parsed_entries:,}건",
            f"<b>템플릿</b> {len(report.templates):,}개 "
            f"(<b>{report.compression_ratio:,.0f}:1</b> 압축)",
            f"<b>인코딩</b> {report.encoding}",
        ]
        if report.first_seen and report.last_seen:
            parts.append(
                f"<b>기간</b> {report.first_seen:%Y-%m-%d %H:%M:%S}<br>"
                f"&nbsp;&nbsp;&nbsp;&nbsp;~ {report.last_seen:%Y-%m-%d %H:%M:%S}"
            )

        level_bits = []
        for level in la.LEVEL_ORDER:
            count = report.level_counts.get(level, 0)
            if count:
                color = LEVEL_COLORS.get(level, "#cbd5e1")
                level_bits.append(
                    f"<span style='color:{color}'><b>{level}</b> {count:,}</span>"
                )
        if level_bits:
            parts.append(" · ".join(level_bits))

        self.lbl_summary.setText("<br>".join(parts))

    def render_highlights(self):
        highlights = self.report.highlights
        table = self.table_highlights
        table.setRowCount(len(highlights))

        for row, item in enumerate(highlights):
            label, color = KIND_LABELS.get(item.kind, (item.kind, "#cbd5e1"))

            kind_item = QTableWidgetItem(label)
            kind_item.setForeground(QColor(color))
            kind_item.setToolTip(KIND_HINTS.get(item.kind, ""))
            table.setItem(row, 0, kind_item)

            table.setItem(row, 1, QTableWidgetItem(item.title))

            detail_item = QTableWidgetItem(item.detail)
            detail_item.setToolTip(item.detail)
            table.setItem(row, 2, detail_item)

            line_item = QTableWidgetItem(f"{item.line_no:,}" if item.line_no else "-")
            line_item.setTextAlignment(Qt.AlignCenter)
            table.setItem(row, 3, line_item)

        table.resizeColumnsToContents()
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)

        if not highlights:
            self.txt_detail.setPlainText(
                "특별히 눈에 띄는 로그가 없습니다.\n"
                "'템플릿 전체' 탭에서 직접 살펴보세요."
            )

    def render_templates(self):
        if not self.report:
            return

        query = self.txt_filter.text().strip().lower()
        problems_only = self.chk_problems_only.isChecked()

        templates = self.report.templates
        if problems_only:
            templates = [t for t in templates if t.is_problem]
        if query:
            templates = [t for t in templates if query in t.text.lower()]

        self._visible_templates = templates
        total = max(self.report.parsed_entries, 1)

        table = self.table_templates
        table.setRowCount(len(templates))

        for row, template in enumerate(templates):
            level_item = QTableWidgetItem(template.level)
            level_item.setForeground(QColor(LEVEL_COLORS.get(template.level, "#cbd5e1")))
            level_item.setTextAlignment(Qt.AlignCenter)
            table.setItem(row, 0, level_item)

            count_item = QTableWidgetItem(f"{template.count:,}")
            count_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            table.setItem(row, 1, count_item)

            share = template.count / total * 100
            share_item = QTableWidgetItem(f"{share:5.1f}%")
            share_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            table.setItem(row, 2, share_item)

            text_item = QTableWidgetItem(template.text)
            text_item.setToolTip(template.text)
            table.setItem(row, 3, text_item)

            for col, value in ((4, template.first_line), (5, template.last_line)):
                cell = QTableWidgetItem(f"{value:,}")
                cell.setTextAlignment(Qt.AlignCenter)
                table.setItem(row, col, cell)

        table.resizeColumnsToContents()
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)

    def render_timeline(self):
        buckets = self.report.buckets
        table = self.table_timeline
        table.setRowCount(len(buckets))

        if not buckets:
            self.tabs.setTabText(2, "⏱ 타임라인 (타임스탬프 없음)")
            return
        self.tabs.setTabText(2, "⏱ 타임라인")

        peak = max(b.total for b in buckets) or 1

        for row, bucket in enumerate(buckets):
            time_item = QTableWidgetItem(f"{bucket.start:%m-%d %H:%M:%S}")
            table.setItem(row, 0, time_item)

            total_item = QTableWidgetItem(f"{bucket.total:,}")
            total_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            table.setItem(row, 1, total_item)

            problem_item = QTableWidgetItem(f"{bucket.problems:,}")
            problem_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if bucket.problems:
                problem_item.setForeground(QColor("#fb923c"))
            table.setItem(row, 2, problem_item)

            width = int(bucket.total / peak * 50)
            problem_width = int(bucket.problems / peak * 50)
            bar = "█" * problem_width + "▓" * max(width - problem_width, 0)
            bar_item = QTableWidgetItem(bar)
            bar_item.setForeground(QColor("#fb923c" if bucket.problems else "#38bdf8"))
            bar_item.setFont(QFont("Consolas", 9))
            table.setItem(row, 3, bar_item)

        table.resizeColumnsToContents()
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)

    # ------------------------------------------------------------------
    # 드릴다운
    # ------------------------------------------------------------------
    def on_highlight_selected(self):
        rows = self.table_highlights.selectionModel().selectedRows()
        if not rows or not self.report:
            return
        item = self.report.highlights[rows[0].row()]

        if item.template is None:
            self.txt_detail.setPlainText(
                f"{KIND_HINTS.get(item.kind, '')}\n\n{item.title}\n{item.detail}"
            )
            return
        self.show_template_detail(item.template, KIND_HINTS.get(item.kind, ""))

    def on_template_selected(self):
        rows = self.table_templates.selectionModel().selectedRows()
        if not rows:
            return
        templates = getattr(self, "_visible_templates", [])
        index = rows[0].row()
        if 0 <= index < len(templates):
            self.show_template_detail(templates[index])

    def show_template_detail(self, template, hint=""):
        lines = []
        if hint:
            lines.append(f"💡 {hint}")
            lines.append("")

        lines.append(f"템플릿 : {template.text}")
        lines.append(
            f"발생    : {template.count:,}회 "
            f"(레벨 {dict(template.level_counts)})"
        )
        lines.append(f"줄 범위 : {template.first_line:,} ~ {template.last_line:,}")
        if template.first_seen:
            lines.append(
                f"시간    : {template.first_seen:%Y-%m-%d %H:%M:%S}"
                f" ~ {template.last_seen:%Y-%m-%d %H:%M:%S}"
            )
        lines.append("")
        lines.append(f"── 원본 로그 (최대 {len(template.samples)}건) " + "─" * 30)
        lines.append("")

        for entry in template.samples:
            lines.append(f"[{entry.line_no:,}행]")
            lines.append(entry.full_text)
            lines.append("")

        self.txt_detail.setPlainText("\n".join(lines))

    def copy_summary(self):
        if not self.report:
            return
        report = self.report

        lines = [
            f"로그 분석 요약 — {Path(report.path).name}",
            f"줄 수 {report.total_lines:,} / 사건 {report.parsed_entries:,}건 "
            f"/ 템플릿 {len(report.templates):,}개 ({report.compression_ratio:,.0f}:1)",
        ]
        if report.first_seen:
            lines.append(
                f"기간 {report.first_seen:%Y-%m-%d %H:%M:%S}"
                f" ~ {report.last_seen:%Y-%m-%d %H:%M:%S}"
            )
        lines.append("레벨: " + ", ".join(
            f"{lv} {report.level_counts[lv]:,}"
            for lv in la.LEVEL_ORDER if report.level_counts.get(lv)
        ))
        lines.append("")
        lines.append("[주목할 로그]")
        for item in report.highlights:
            label = KIND_LABELS.get(item.kind, (item.kind, ""))[0]
            lines.append(f"- {label} {item.title} :: {item.detail}")

        QApplication.clipboard().setText("\n".join(lines))
        self.lbl_status.setText("📋 분석 요약을 클립보드에 복사했습니다.")

    def shutdown(self):
        if self.thread:
            self.thread.quit()
            self.thread.wait(3000)
