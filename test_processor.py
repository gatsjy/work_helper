# -*- coding: utf-8 -*-
"""
집합 분석 / 클립보드 파싱 테스트.

예전 이 파일은 print 만 하고 assert 가 하나도 없었다. 결과가 틀려도 통과했다.
여기 있는 케이스들은 대부분 실제로 발견된 버그를 고정한 것이다.
"""
import pytest

from clipboard_parser import (
    parse_rows, parse_table, sniff_delimiter, column_letter,
    detect_vertical_block_size,
)
from excel_processor import ExcelSetProcessor


def vals(items):
    return [item['val'] for item in items]


# ---------------------------------------------------------------------------
# 클립보드 파싱
# ---------------------------------------------------------------------------
class TestDelimiterSniffing:

    def test_tab_wins(self):
        assert sniff_delimiter(["a\tb", "c\td"]) == "\t"

    def test_tab_detected_even_if_first_line_has_none(self):
        # 회귀: 예전에는 첫 줄만 보고 판단해서, 아래 TAB 줄들을 통째로
        # 한 값처럼 다뤘다.
        assert sniff_delimiter(["plainvalue", "x\ty", "z\tw"]) == "\t"

    def test_name_with_comma_is_not_csv(self):
        # 회귀: "Kim, John" -> "Kim" 으로 잘리던 문제.
        assert sniff_delimiter(["Kim, John", "Lee, Ann"]) is None

    def test_real_csv_is_detected(self):
        assert sniff_delimiter(["a,b,c", "d,e,f"]) == ","

    def test_ragged_comma_counts_are_not_csv(self):
        assert sniff_delimiter(["a,b,c", "d,e"]) is None

    def test_plain_lines_have_no_delimiter(self):
        assert sniff_delimiter(["USR001", "USR002"]) is None


class TestParseRows:

    def test_comma_containing_values_stay_whole(self):
        rows = parse_rows("Kim, John\nLee, Ann")
        assert rows == [["Kim, John"], ["Lee, Ann"]]

    def test_tab_separated_splits(self):
        assert parse_rows("a\tb\nc\td") == [["a", "b"], ["c", "d"]]

    def test_blank_lines_dropped(self):
        assert parse_rows("a\n\n  \nb") == [["a"], ["b"]]

    def test_empty_input(self):
        assert parse_rows("") == []
        assert parse_rows("   \n  ") == []


class TestParseTable:

    def test_vertical_block_detection(self):
        # 3열짜리 표를 세로로 이어붙여 복사한 형태
        text = "\n".join(["이름", "부서", "직급"] * 4)
        assert detect_vertical_block_size(text.splitlines()) == 3
        rows = parse_table(text)
        assert all(len(r) == 3 for r in rows)
        assert rows[0] == ["이름", "부서", "직급"]

    def test_single_column_stays_single(self):
        rows = parse_table("USR001\nUSR002\nUSR003")
        assert rows == [["USR001"], ["USR002"], ["USR003"]]

    def test_tab_table(self):
        rows = parse_table("A\tB\n1\t2\n3\t4")
        assert rows == [["A", "B"], ["1", "2"], ["3", "4"]]


class TestColumnLetter:

    @pytest.mark.parametrize("index,expected", [
        (0, "A"), (1, "B"), (25, "Z"), (26, "AA"), (27, "AB"), (51, "AZ"), (52, "BA"),
    ])
    def test_letters(self, index, expected):
        assert column_letter(index) == expected


# ---------------------------------------------------------------------------
# 집합 연산
# ---------------------------------------------------------------------------
class TestSetAnalysis:

    def test_basic_set_operations(self):
        result = ExcelSetProcessor.analyze_raw_text_sets(
            "USR001\nUSR002\nUSR003\nUSR004\nUSR005",
            "USR003\nUSR004\nUSR005\nUSR006\nUSR007",
        )
        stats = result['stats']
        assert stats['intersection_count'] == 3
        assert stats['a_only_count'] == 2
        assert stats['b_only_count'] == 2
        assert stats['sym_diff_count'] == 4
        assert stats['union_count'] == 7
        assert vals(result['a_only']) == ["USR001", "USR002"]
        assert vals(result['b_only']) == ["USR006", "USR007"]

    def test_values_with_commas_are_not_truncated(self):
        # 회귀: 교집합이 "Kim" 으로 나오던 문제.
        result = ExcelSetProcessor.analyze_raw_text_sets(
            "Kim, John\nLee, Ann\nPark, Bo",
            "Kim, John\nChoi, Dae",
        )
        assert vals(result['intersection']) == ["Kim, John"]
        assert result['stats']['unique_a_count'] == 3

    def test_case_insensitive_by_default(self):
        result = ExcelSetProcessor.analyze_raw_text_sets("ABC", "abc")
        assert result['stats']['intersection_count'] == 1

    def test_case_sensitive_when_requested(self):
        result = ExcelSetProcessor.analyze_raw_text_sets(
            "ABC", "abc", case_sensitive=True
        )
        assert result['stats']['intersection_count'] == 0

    def test_trim_collapses_padded_duplicates(self):
        result = ExcelSetProcessor.analyze_raw_text_sets(
            "  kim  \nkim", "kim", trim_space=True
        )
        assert result['stats']['unique_a_count'] == 1

    def test_header_row_excluded(self):
        result = ExcelSetProcessor.analyze_raw_text_sets(
            "사번\nE001\nE002",
            "사번\nE002\nE003",
            has_header_a=True, has_header_b=True,
        )
        assert result['stats']['unique_a_count'] == 2
        assert vals(result['intersection']) == ["E002"]

    def test_empty_values_dropped(self):
        result = ExcelSetProcessor.analyze_raw_text_sets(
            "a\n\nb", "a", drop_empty=True
        )
        assert result['stats']['unique_a_count'] == 2

    def test_both_empty_inputs(self):
        result = ExcelSetProcessor.analyze_raw_text_sets("", "")
        assert result['stats']['union_count'] == 0
        assert result['intersection'] == []

    def test_one_side_empty(self):
        result = ExcelSetProcessor.analyze_raw_text_sets("a\nb", "")
        assert result['stats']['a_only_count'] == 2
        assert result['stats']['intersection_count'] == 0

    def test_multi_column_paste_uses_selected_column(self):
        result = ExcelSetProcessor.analyze_raw_text_sets(
            "a\tX\nb\tY", "Y\tz", col_a_idx=1, col_b_idx=0
        )
        assert vals(result['intersection']) == ["Y"]

    def test_origin_labels(self):
        result = ExcelSetProcessor.analyze_raw_text_sets("a\nc", "b\nc")
        assert result['a_only'][0]['origin'] == "A전용(차집합A)"
        assert result['b_only'][0]['origin'] == "B전용(차집합B)"
        assert result['intersection'][0]['origin'] == "공통(교집합)"

    def test_sym_diff_is_a_only_plus_b_only(self):
        result = ExcelSetProcessor.analyze_raw_text_sets("a\nb\nc", "c\nd")
        assert vals(result['sym_diff']) == vals(result['a_only']) + vals(result['b_only'])
