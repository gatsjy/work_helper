# -*- coding: utf-8 -*-
import pandas as pd
import os
from excel_processor import ExcelSetProcessor

def make_sample_data():
    data_a = [
        "홍길동", "김철수", "이영희", "박민수", 
        "최유진", "정재훈", "강민아", "윤서준", "  김철수  "
    ]
    data_b = [
        "김철수", "LEE YOUNG-HEE", "최유진", "윤서준", 
        "한지우", "송태양", "임수빈"
    ]
    
    max_len = max(len(data_a), len(data_b))
    data_a += [None] * (max_len - len(data_a))
    data_b += [None] * (max_len - len(data_b))

    df = pd.DataFrame({
        "전산팀_명단": data_a,
        "인사팀_등록명단": data_b
    })
    
    sample_path = "sample_data.xlsx"
    df.to_excel(sample_path, sheet_name="임직원비교", index=False)
    return sample_path

def test_excel_processor():
    sample_path = make_sample_data()
    processor = ExcelSetProcessor(sample_path)
    
    sheets = processor.get_sheet_names()
    print(f"Sheets loaded: {len(sheets)}")
    
    cols = processor.get_columns("임직원비교")
    print(f"Columns: {cols}")
    
    result = processor.analyze_sets(
        sheet_a="임직원비교",
        col_a="전산팀_명단",
        sheet_b="임직원비교",
        col_b="인사팀_등록명단",
        case_sensitive=False,
        trim_space=True,
        drop_empty=True
    )
    
    stats = result['stats']
    print("--- Analysis Results ---")
    print(f"Unique A: {stats['unique_a_count']}, Unique B: {stats['unique_b_count']}")
    print(f"Intersection (교집합): {len(result['intersection'])}")
    print(f"A Only (차집합 A): {len(result['a_only'])}")
    print(f"B Only (차집합 B): {len(result['b_only'])}")
    print(f"Symmetric Diff (대칭차집합): {len(result['sym_diff'])}")
    print(f"Union (합집합): {len(result['union'])}")
    
    output_excel = "test_output_report.xlsx"
    processor.export_excel_report(result, output_excel)
    print(f"Report exported successfully to {output_excel}")

if __name__ == "__main__":
    test_excel_processor()
