# -*- coding: utf-8 -*-
"""
🛡️ 개인정보 비식별화 탭 (HKDeID 연동)

무거운 작업(워크북 로딩·마스킹·저장)은 전부 QThread 워커에서 돌린다.
GUI 스레드에서 돌리면 수만 행짜리 워크북에서 창이 '응답 없음'으로 굳는다.
"""
import os
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QGroupBox,
    QCheckBox, QLineEdit, QSpinBox, QFileDialog, QMessageBox, QProgressBar,
    QTextEdit, QTableWidget, QTableWidgetItem, QHeaderView, QFormLayout,
)
from PySide6.QtCore import Qt, QObject, QThread, Signal
from PySide6.QtGui import QFont

import deid_service as ds
from hkdeid.config import HKDeIDConfig


class DeIdWorker(QObject):
    """백그라운드 스레드에서 비식별화/미리보기를 실행한다."""

    progress = Signal(int, str)
    finished = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, mode, input_path, output_path, config):
        super().__init__()
        self.mode = mode                 # "preview" | "run"
        self.input_path = input_path
        self.output_path = output_path
        self.config = config
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def _should_cancel(self):
        return self._cancel

    def run(self):
        try:
            if self.mode == "preview":
                report = ds.analyze_workbook(
                    self.input_path,
                    config=self.config,
                    progress=lambda p, m: self.progress.emit(p, m),
                )
            else:
                report = ds.deidentify_workbook(
                    self.input_path,
                    self.output_path,
                    config=self.config,
                    progress=lambda p, m: self.progress.emit(p, m),
                    should_cancel=self._should_cancel,
                )
            self.finished.emit(report)
        except ds.DeIdCancelled:
            self.cancelled.emit()
        except PermissionError:
            self.failed.emit(
                "파일에 접근할 수 없습니다.\n"
                "결과 파일이 Excel에서 열려 있다면 닫고 다시 시도하세요."
            )
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class DeIdWidget(QWidget):
    """엑셀 개인정보 비식별화 위젯."""

    # (설정 필드명, 라벨, 툴팁)
    MASK_OPTIONS = [
        ("mask_name",      "환자명 가명처리",      "홍길동 → PATIENT_4D8347C8"),
        ("mask_patient_id", "등록번호(MRN) 가명처리", "123456 → MRN_CF85D154"),
        ("mask_doctor",    "의료진 가명처리",      "집도의·보조의 등 모든 의료진 열"),
        ("mask_rrn",       "주민등록번호 마스킹",   "900101-1234567 → 900101-*******"),
        ("mask_phone",     "전화번호 마스킹",      "010-1234-5678 → 010-****-5678"),
        ("mask_address",   "주소 마스킹",         "시/도 + 시/군/구만 남김"),
        ("mask_email",     "이메일 마스킹",        "hong@naver.com → h****@naver.com"),
        ("shift_date",     "날짜 이동 (Date Shift)", "모든 날짜를 같은 일수만큼 이동 (간격 보존)"),
        ("mask_free_text", "자유 텍스트 개인정보 마스킹", "비고/메모 열에 섞인 전화·주민·이메일"),
    ]

    def __init__(self):
        super().__init__()
        self.input_path = None
        self.thread = None
        self.worker = None
        self.last_report = None
        self.option_checks = {}
        self.init_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def init_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(16)

        main_layout.addWidget(self._build_left_panel())
        main_layout.addLayout(self._build_right_panel(), stretch=1)

    def _build_left_panel(self):
        panel = QWidget()
        panel.setFixedWidth(380)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)

        title = QLabel("🛡️ 엑셀 개인정보 비식별화")
        title.setFont(QFont("맑은 고딕", 13, QFont.Bold))
        layout.addWidget(title)

        desc = QLabel(
            "원본 시트·헤더·서식·수식은 그대로 두고 개인정보가 담긴 "
            "<b>셀 값만</b> 바꿉니다. LLM이나 동료에게 넘기기 전에 먼저 돌리세요."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #94a3b8; font-size: 11px;")
        layout.addWidget(desc)

        # 1. 파일 선택
        file_group = QGroupBox("1. 대상 엑셀 파일")
        file_layout = QVBoxLayout(file_group)

        self.lbl_file = QLabel("선택된 파일이 없습니다.")
        self.lbl_file.setWordWrap(True)
        self.lbl_file.setStyleSheet("color: #fbbf24; font-weight: bold;")
        file_layout.addWidget(self.lbl_file)

        btn_browse = QPushButton("📂 엑셀 파일 선택...")
        btn_browse.setStyleSheet(
            "background-color: #2563eb; color: white; font-weight: bold; padding: 8px;"
        )
        btn_browse.clicked.connect(self.browse_file)
        file_layout.addWidget(btn_browse)
        layout.addWidget(file_group)

        # 2. 마스킹 항목
        opt_group = QGroupBox("2. 비식별화 항목")
        opt_layout = QVBoxLayout(opt_group)
        for field, label, tooltip in self.MASK_OPTIONS:
            chk = QCheckBox(label)
            chk.setChecked(True)
            chk.setToolTip(tooltip)
            self.option_checks[field] = chk
            opt_layout.addWidget(chk)
        layout.addWidget(opt_group)

        # 3. 세부 설정
        adv_group = QGroupBox("3. 세부 설정")
        adv_layout = QFormLayout(adv_group)

        self.spin_date_shift = QSpinBox()
        self.spin_date_shift.setRange(-36500, 36500)
        self.spin_date_shift.setValue(-1000)
        self.spin_date_shift.setSuffix(" 일")
        self.spin_date_shift.setToolTip(
            "모든 날짜를 이 일수만큼 이동합니다.\n"
            "고정 오프셋이라 재원일수·방문 간격 같은 시간 관계는 그대로 보존됩니다."
        )
        adv_layout.addRow("날짜 이동:", self.spin_date_shift)

        self.spin_zero_pad = QSpinBox()
        self.spin_zero_pad.setRange(0, 20)
        self.spin_zero_pad.setValue(0)
        self.spin_zero_pad.setToolTip(
            "등록번호 자릿수 통일 (0이면 사용 안 함).\n"
            "예: 8 → \"12345\"와 \"00012345\"를 같은 환자로 링크합니다."
        )
        adv_layout.addRow("등록번호 zero-pad:", self.spin_zero_pad)

        self.txt_suffix = QLineEdit("_deid")
        self.txt_suffix.setToolTip("patients.xlsx → patients_deid.xlsx")
        adv_layout.addRow("출력 파일 접미사:", self.txt_suffix)
        layout.addWidget(adv_group)

        # 4. 실행
        run_group = QGroupBox("4. 실행")
        run_layout = QVBoxLayout(run_group)

        self.btn_preview = QPushButton("🔍 미리보기 (파일 안 만듦)")
        self.btn_preview.setToolTip(
            "어떤 열이 개인정보로 탐지되는지 먼저 확인합니다. 파일은 만들지 않습니다."
        )
        self.btn_preview.setStyleSheet(
            "background-color: #334155; color: #e2e8f0; font-weight: bold; padding: 8px;"
        )
        self.btn_preview.clicked.connect(lambda: self.start_job("preview"))
        run_layout.addWidget(self.btn_preview)

        self.btn_run = QPushButton("🛡️ 비식별화 실행")
        self.btn_run.setFixedHeight(42)
        self.btn_run.setFont(QFont("맑은 고딕", 10, QFont.Bold))
        self.btn_run.setStyleSheet(
            "background-color: #059669; color: white; border-radius: 6px;"
        )
        self.btn_run.clicked.connect(lambda: self.start_job("run"))
        run_layout.addWidget(self.btn_run)

        self.btn_cancel = QPushButton("⏹ 취소")
        self.btn_cancel.setStyleSheet(
            "background-color: #7f1d1d; color: #fecaca; font-weight: bold; padding: 6px;"
        )
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self.cancel_job)
        run_layout.addWidget(self.btn_cancel)

        self.btn_open_folder = QPushButton("📁 결과 폴더 열기")
        self.btn_open_folder.setEnabled(False)
        self.btn_open_folder.clicked.connect(self.open_result_folder)
        run_layout.addWidget(self.btn_open_folder)
        layout.addWidget(run_group)

        layout.addStretch()

        key_hint = QLabel(
            f"🔑 가명 비밀키: <code>{ds.resolve_key_file()}</code><br>"
            "같은 키를 쓰면 다른 파일에서도 같은 환자가 같은 가명이 됩니다. "
            "백업해 두고, 외부에 공유하지 마세요."
        )
        key_hint.setWordWrap(True)
        key_hint.setStyleSheet("color: #64748b; font-size: 10px;")
        layout.addWidget(key_hint)

        return panel

    def _build_right_panel(self):
        layout = QVBoxLayout()

        status_box = QGroupBox("진행 상태")
        status_layout = QVBoxLayout(status_box)

        self.lbl_status = QLabel("대기 중 — 엑셀 파일을 선택하세요.")
        self.lbl_status.setStyleSheet("color: #38bdf8; font-weight: bold;")
        status_layout.addWidget(self.lbl_status)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(12)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar { background-color: #0f172a; border: 1px solid #334155; border-radius: 5px; }
            QProgressBar::chunk {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                                  stop:0 #10b981, stop:1 #3b82f6);
                border-radius: 4px;
            }
        """)
        status_layout.addWidget(self.progress_bar)
        layout.addWidget(status_box)

        detect_box = QGroupBox("탐지된 개인정보 컬럼 (시트별)")
        detect_layout = QVBoxLayout(detect_box)
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(
            ["시트", "행 수", "개인정보 열", "탐지된 컬럼"]
        )
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        detect_layout.addWidget(self.table)
        layout.addWidget(detect_box, stretch=2)

        log_box = QGroupBox("실행 로그")
        log_layout = QVBoxLayout(log_box)
        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setStyleSheet(
            "background-color: #0f172a; color: #cbd5e1; font-family: Consolas, monospace;"
        )
        log_layout.addWidget(self.txt_log)
        layout.addWidget(log_box, stretch=1)

        return layout

    # ------------------------------------------------------------------
    # 동작
    # ------------------------------------------------------------------
    def log(self, message):
        self.txt_log.append(message)

    def browse_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "비식별화할 엑셀 파일 선택", "",
            "Excel 파일 (*.xlsx *.xlsm);;모든 파일 (*.*)"
        )
        if not path:
            return

        self.input_path = path
        self.lbl_file.setText(f"📄 {Path(path).name}")
        self.lbl_file.setToolTip(path)
        self.lbl_status.setText("파일 선택됨 — 미리보기로 탐지 결과를 먼저 확인하세요.")
        self.log(f"\n📄 선택: {path}")
        self.table.setRowCount(0)

    def build_config(self):
        config = HKDeIDConfig.default()
        for field, chk in self.option_checks.items():
            setattr(config, field, chk.isChecked())
        config.date_shift_days = self.spin_date_shift.value()
        config.id_zero_pad = self.spin_zero_pad.value()

        suffix = self.txt_suffix.text().strip()
        config.output_suffix = suffix if suffix else "_deid"
        return config

    def start_job(self, mode):
        if self.thread is not None:
            QMessageBox.information(self, "안내", "이미 작업이 실행 중입니다.")
            return

        if not self.input_path:
            QMessageBox.warning(self, "파일 없음", "먼저 엑셀 파일을 선택하세요.")
            return

        if not Path(self.input_path).exists():
            QMessageBox.warning(
                self, "파일 없음",
                "선택한 파일이 더 이상 존재하지 않습니다. 다시 선택하세요."
            )
            return

        config = self.build_config()
        output_path = None

        if mode == "run":
            if not any(chk.isChecked() for chk in self.option_checks.values()):
                QMessageBox.warning(
                    self, "항목 없음",
                    "비식별화 항목이 하나도 선택되지 않았습니다.\n"
                    "이 상태로 실행하면 원본과 똑같은 파일이 만들어집니다."
                )
                return

            default_out = Path(self.input_path)
            default_out = default_out.with_name(
                f"{default_out.stem}{config.output_suffix}{default_out.suffix}"
            )
            path, _ = QFileDialog.getSaveFileName(
                self, "비식별화 결과 저장", str(default_out),
                "Excel 파일 (*.xlsx);;모든 파일 (*.*)"
            )
            if not path:
                return

            if Path(path).resolve() == Path(self.input_path).resolve():
                QMessageBox.critical(
                    self, "원본 덮어쓰기 불가",
                    "결과를 원본 파일에 덮어쓸 수 없습니다.\n다른 이름을 지정하세요."
                )
                return
            output_path = path

        self.set_busy(True)
        self.progress_bar.setValue(0)
        self.log(
            "\n" + "=" * 52 + "\n"
            + ("🔍 미리보기 시작" if mode == "preview" else "🛡️ 비식별화 시작")
        )

        self.worker = DeIdWorker(mode, self.input_path, output_path, config)
        self.thread = QThread(self)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self.on_progress)
        self.worker.finished.connect(self.on_finished)
        self.worker.failed.connect(self.on_failed)
        self.worker.cancelled.connect(self.on_cancelled)
        self.thread.start()

    def cancel_job(self):
        if self.worker:
            self.worker.cancel()
            self.lbl_status.setText("취소 요청됨 — 현재 시트를 마치는 중...")
            self.btn_cancel.setEnabled(False)

    def set_busy(self, busy):
        self.btn_run.setEnabled(not busy)
        self.btn_preview.setEnabled(not busy)
        self.btn_cancel.setEnabled(busy)

    def cleanup_thread(self):
        if self.thread:
            self.thread.quit()
            self.thread.wait()
            self.thread.deleteLater()
        if self.worker:
            self.worker.deleteLater()
        self.thread = None
        self.worker = None
        self.set_busy(False)

    def on_progress(self, value, message):
        self.progress_bar.setValue(value)
        self.lbl_status.setText(message)

    def on_failed(self, message):
        self.cleanup_thread()
        self.progress_bar.setValue(0)
        self.lbl_status.setText("❌ 실패")
        self.log(f"❌ 실패: {message}")
        QMessageBox.critical(self, "실행 실패", message)

    def on_cancelled(self):
        self.cleanup_thread()
        self.progress_bar.setValue(0)
        self.lbl_status.setText("⏹ 취소됨 — 결과 파일은 만들어지지 않았습니다.")
        self.log("⏹ 사용자가 취소했습니다. 결과 파일은 저장되지 않았습니다.")

    def on_finished(self, report):
        mode = self.worker.mode if self.worker else "run"
        self.cleanup_thread()
        self.last_report = report
        self.render_report(report)

        if mode == "preview":
            self.lbl_status.setText(
                f"🔍 미리보기 완료 — 시트 {report.processed_sheets}개, "
                f"개인정보 열 {report.total_pii_columns}개 탐지"
            )
            self.log(
                f"🔍 미리보기 완료: 시트 {report.processed_sheets}개, "
                f"{report.total_rows}행, 개인정보 열 {report.total_pii_columns}개"
            )
        else:
            self.lbl_status.setText(f"✅ 완료 — {Path(report.output_path).name}")
            self.btn_open_folder.setEnabled(True)
            self.log(
                f"✅ 저장: {report.output_path}\n"
                f"   시트 {report.processed_sheets}개 / {report.total_rows}행\n"
                f"   고유 환자 {report.unique_patients}명 "
                f"(시트 간 링크 {report.cross_sheet_linked}명)"
            )

        for warning in report.warnings:
            self.log(f"⚠️ {warning}")

        # 아무것도 못 가린 경우는 조용히 넘어가면 안 된다 — 사용자는 이 파일을
        # 안전하다고 믿고 외부로 내보낸다.
        if report.total_pii_columns == 0:
            QMessageBox.warning(
                self, "개인정보 열 미탐지",
                "개인정보로 인식된 열이 하나도 없습니다.\n\n"
                "결과 파일은 사실상 원본과 같습니다. 공유하기 전에 반드시 직접 "
                "확인하고, 헤더명이 특이하다면 configs/aliases.yaml 에 별칭을 "
                "추가하세요."
            )
        elif mode == "run":
            QMessageBox.information(
                self, "비식별화 완료",
                f"저장 위치:\n{report.output_path}\n\n"
                f"시트 {report.processed_sheets}개 / {report.total_rows}행\n"
                f"고유 환자 {report.unique_patients}명\n\n"
                "※ 자동 도구이므로 공유 전 결과를 직접 확인하세요."
            )

    def render_report(self, report):
        self.table.setRowCount(len(report.sheets))

        for row, sheet in enumerate(report.sheets):
            item_title = QTableWidgetItem(sheet.title)
            self.table.setItem(row, 0, item_title)

            if sheet.skipped:
                item_rows = QTableWidgetItem("-")
                item_pii = QTableWidgetItem("-")
                detail = sheet.reason
            else:
                item_rows = QTableWidgetItem(str(sheet.rows))
                item_pii = QTableWidgetItem(str(sheet.pii_columns))
                parts = [
                    f"{ds.CATEGORY_LABELS.get(cat, cat)}={'/'.join(cols)}"
                    for cat, cols in sheet.detected.items()
                ]
                detail = ", ".join(parts) if parts else "탐지된 컬럼 없음"

            item_rows.setTextAlignment(Qt.AlignCenter)
            item_pii.setTextAlignment(Qt.AlignCenter)

            if not sheet.skipped and sheet.pii_columns == 0:
                item_pii.setForeground(Qt.GlobalColor.red)
                item_title.setForeground(Qt.GlobalColor.red)

            self.table.setItem(row, 1, item_rows)
            self.table.setItem(row, 2, item_pii)
            self.table.setItem(row, 3, QTableWidgetItem(detail))

        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)

    def open_result_folder(self):
        if not self.last_report or not self.last_report.output_path:
            return
        output = Path(self.last_report.output_path)
        if not output.exists():
            QMessageBox.warning(self, "안내", "결과 파일을 찾을 수 없습니다.")
            return
        os.startfile(output.parent)

    def shutdown(self):
        """앱 종료 시 워커 스레드를 정리한다 (좀비 스레드 방지)."""
        if self.worker:
            self.worker.cancel()
        if self.thread:
            self.thread.quit()
            self.thread.wait(3000)
