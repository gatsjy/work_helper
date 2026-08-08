"""
Column Analyzer

컬럼 헤더(별칭)를 표준 카테고리로 매핑한다.

매칭 규칙
- 정규화 후 '완전일치'로만 판정한다(부분일치 금지 → 오탐 방지).
- 정규화: 앞뒤 공백 제거 + 대문자화 + 공백/구분자(. _ -) 제거.
  예) "Name"/"name"/"NAME" → NAME,  "H.P" → HP,  "PAT_ID"/"PAT-ID" → PATID,
      "최초 작성일자" → 최초작성일자
- date 카테고리만 '여러 열'을 모두 수집하고, 나머지는 첫 매칭 1개만 사용한다.

주의(의도적으로 제외한 것)
- 너무 generic해서 오탐 위험이 큰 토큰은 넣지 않았다:
  "번호"(순번/접수번호/청구번호 등과 혼동), "일자"(단독), "코드"(단독), "성별", "나이".
- "진료번호"는 시스템에 따라 '방문(encounter) 번호'라 patient_id에 넣지 않았다.
"""

import re
from pathlib import Path

import yaml

# 저장소 루트의 사용자 별칭 파일 (있으면 내장 별칭에 추가된다)
DEFAULT_ALIASES_PATH = Path(__file__).resolve().parent.parent / "configs" / "aliases.yaml"


def normalize(text):
    """헤더 비교용 정규화."""
    if text is None:
        return ""
    s = str(text).strip().upper()
    s = re.sub(r"[\s._\-]", "", s)   # 공백/온점/언더스코어/하이픈 제거
    return s


# 중복 헤더를 DataFrame에서 유일하게 만들 때 쓰는 내부 구분자.
# 실제 엑셀 헤더에는 나오지 않는 제어문자를 사용한다. 라벨은 내부 접근용일
# 뿐이며, 다시 엑셀에 쓸 때는 열 위치 기준이라 원본 헤더는 그대로 유지된다.
_DUP_SEP = "\x00#"


def make_unique_columns(columns):
    """
    중복된 컬럼명에 내부 접미사를 붙여 유일하게 만든다.
    (pandas는 중복 컬럼명이면 df[name]이 Series가 아니라 DataFrame을 반환해
     이후 처리가 깨지므로 이를 방지한다.)
    """
    counts = {}
    result = []
    for col in columns:
        if col in counts:
            counts[col] += 1
            result.append(f"{col}{_DUP_SEP}{counts[col]}")
        else:
            counts[col] = 0
            result.append(col)
    return result


def base_name(col):
    """유일화 접미사를 떼어 원래 헤더명을 돌려준다."""
    if isinstance(col, str) and _DUP_SEP in col:
        return col.split(_DUP_SEP, 1)[0]
    return col


def load_alias_overrides(path):
    """
    YAML 별칭 파일을 읽어 {카테고리: [별칭, ...]} dict로 반환한다.
    파일이 없으면 빈 dict.
    """
    path = Path(path)
    if not path.exists():
        return {}

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    result = {}
    for category, aliases in data.items():
        if aliases is None:
            continue
        if isinstance(aliases, str):
            aliases = [aliases]
        result[category] = list(aliases)

    return result


class ColumnAnalyzer:

    def __init__(self, extra_aliases=None, aliases_path=None):
        """
        extra_aliases : {카테고리: [별칭...]} dict. 내장 별칭에 '추가'된다.
        aliases_path  : 별칭 YAML 경로. 생략 시 configs/aliases.yaml 이
                        있으면 자동으로 읽어 추가한다.

        어느 쪽이든 기존 내장 별칭을 대체하지 않고 union으로 합쳐지므로,
        사용자는 병원별로 추가할 헤더만 나열하면 된다.
        """

        self.aliases = {

            # 환자명 -----------------------------------------------------
            "patient_name": [
                "성명", "이름", "환자명", "환자성명", "수진자명", "대상자명",
                "PAT_NAME", "PATIENT_NAME", "NAME", "PT_NAME",
            ],

            # 환자 식별번호 (등록/차트) ----------------------------------
            "patient_id": [
                "등록번호", "환자번호", "환자등록번호", "병록번호",
                "차트번호", "챠트번호", "수진자번호",
                "MRN", "PAT_ID", "PATIENT_ID", "PT_ID", "PID",
                "CHART_NO", "CHARTNO", "PATNO",
            ],

            # 전화 / 연락처 (보호자 연락처 포함 — 모두 PII) ---------------
            "phone": [
                "전화번호", "전화", "휴대폰", "휴대폰번호", "핸드폰", "핸드폰번호",
                "연락처", "자택전화", "직장전화", "비상연락처", "보호자연락처",
                "H.P", "HP", "TEL", "PHONE", "MOBILE", "CELL", "CONTACT",
            ],

            # 주민등록번호 / 고유식별번호 --------------------------------
            "rrn": [
                "주민등록번호", "주민번호", "주민",
                "RRN", "JUMIN", "SSN", "RESIDENT_NO", "RESIDENT_REGISTRATION_NO",
            ],

            # 진료과 / 부서 ----------------------------------------------
            "department": [
                "진료과", "진료과목", "과", "처방과", "수술과", "발생과", "의뢰과",
                "부서", "부서명", "집도과",
                # 모니터링 통계
                "해당과", "시술과", "Pre진료과", "Post진료과",
                "DEPT", "DEPARTMENT", "DEPT_NM", "DEPT_NAME",
            ],

            # 의료진 코드 / 사번 / 면허번호 ------------------------------
            "doctor_id": [
                "의사코드", "닥터코드", "의사ID", "사번", "직원번호", "면허번호",
                "STAFF_ID", "DOCTOR_ID", "DR_CODE", "EMP_NO", "EMP_ID", "LICENSE_NO",
            ],

            # 의료진명 (작성자/판독의/보조의 등 스태프명 포함) -----------
            # ※ 매칭되는 '모든' 열이 마스킹된다(수술기록의 집도의+보조의사1~3 등).
            #    doctor_id가 있으면 첫 의료진 열(집도의)은 코드 기준 가명으로
            #    통합되고, 나머지 보조의 열은 이름(+과) 기준으로 가명화된다.
            "doctor_name": [
                "집도의", "주치의", "담당의", "담당의사", "처방의", "처방의사",
                "시술의", "판독의", "진료의", "작성의", "작성자",
                "의사", "의사명", "의료진", "교수", "교수명",
                "전문의", "전공의", "수련의", "지도전문의",
                # 보조 의료진 (수술기록)
                "보조", "보조의", "보조의사",
                "보조의사1", "보조의사2", "보조의사3",
                "보조의1", "보조의2", "보조의3",
                "제1보조의", "제2보조의", "제3보조의",
                # 모니터링 통계
                "전문의명", "전공의명",
                "Pre작성자", "Post작성자", "pre담당의", "post담당의",
                "SURGEON", "DOCTOR", "DOC_NAME", "PHYSICIAN", "ATTENDING", "STAFF_NAME",
            ],

            # 날짜/일시 (모두 동일 오프셋으로 이동) -----------------------
            # ※ 생년월일 포함 여부는 아래 프롬프트에서 확인 필요.
            "date": [
                # 진료/수술/입퇴원
                "수술일", "수술일자", "수술예정일", "수술시작일시", "수술종료일시",
                "입원일", "입원일자", "입원일시", "퇴원일", "퇴원일자", "퇴원일시",
                "퇴원예정일", "입실일", "퇴실일", "전과일", "전동일",
                "진료일", "내원일", "내원일시", "방문일", "방문일자", "예약일", "예약일자",
                # 검사/영상/처방/오더
                "검사일", "검사일자", "검사접수일", "검사보고일", "채혈일", "촬영일",
                "판독일", "보고일", "결과일", "처방일", "처방일자", "시술일", "시술일자", "시행일",
                "오더일", "오더일자", "접수일",
                # 원무/청구/작성
                "수납일", "등록일", "등록일자", "청구일", "심사일", "지급일",
                "작성일", "작성일자", "작성일시", "수정일", "수정일시",
                "최초 작성일자", "최종 작성일자",
                # 출생/사망 (플래그: 아래 참고)
                "생년월일", "생일", "사망일", "사망일자",
                # 영문
                "DATE", "OP_DATE", "ADM_DATE", "ADMISSION_DATE", "DISCHARGE_DATE",
                "VISIT_DATE", "ORDER_DATE", "TEST_DATE", "EXAM_DATE", "RESULT_DATE",
                "CREATE_DATE", "UPDATE_DATE", "REG_DATE",
                "BIRTH_DATE", "DOB", "DEATH_DATE",
            ],

            # 주소 ---------------------------------------------------------
            "address": [
                "주소", "자택주소", "환자주소", "거주지", "도로명주소", "지번주소",
                "ADDRESS", "ADDR",
            ],

            # 이메일 -------------------------------------------------------
            "email": [
                "이메일", "메일", "이메일주소", "전자우편",
                "EMAIL", "E-MAIL", "MAIL",
            ],
        }

        # 사용자 별칭을 내장 별칭에 추가(union)한다.
        if aliases_path is None and DEFAULT_ALIASES_PATH.exists():
            aliases_path = DEFAULT_ALIASES_PATH

        overrides = dict(extra_aliases or {})
        if aliases_path is not None:
            for category, aliases in load_alias_overrides(aliases_path).items():
                overrides.setdefault(category, [])
                overrides[category] = overrides[category] + aliases

        for category, aliases in overrides.items():
            self.aliases.setdefault(category, [])
            # 순서 유지 + 중복 제거하며 추가
            existing = self.aliases[category]
            for alias in aliases:
                if alias not in existing:
                    existing.append(alias)

        # 정규화된 별칭 집합을 미리 만들어 둔다(런타임 비교용).
        self._alias_sets = {
            standard_name: {normalize(a) for a in alias_list}
            for standard_name, alias_list in self.aliases.items()
        }
        # 헤더행 탐지에 쓰는 전체 별칭 집합.
        self._all_aliases = set()
        for alias_set in self._alias_sets.values():
            self._all_aliases |= alias_set

    def find_header_row(self, ws, max_scan_rows=20):
        """
        alias 매칭 수가 가장 많은 행을 헤더행으로 추정한다(1-based).
        """
        best_row = 1
        best_score = -1

        for row_idx, row in enumerate(ws.iter_rows(values_only=True), start=1):

            if row_idx > max_scan_rows:
                break

            score = sum(
                1 for cell in row
                if cell is not None and normalize(cell) in self._all_aliases
            )

            if score > best_score:
                best_score = score
                best_row = row_idx

        return best_row

    # 여러 열을 모두 수집하는 카테고리 (수술기록의 집도의+보조의사1~3,
    # 입원일/퇴원일/수술일 등 한 시트에 같은 종류의 열이 여러 개 나올 수 있음)
    MULTI_COLUMN = {"date", "doctor_name"}

    def analyze(self, df):
        """
        DataFrame 컬럼을 표준 카테고리로 매핑한다.
        - date, doctor_name: 매칭되는 모든 열의 리스트
        - 그 외: 첫 매칭 열 1개(없으면 None)
        """
        result = {}

        # 중복 헤더로 유일화된 컬럼(예: "수술일\x00#1")도 원래 이름 기준으로
        # 매칭되도록 base_name으로 정규화한다.
        for standard_name, alias_set in self._alias_sets.items():

            if standard_name in self.MULTI_COLUMN:
                result[standard_name] = [
                    column for column in df.columns
                    if normalize(base_name(column)) in alias_set
                ]
                continue

            result[standard_name] = None
            for column in df.columns:
                if normalize(base_name(column)) in alias_set:
                    result[standard_name] = column
                    break

        return result
