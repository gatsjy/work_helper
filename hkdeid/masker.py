"""
HKDeID Masker
"""
import hashlib
import hmac
from hkdeid.security import get_secret_key
import re
from datetime import timedelta
import pandas as pd


# 자유 텍스트(비고/메모 등)에 섞인 개인정보 탐지용.
# 오탐(false positive)을 줄이기 위해 '형식이 뚜렷한' 패턴만 사용한다.
_RRN_DASH_RE = re.compile(r"(\d{6})-(\d{7})")            # 900101-1234567
_PHONE_DASH_RE = re.compile(r"(\d{2,3})-(\d{3,4})-(\d{4})")  # 010-1234-5678
_PHONE_MOBILE_RE = re.compile(r"(?<!\d)(01\d)(\d{4})(\d{4})(?!\d)")  # 01012345678
_EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


def _mask_email_match(match):
    email = match.group(0)
    local, _, domain = email.partition("@")
    masked_local = (local[0] + "****") if local else "****"
    return f"{masked_local}@{domain}"


def mask_pii_in_text(text):
    """
    자유 텍스트 안에 섞인 전화번호/주민번호/이메일을 마스킹한다.

    구조화된 열(성명/전화번호 등)과 달리 어떤 값이 들어올지 모르므로,
    형식이 분명해 오탐이 적은 패턴만 처리한다. (숫자만 나열된 검사값 등을
    잘못 가리지 않도록, 대시 없는 13자리 주민번호 등은 다루지 않는다.)
    """
    s = str(text)
    s = _RRN_DASH_RE.sub(r"\1-*******", s)
    s = _PHONE_DASH_RE.sub(r"\1-****-\3", s)
    s = _PHONE_MOBILE_RE.sub(r"\1****\3", s)
    s = _EMAIL_RE.sub(_mask_email_match, s)
    return s


def normalize_value(value, zero_pad=0):
    """
    가명(pseudonym) 생성 키로 쓰기 위한 값 정규화.

    같은 사람/의료진이 시트마다 조금씩 다르게 저장돼 있어도 동일한 가명이
    나오도록 표준화한다. 이 정규화가 없으면 아래 같은 경우 서로 다른 사람으로
    갈려서 시트 간 매핑이 깨진다.

      - 엑셀이 숫자를 실수로 저장한 경우:  1001, 1001.0, "1001"  -> "1001"
      - 앞뒤/중간 공백 차이:               " S0001 ", "S0001"      -> "S0001"
      - 대소문자 차이:                     "s0001", "S0001"        -> "S0001"

    zero_pad > 0 이고 값이 순수 숫자면 해당 자릿수로 0을 채운다.
    등록번호가 시트마다 자릿수만 다르게 기록된 경우를 통일한다.

      - zero_pad=8:  "12345", "00012345"  -> "00012345"

    ※ 시트마다 등록번호가 아예 다른 값으로 기록된 경우(예: 한 시트는
      "S0001", 다른 시트는 접두어를 뗀 "1")는 정규화로 통일할 수 없다.
      그런 경우는 별도의 매핑 테이블이 필요하다.
    """
    # numpy float 포함: 정수값 실수(1001.0)는 정수로 통일
    if isinstance(value, float) and float(value).is_integer():
        value = int(value)

    result = re.sub(r"\s+", "", str(value)).upper()

    if zero_pad and result.isdigit():
        result = result.zfill(zero_pad)

    return result


class Masker:

    """Data masking engine."""

    def __init__(self):
        pass

    def mask(self, df, column_map, config, footer_rows=None):
        """
        Execute masking according to configuration.

        footer_rows : 합계/소계 등 요약 행의 위치(df 인덱스) 집합.
                      데이터 정렬을 유지하기 위해 df에는 남아있지만
                      마스킹 대상에서는 제외한다.
        """

        footer_rows = footer_rows or set()

        # 등록번호 zero-padding 자릿수 (0이면 사용 안 함)
        id_zero_pad = getattr(config, "id_zero_pad", 0)

        if config.mask_name:
            self.mask_name(df, column_map, footer_rows, id_zero_pad)

        if config.mask_patient_id:
            self.mask_patient_id(df, column_map, footer_rows, id_zero_pad)

        if config.mask_phone:
            self.mask_phone(df, column_map, footer_rows)

        if config.mask_rrn:
            self.mask_rrn(df, column_map, footer_rows)

        if config.mask_address:
            self.mask_address(df, column_map, footer_rows)

        if config.mask_email:
            self.mask_email(df, column_map, footer_rows)

        if config.mask_doctor:
            self.mask_doctor(df, column_map, footer_rows)

        if config.shift_date:
            self.shift_date(df, column_map, config.date_shift_days, footer_rows)

        if getattr(config, "mask_free_text", False):
            self.mask_free_text(df, column_map, footer_rows)

        return df

    # 가명에 사용할 해시 hex 자릿수. 16자 = 64비트라 수백만 건 규모에서도
    # 충돌(서로 다른 값이 같은 가명이 되는 것)이 사실상 없다.
    PSEUDONYM_HEX_LEN = 16

    def generate_pseudonym(
        self,
        value,
        prefix="PATIENT"
    ):
        """
        HMAC-SHA256 기반 가명 생성
        """

        secret = get_secret_key()

        digest = hmac.new(
            secret.encode("utf-8"),
            str(value).encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

        return f"{prefix}_{digest[:self.PSEUDONYM_HEX_LEN].upper()}"

    def mask_name(self, df, column_map, footer_rows=None, id_zero_pad=0):

        footer_rows = footer_rows or set()

        column = column_map.get("patient_name")
        patient_id_column = column_map.get("patient_id")

        if column is None:
            return

        # 문자열 가명을 자유롭게 넣을 수 있도록 object 타입으로 변환
        # (원본 숫자/문자 값은 그대로 유지되어 정규화 시 읽을 수 있음)
        df[column] = df[column].astype(object)

        for idx, value in df[column].items():

            if idx in footer_rows:
                continue

            if pd.isna(value):
                continue

            # 등록번호가 있으면 '등록번호 + 이름'을 키로 사용한다.
            # (등록번호가 시트 간 링크의 기준이므로 먼저 정규화한다)
            if patient_id_column and not pd.isna(df.at[idx, patient_id_column]):
                patient_key = (
                    normalize_value(df.at[idx, patient_id_column], id_zero_pad)
                    + "|"
                    + normalize_value(value)
                )
            else:
                patient_key = normalize_value(value)

            pseudonym = self.generate_pseudonym(patient_key)

            df.at[idx, column] = pseudonym
    
    def mask_patient_id(self, df, column_map, footer_rows=None, id_zero_pad=0):

        footer_rows = footer_rows or set()

        column = column_map.get("patient_id")

        if column is None:
            return

        # 문자열 가명을 넣을 수 있도록 object 타입으로 변환하되,
        # 원본 값(숫자/문자)은 정규화를 위해 그대로 읽어들인다.
        df[column] = df[column].astype(object)

        for idx, value in df[column].items():

            if idx in footer_rows:
                continue

            if pd.isna(value):
                continue

            pseudonym = self.generate_pseudonym(
                normalize_value(value, id_zero_pad),
                "MRN"
            )

            df.at[idx, column] = pseudonym
    
    def mask_phone(self, df, column_map, footer_rows=None):

        footer_rows = footer_rows or set()

        column = column_map.get("phone")

        if column is None:
            return

        for idx, value in df[column].items():

            if idx in footer_rows:
                continue

            if pd.isna(value):
                continue

            phone = str(value)

            # 010-1234-5678
            phone = re.sub(
                r"(\d{2,3})-(\d{3,4})-(\d{4})",
                r"\1-****-\3",
                phone
            )

            # 01012345678
            phone = re.sub(
                r"(\d{3})(\d{4})(\d{4})",
                r"\1****\3",
                phone
            )

            df.at[idx, column] = phone
            
    def mask_rrn(self, df, column_map, footer_rows=None):

        footer_rows = footer_rows or set()

        column = column_map.get("rrn")

        if column is None:
            return

        for idx, value in df[column].items():

            if idx in footer_rows:
                continue

            if pd.isna(value):
                continue

            rrn = str(value)

            # 950101-1234567
            rrn = re.sub(
                r"(\d{6})-(\d{7})",
                r"\1-*******",
                rrn
            )

            # 9501011234567
            rrn = re.sub(
                r"(\d{6})(\d{7})",
                r"\1*******",
                rrn
            )

            df.at[idx, column] = rrn
            
    def mask_address(self, df, column_map, footer_rows=None):

        footer_rows = footer_rows or set()

        column = column_map.get("address")

        if column is None:
            return

        for idx, value in df[column].items():

            if idx in footer_rows:
                continue

            if pd.isna(value):
                continue

            # 시/도, 시/군/구 정도까지만 남기고 상세 주소(동/번지 등)는 마스킹한다.
            tokens = str(value).split()

            if len(tokens) > 2:
                masked = " ".join(tokens[:2]) + " ****"
            else:
                masked = "****"

            df.at[idx, column] = masked

    def mask_email(self, df, column_map, footer_rows=None):

        footer_rows = footer_rows or set()

        column = column_map.get("email")

        if column is None:
            return

        for idx, value in df[column].items():

            if idx in footer_rows:
                continue

            if pd.isna(value):
                continue

            email = str(value)

            match = re.match(r"^([^@\s]+)(@.+)$", email)

            if match:
                local, domain = match.groups()
                masked_local = local[0] + "****" if local else "****"
                df.at[idx, column] = masked_local + domain
            else:
                df.at[idx, column] = "****"

    def mask_doctor(self, df, column_map, footer_rows=None):

        footer_rows = footer_rows or set()

        name_columns = column_map.get("doctor_name")
        doctor_id_column = column_map.get("doctor_id")
        department_column = column_map.get("department")

        if not name_columns:
            return

        # analyze()는 doctor_name을 리스트로 주지만, 예전 방식(단일 문자열)도
        # 안전하게 처리한다.
        if isinstance(name_columns, str):
            name_columns = [name_columns]

        for column in name_columns:
            df[column] = df[column].astype(object)

        if doctor_id_column:
            df[doctor_id_column] = df[doctor_id_column].astype(object)

        # 첫 의료진 열(집도의)만 의사코드와 짝지어 같은 가명으로 통합한다.
        primary_column = name_columns[0]

        for column in name_columns:

            is_primary = column is primary_column

            for idx, value in df[column].items():

                if idx in footer_rows:
                    continue

                if pd.isna(value):
                    continue

                # 1순위 : 의사코드 (집도의 열에만 적용)
                if (
                    is_primary
                    and doctor_id_column
                    and not pd.isna(df.at[idx, doctor_id_column])
                ):

                    doctor_key = normalize_value(df.at[idx, doctor_id_column])

                # 2순위 : 진료과 + 이름
                elif (
                    department_column
                    and not pd.isna(df.at[idx, department_column])
                ):

                    doctor_key = (
                        normalize_value(df.at[idx, department_column])
                        + "|"
                        + normalize_value(value)
                    )

                # 3순위 : 이름만
                else:

                    doctor_key = normalize_value(value)

                pseudonym = self.generate_pseudonym(
                    doctor_key,
                    "DOC"
                )

                # 의료진 이름 열 변경
                df.at[idx, column] = pseudonym

                # 집도의 열이면 의사코드 열도 같은 값으로 변경
                if is_primary and doctor_id_column:
                    df.at[idx, doctor_id_column] = pseudonym
            
    def mask_free_text(self, df, column_map, footer_rows=None):
        """
        헤더로 분류되지 않은 자유 텍스트 열(비고/메모/특이사항 등)의
        문자열 셀에서 전화번호/주민번호/이메일을 마스킹한다.

        이미 구조화된 열(성명·전화번호 등)은 각 마스커가 처리하므로 제외하고,
        숫자/날짜 셀은 건드리지 않아 검사값 오탐을 피한다.
        """
        footer_rows = footer_rows or set()

        # column_map에서 이미 다뤄지는 모든 열을 수집한다.
        structured = set()
        for value in column_map.values():
            if value is None:
                continue
            if isinstance(value, list):
                structured.update(value)
            else:
                structured.add(value)

        for column in df.columns:

            if column in structured:
                continue

            for idx, value in df[column].items():

                if idx in footer_rows:
                    continue

                # 문자열 셀만 스캔 (숫자/날짜는 오탐 방지 위해 건드리지 않음)
                if not isinstance(value, str):
                    continue

                masked = mask_pii_in_text(value)

                if masked != value:
                    df.at[idx, column] = masked

    def shift_date(self, df, column_map, days, footer_rows=None):
        """
        모든 날짜를 '동일한' 오프셋(days)만큼 이동한다.

        날짜마다 랜덤하게 옮기지 않는 이유:
        고정 오프셋은 시간 구조를 그대로 보존한다 — 재원일수(퇴원일-입원일),
        방문 간격, 그리고 '어느 주/월에 속하는가' 하는 달력 정렬까지 유지된다.
        병원의 주간 통계(SARI/ASA/모니터링 등)가 이 관계에 의존하므로, 날짜별
        랜덤 이동을 하면 통계 로직 자체를 짤 수 없게 된다.
        (트레이드오프: 상대적 시점이 보존되므로 완전 익명화는 아니다.)
        """

        footer_rows = footer_rows or set()

        columns = column_map.get("date", [])

        if not columns:
            return

        for column in columns:

            # 날짜가 문자열로 저장된 열은 dtype이 str/datetime이라 Timestamp를
            # 바로 넣을 수 없다(pandas 3.0). object로 바꿔 안전하게 대입한다.
            df[column] = df[column].astype(object)

            for idx, value in df[column].items():

                if idx in footer_rows:
                    continue

                if pd.isna(value):
                    continue

                try:
                    date = pd.to_datetime(value)
                    date = date + timedelta(days=days)
                    df.at[idx, column] = date

                except Exception:
                    continue