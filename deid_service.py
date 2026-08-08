# -*- coding: utf-8 -*-
"""
HKDeID 어댑터 (work_helper 통합 계층)

vendored `hkdeid/` 패키지는 원본 그대로 두고, GUI가 필요로 하는 것만 이 파일에서 감싼다.

`HKDeIDEngine.run()`을 그대로 쓰지 않는 이유:
  - 반환값이 없고 결과를 stdout으로만 출력한다 (--noconsole exe에서는 전부 사라진다).
  - 출력 경로를 지정할 수 없다 (항상 입력 파일 옆에 쓴다).
  - 진행률 콜백/취소 지점이 없어 큰 워크북에서 UI가 얼어붙는다.
  - 개인정보 열을 하나도 못 찾아도 조용히 "성공"한다.

그래서 engine.run()과 같은 순서로 같은 프리미티브를 호출하되,
구조화된 결과를 돌려주고 진행 상황을 보고한다. 마스킹 로직 자체는 손대지 않는다.
"""
import os
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from collections import defaultdict

import pandas as pd

import hkdeid.security as _hk_security
import hkdeid.masker as _hk_masker
from hkdeid.analyzer import ColumnAnalyzer, base_name
from hkdeid.config import HKDeIDConfig
from hkdeid.excel import (
    load_workbook_file,
    worksheet_to_dataframe,
    dataframe_to_worksheet,
)
from hkdeid.masker import Masker, normalize_value
from hkdeid.version import __version__ as HKDEID_VERSION


# ---------------------------------------------------------------------------
# 비밀키 위치 고정 (PyInstaller onefile 대응)
# ---------------------------------------------------------------------------
# hkdeid/security.py 의 KEY_FILE 은 `Path(__file__).parent.parent/.secret.key` 라서
# --onefile 로 얼리면 매 실행마다 새로 만들어졌다 사라지는 임시 폴더(_MEIxxxx)를
# 가리킨다. 그러면 실행할 때마다 키가 새로 생성되어 같은 환자가 매번 다른 가명을
# 받는다 — 파일 간 링크라는 이 툴의 존재 이유가 조용히 무너진다.
# 얼린 상태에서는 exe 옆(없으면 홈 디렉터리)에 키를 두어 실행 간에 유지되게 한다.
KEY_FILENAME = ".secret.key"


def _is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def _writable_dir(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".hkdeid_write_test"
        probe.write_text("x", encoding="utf-8")
        probe.unlink()
        return True
    except Exception:
        return False


def resolve_key_file() -> Path:
    """실행 간에 유지되는 .secret.key 경로를 고른다.

    같은 키 → 같은 가명이므로, 이 경로가 안정적이어야 서로 다른 파일·서로 다른
    실행에서 같은 환자를 이어붙일 수 있다.
    """
    if _is_frozen():
        exe_dir = Path(sys.executable).resolve().parent
        if _writable_dir(exe_dir):
            return exe_dir / KEY_FILENAME
        # 네트워크 드라이브/읽기 전용 위치에서 실행한 경우
        return Path.home() / ".work_helper_hkdeid.secret.key"
    # 소스 실행: 원본 hkdeid 의 동작(저장소 루트)을 그대로 유지한다.
    return Path(__file__).resolve().parent / KEY_FILENAME


_key_cache_lock = threading.Lock()
_key_cache: dict = {}

# 패치하기 '전'의 원본 함수를 붙잡아 둔다. 이걸 안 하면 아래 래퍼가
# 자기 자신을 부르게 되어 무한 재귀에 빠진다.
_original_get_secret_key = _hk_security.get_secret_key


def _cached_get_secret_key() -> str:
    """비밀키를 한 번만 읽어 캐시한다.

    원본 generate_pseudonym() 은 셀 하나 가명화할 때마다 get_secret_key() 를 부르고,
    그때마다 파일을 연다. 10만 행 워크북이면 디스크 읽기 10만+ 번이다.
    키는 프로세스 수명 동안 바뀌지 않으므로 캐시해도 동작은 동일하다.
    """
    key_file = resolve_key_file()
    with _key_cache_lock:
        cached = _key_cache.get(str(key_file))
        if cached:
            return cached

    _hk_security.KEY_FILE = key_file
    secret = _original_get_secret_key()   # 없으면 생성하는 원본 로직 그대로

    with _key_cache_lock:
        _key_cache[str(key_file)] = secret
    return secret


def install_key_patch() -> Path:
    """vendored hkdeid 가 안정적이고 캐시된 키를 쓰도록 연결한다.

    masker.py 가 `from hkdeid.security import get_secret_key` 로 이름을 미리
    바인딩하므로 두 네임스페이스 모두 교체해야 한다.
    """
    key_file = resolve_key_file()
    _hk_security.KEY_FILE = key_file
    _hk_security.get_secret_key = _cached_get_secret_key
    _hk_masker.get_secret_key = _cached_get_secret_key
    return key_file


install_key_patch()


# ---------------------------------------------------------------------------
# 결과 자료구조
# ---------------------------------------------------------------------------
# GUI 에 보여줄 카테고리 라벨
CATEGORY_LABELS = {
    "patient_name": "환자명",
    "patient_id": "등록번호(MRN)",
    "rrn": "주민등록번호",
    "phone": "전화번호",
    "address": "주소",
    "email": "이메일",
    "doctor_name": "의료진명",
    "doctor_id": "의사코드",
    "department": "진료과",
    "date": "날짜",
}

# 실제로 개인정보를 담는 카테고리 (department 는 PII 가 아니라 가명 키 재료다)
PII_CATEGORIES = (
    "patient_name", "patient_id", "rrn", "phone",
    "address", "email", "doctor_name",
)


@dataclass
class SheetReport:
    title: str
    rows: int = 0
    header_row: int = 1
    footer_rows: int = 0
    detected: dict = field(default_factory=dict)   # 카테고리 -> [원본 헤더명]
    skipped: bool = False
    reason: str = ""

    @property
    def pii_columns(self) -> int:
        return sum(
            len(cols) for cat, cols in self.detected.items()
            if cat in PII_CATEGORIES
        )


@dataclass
class DeIdReport:
    input_path: str = ""
    output_path: str = ""
    sheets: list = field(default_factory=list)     # [SheetReport]
    total_rows: int = 0
    unique_patients: int = 0
    cross_sheet_linked: int = 0
    id_conflicts: int = 0
    name_splits: int = 0
    warnings: list = field(default_factory=list)
    key_file: str = ""
    version: str = HKDEID_VERSION

    @property
    def processed_sheets(self) -> int:
        return sum(1 for s in self.sheets if not s.skipped)

    @property
    def total_pii_columns(self) -> int:
        return sum(s.pii_columns for s in self.sheets if not s.skipped)


class DeIdCancelled(Exception):
    """사용자가 실행 도중 취소했을 때."""


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------
def _detected_map(column_map: dict) -> dict:
    """analyze() 결과를 {카테고리: [표시용 헤더명]} 으로 정리한다.

    중복 헤더에 붙은 내부 접미사(\\x00#1)는 떼고 보여준다.
    """
    detected = {}
    for category, value in column_map.items():
        if value is None:
            continue
        columns = value if isinstance(value, list) else [value]
        columns = [str(base_name(c)) for c in columns if c is not None]
        if columns:
            detected[category] = columns
    return detected


def _default_output_path(input_path, suffix: str) -> Path:
    p = Path(input_path)
    return p.with_name(f"{p.stem}{suffix}{p.suffix}")


def _noop(*_args, **_kwargs):
    return None


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------
def analyze_workbook(input_path, config=None, progress=None) -> DeIdReport:
    """미리보기(dry-run): 파일을 쓰지 않고 어떤 열이 잡히는지만 확인한다.

    비식별화 툴에서 가장 위험한 실패는 '조용히 아무것도 안 가리고 성공하는 것'이다.
    실행 전에 무엇이 탐지됐는지 먼저 보여준다.
    """
    progress = progress or _noop
    config = config or HKDeIDConfig.default()
    input_path = Path(input_path)

    if not input_path.exists():
        raise FileNotFoundError(f"입력 파일을 찾을 수 없습니다: {input_path}")

    report = DeIdReport(
        input_path=str(input_path),
        key_file=str(resolve_key_file()),
    )

    progress(0, "워크북을 읽는 중...")
    workbook = load_workbook_file(input_path)
    sheets = workbook.worksheets
    total = max(len(sheets), 1)

    for i, ws in enumerate(sheets):
        progress(int(i / total * 100), f"[{ws.title}] 컬럼 분석 중...")

        analyzer = ColumnAnalyzer()
        df, header_row, footer_rows = worksheet_to_dataframe(ws, analyzer)

        if df.empty:
            report.sheets.append(
                SheetReport(title=ws.title, skipped=True, reason="빈 시트")
            )
            continue

        column_map = analyzer.analyze(df)
        sheet_report = SheetReport(
            title=ws.title,
            rows=len(df),
            header_row=header_row,
            footer_rows=len(footer_rows),
            detected=_detected_map(column_map),
        )
        report.sheets.append(sheet_report)
        report.total_rows += len(df)

    _add_coverage_warnings(report)
    progress(100, "분석 완료")
    return report


def deidentify_workbook(
    input_path,
    output_path=None,
    config=None,
    progress=None,
    should_cancel=None,
) -> DeIdReport:
    """워크북을 비식별화해 새 파일로 저장한다.

    HKDeIDEngine.run() 과 같은 순서로 같은 프리미티브를 호출하되,
    결과를 구조화해 돌려주고 진행률/취소를 지원한다.
    """
    progress = progress or _noop
    should_cancel = should_cancel or (lambda: False)
    config = config or HKDeIDConfig.default()

    input_path = Path(input_path)
    if not input_path.exists():
        raise FileNotFoundError(f"입력 파일을 찾을 수 없습니다: {input_path}")

    if output_path is None:
        output_path = _default_output_path(input_path, config.output_suffix)
    output_path = Path(output_path)

    # 원본 덮어쓰기 방지 — 원본이 사라지면 되돌릴 방법이 없다.
    if output_path.resolve() == input_path.resolve():
        raise ValueError(
            "출력 파일이 원본과 같습니다. 원본을 덮어쓸 수 없습니다.\n"
            "다른 이름으로 저장하세요."
        )

    report = DeIdReport(
        input_path=str(input_path),
        output_path=str(output_path),
        key_file=str(resolve_key_file()),
    )

    # 마스킹 '전' 원본값 기준 링크 감사 (engine.run 과 동일)
    id_to_sheets = defaultdict(set)
    id_to_names = defaultdict(set)
    name_to_ids = defaultdict(set)

    progress(0, "워크북을 읽는 중...")
    workbook = load_workbook_file(input_path)
    sheets = workbook.worksheets
    total = max(len(sheets), 1)

    id_zero_pad = getattr(config, "id_zero_pad", 0)

    for i, ws in enumerate(sheets):
        if should_cancel():
            raise DeIdCancelled()

        base = int(i / total * 90)
        progress(base, f"[{ws.title}] 처리 중... ({i + 1}/{total})")

        analyzer = ColumnAnalyzer()
        df, header_row, footer_rows = worksheet_to_dataframe(ws, analyzer)

        if df.empty:
            report.sheets.append(
                SheetReport(title=ws.title, skipped=True, reason="빈 시트")
            )
            continue

        column_map = analyzer.analyze(df)

        _collect_linkage(
            df, column_map, footer_rows, ws.title,
            id_to_sheets, id_to_names, name_to_ids, id_zero_pad,
        )

        Masker().mask(df, column_map, config, footer_rows)
        dataframe_to_worksheet(ws, df, header_row)

        report.sheets.append(SheetReport(
            title=ws.title,
            rows=len(df),
            header_row=header_row,
            footer_rows=len(footer_rows),
            detected=_detected_map(column_map),
        ))
        report.total_rows += len(df)

    if should_cancel():
        raise DeIdCancelled()

    progress(92, "결과 파일 저장 중...")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(output_path)

    progress(97, "링크 검증 중...")
    report.unique_patients = len(id_to_sheets)
    report.cross_sheet_linked = sum(
        1 for s in id_to_sheets.values() if len(s) > 1
    )
    report.id_conflicts = sum(
        1 for names in id_to_names.values() if len(names) > 1
    )
    report.name_splits = sum(
        1 for ids in name_to_ids.values() if len(ids) > 1
    )

    _add_coverage_warnings(report)
    if report.id_conflicts:
        report.warnings.append(
            f"같은 등록번호에 다른 이름이 섞임: {report.id_conflicts}건 "
            "(등록번호 오입력 가능성)"
        )
    if report.name_splits:
        report.warnings.append(
            f"같은 이름이 여러 등록번호로 나뉨: {report.name_splits}건 "
            "(동명이인이거나 시트마다 등록번호 표기가 다를 수 있음)"
        )

    progress(100, "완료")
    return report


def _collect_linkage(
    df, column_map, footer_rows, sheet_title,
    id_to_sheets, id_to_names, name_to_ids, id_zero_pad,
):
    """마스킹 전 원본값을 정규화해 환자 링크 정보를 누적한다."""
    pid_col = column_map.get("patient_id")
    name_col = column_map.get("patient_name")

    if pid_col is None:
        return

    for idx, value in df[pid_col].items():
        if idx in footer_rows or pd.isna(value):
            continue

        norm_id = normalize_value(value, id_zero_pad)
        id_to_sheets[norm_id].add(sheet_title)

        if name_col is not None:
            name_value = df.at[idx, name_col]
            if not pd.isna(name_value):
                norm_name = normalize_value(name_value)
                id_to_names[norm_id].add(norm_name)
                name_to_ids[norm_name].add(norm_id)


def _add_coverage_warnings(report: DeIdReport):
    """개인정보를 못 찾은 경우를 크게 경고한다.

    비식별화 툴에서 가장 위험한 실패는 크래시가 아니라, 아무것도 못 가린 파일을
    '완료'라고 돌려주는 것이다. 사용자는 그 파일을 안전하다고 믿고 LLM 에 붙여넣는다.
    """
    processed = [s for s in report.sheets if not s.skipped]

    if not processed:
        report.warnings.append(
            "처리할 데이터가 있는 시트가 없습니다. 파일을 확인하세요."
        )
        return

    if report.total_pii_columns == 0:
        report.warnings.append(
            "⚠️ 개인정보 열을 하나도 찾지 못했습니다. "
            "결과 파일은 사실상 원본과 같습니다 — 공유 전 반드시 직접 확인하세요. "
            "헤더명이 특이하다면 configs/aliases.yaml 에 별칭을 추가하세요."
        )
        return

    blind = [s.title for s in processed if s.pii_columns == 0]
    if blind:
        preview = ", ".join(blind[:5])
        more = f" 외 {len(blind) - 5}개" if len(blind) > 5 else ""
        report.warnings.append(
            f"개인정보 열이 탐지되지 않은 시트: {preview}{more} "
            "(해당 시트는 값이 그대로 남습니다)"
        )
