"""
HKDeID Engine
"""
from .excel import (
    load_workbook_file,
    worksheet_to_dataframe,
    dataframe_to_worksheet,
    save_workbook,
)
from .masker import Masker, normalize_value
from .analyzer import ColumnAnalyzer
from .config import HKDeIDConfig
from .version import __version__
from pathlib import Path
from collections import defaultdict
import pandas as pd


class HKDeIDEngine:
    """Main execution engine."""

    def __init__(self, config=None):
        self.version = __version__

        # config 인자로 HKDeIDConfig 또는 YAML 경로를 넘길 수 있고,
        # 생략하면 번들된 기본 설정(작업 디렉터리 무관)을 로드한다.
        if config is None:
            self.config = HKDeIDConfig.default()
        elif isinstance(config, HKDeIDConfig):
            self.config = config
        else:
            self.config = HKDeIDConfig.from_yaml(str(config))

    def run(self, input_path):
        
        input_path = Path(input_path)

        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")

        print("=" * 60)
        print(f"HKDeID v{self.version}")
        print("Medical Excel De-identification Toolkit")
        print("=" * 60)

        print("[1/5] Loading configuration...")

        print("[2/5] Loading Excel file...")
        workbook = load_workbook_file(input_path)

        total_rows = 0
        sheet_count = 0

        # 시트 간 환자 링크 감사(audit)용 집계.
        # 마스킹 '전' 원본값을 정규화해서 모아, 같은 등록번호가 여러 시트에
        # 걸쳐 있는지 / 데이터 이상은 없는지 확인한다.
        id_to_sheets = defaultdict(set)   # 정규화 등록번호 -> {시트명}
        id_to_names = defaultdict(set)    # 정규화 등록번호 -> {정규화 이름}
        name_to_ids = defaultdict(set)    # 정규화 이름     -> {정규화 등록번호}

        print("[3/5] Processing worksheets...")

        for ws in workbook.worksheets:

            print("-" * 50)
            print(f"Sheet : {ws.title}")

            analyzer = ColumnAnalyzer()

            df, header_row, footer_rows = worksheet_to_dataframe(
                ws,
                analyzer,
            )

            if df.empty:
                print("Empty sheet - Skip")
                continue

            print("Columns :", df.columns.tolist())

            column_map = analyzer.analyze(df)

            print(column_map)

            # 마스킹 전에 원본 등록번호/이름 링크를 수집한다.
            self._collect_linkage(
                df,
                column_map,
                footer_rows,
                ws.title,
                id_to_sheets,
                id_to_names,
                name_to_ids,
            )

            masker = Masker()
            df = masker.mask(df, column_map, self.config, footer_rows)

            dataframe_to_worksheet(
                ws,
                df,
                header_row,
            )

            print(f"Processed {len(df)} rows.")

            total_rows += len(df)
            sheet_count += 1
        output_path = save_workbook(
            workbook,
            input_path,
            self.config.output_suffix
        )

        print(f"Output : {output_path}")

        print("[4/5] Validating results...")
        self._validate_linkage(id_to_sheets, id_to_names, name_to_ids)

        print("[5/5] Generating report...")

        print()
        print("HKDeID finished successfully.")
        print(f"Sheets           : {sheet_count}")
        print(f"Rows             : {total_rows}")
        print(f"Unique patients  : {len(id_to_sheets)}")
        print(
            "Cross-sheet linked : "
            f"{sum(1 for s in id_to_sheets.values() if len(s) > 1)}"
        )

    def _collect_linkage(
        self,
        df,
        column_map,
        footer_rows,
        sheet_title,
        id_to_sheets,
        id_to_names,
        name_to_ids,
    ):
        """마스킹 전 원본값을 정규화해 환자 링크 정보를 누적한다."""

        pid_col = column_map.get("patient_id")
        name_col = column_map.get("patient_name")

        if pid_col is None:
            return

        # 감사(audit)의 등록번호 정규화는 실제 가명 키와 동일해야 하므로
        # 마스킹과 같은 zero-padding 설정을 적용한다.
        id_zero_pad = getattr(self.config, "id_zero_pad", 0)

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

    def _validate_linkage(self, id_to_sheets, id_to_names, name_to_ids):
        """
        시트 간 환자 링크의 일관성/이상을 점검한다.

        정규화된 등록번호가 같으면 항상 같은 가명이 나오는 것은 설계상
        보장되므로, 여기서는 '통일할 수 없는' 데이터 이상만 보고한다.
        """

        # 같은 등록번호인데 이름이 여러 개 -> 등록번호 오입력 가능성
        id_conflicts = {
            norm_id: names
            for norm_id, names in id_to_names.items()
            if len(names) > 1
        }

        # 같은 이름인데 등록번호가 여러 개 -> 동명이인 또는 링크 분할 가능성
        name_splits = {
            norm_name: ids
            for norm_name, ids in name_to_ids.items()
            if len(ids) > 1
        }

        if not id_conflicts and not name_splits:
            print("  - No linkage anomalies detected.")
            return

        if id_conflicts:
            print(
                f"  [!] 같은 등록번호에 다른 이름이 섞임 : {len(id_conflicts)}건 "
                "(등록번호 오입력 확인 필요)"
            )

        if name_splits:
            print(
                f"  [!] 같은 이름이 여러 등록번호로 나뉨 : {len(name_splits)}건 "
                "(동명이인이거나, 시트마다 등록번호가 다르게 기록됐을 수 있음)"
            )