"""
HKDeID Command-line Interface

설치 후 `hkdeid <입력파일>` 로 실행하거나, 저장소에서 `python main.py <입력파일>`
로 실행할 수 있다.
"""
import argparse
import sys

from .engine import HKDeIDEngine
from .config import HKDeIDConfig
from .version import __version__


def build_parser():
    parser = argparse.ArgumentParser(
        prog="hkdeid",
        description=(
            "HKDeID - Medical Excel de-identification toolkit "
            "for health information managers"
        ),
    )
    parser.add_argument("input", help="입력 Excel 파일 (.xlsx)")
    parser.add_argument(
        "--config",
        metavar="PATH",
        help="설정 YAML 경로 (생략 시 번들 기본 설정 사용)",
    )
    parser.add_argument(
        "--date-shift-days",
        type=int,
        metavar="N",
        help="모든 날짜를 N일만큼 이동 (설정값 덮어씀)",
    )
    parser.add_argument(
        "--id-zero-pad",
        type=int,
        metavar="WIDTH",
        help="순수 숫자 등록번호를 WIDTH 자리로 zero-padding (0이면 사용 안 함)",
    )
    parser.add_argument(
        "--output-suffix",
        metavar="SUFFIX",
        help='출력 파일 접미사 (기본 "_deid")',
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"HKDeID {__version__}",
    )
    return parser


def _load_config(args):
    """--config 또는 기본 설정을 로드하고, CLI 옵션으로 덮어쓴다."""
    if args.config:
        config = HKDeIDConfig.from_yaml(args.config)
    else:
        config = HKDeIDConfig.default()

    if args.date_shift_days is not None:
        config.date_shift_days = args.date_shift_days
    if args.id_zero_pad is not None:
        config.id_zero_pad = args.id_zero_pad
    if args.output_suffix is not None:
        config.output_suffix = args.output_suffix

    return config


def main(argv=None):
    args = build_parser().parse_args(argv)

    config = _load_config(args)
    engine = HKDeIDEngine(config)

    try:
        engine.run(args.input)
    except FileNotFoundError as e:
        print(f"[error] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
