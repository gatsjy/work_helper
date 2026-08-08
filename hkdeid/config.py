"""
HKDeID Configuration
"""

from dataclasses import dataclass, fields
from pathlib import Path
import yaml

# 저장소 루트의 기본 설정 파일 (hkdeid/config.py -> ../configs/default.yaml)
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "configs" / "default.yaml"


@dataclass
class HKDeIDConfig:
    """Configuration for HKDeID."""

    # Date
    date_shift_days: int = -1000

    # Personal Information
    mask_name: bool = True
    mask_patient_id: bool = True
    mask_doctor: bool = True
    mask_doctor_id: bool = False
    mask_rrn: bool = True
    mask_phone: bool = True
    mask_address: bool = True
    mask_email: bool = True
    shift_date: bool = True

    # 헤더로 분류되지 않은 자유 텍스트 열(비고/메모 등)에서 전화/주민/이메일
    # 패턴을 찾아 마스킹한다. 문자열 셀 + 형식이 뚜렷한 패턴만 다룬다.
    mask_free_text: bool = True

    # Hospital Information
    replace_hospital: bool = True
    replace_doctor: bool = True

    # Identifier normalization
    # 등록번호가 순수 숫자일 때 지정 자릿수로 0을 채워, 시트마다 자릿수만
    # 다르게 기록된 같은 환자를 통일한다. 0이면 사용 안 함.
    id_zero_pad: int = 0

    # Output
    output_suffix: str = "_deid"
    
    @classmethod
    def from_yaml(cls, path: str):
        """Load configuration from a YAML file.

        데이터클래스에 없는 키는 무시해, YAML에 오타/구버전 키가 있어도
        전체 로딩이 실패하지 않도록 한다.
        """

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        known = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in data.items() if k in known}

        return cls(**filtered)

    @classmethod
    def default(cls):
        """기본 설정을 로드한다.

        번들된 configs/default.yaml 을 현재 작업 디렉터리와 무관하게 찾아
        로드하고, 파일이 없으면 데이터클래스 기본값을 사용한다.
        """
        if DEFAULT_CONFIG_PATH.exists():
            return cls.from_yaml(str(DEFAULT_CONFIG_PATH))

        return cls()