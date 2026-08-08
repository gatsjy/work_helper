# -*- coding: utf-8 -*-
"""
클립보드 표 파싱 (집합 분석 탭 / Concat 탭 공용)

원래는 두 탭이 각자 다른 규칙으로 붙여넣기를 파싱했고, 둘 다 콤마에서 잘렸다.

    "Kim, John"  ->  "Kim"      # 값의 뒷부분이 조용히 사라진다

이건 크래시가 아니라서 더 나쁘다. 사용자는 잘린 결과를 그대로 엑셀에 복사해 간다.

핵심 규칙: **엑셀은 Ctrl+C 할 때 항상 TAB으로 구분한다.**
그래서 TAB이 있으면 TAB이 정답이다. TAB이 없을 때만 다른 가능성을 따진다.
"""
import re

TAB = "\t"
COMMA = ","

# 값 안에 그냥 들어있는 콤마("홍길동, 대리")와 진짜 CSV를 가르는 최소 필드 수.
# "성", "이름" 처럼 콤마 1개짜리는 CSV로 보지 않는다 — 이름 표기에서 훨씬 흔하다.
MIN_CSV_FIELDS = 3


def split_lines(text):
    """비어있지 않은 줄만 남긴다."""
    if not text or not text.strip():
        return []
    return [line for line in text.splitlines() if line.strip()]


def sniff_delimiter(lines):
    """구분자를 추정한다. 못 찾으면 None (= 한 줄이 곧 한 값).

    첫 줄만 보고 판단하지 않는다. 예전 코드는 첫 줄만 보다가, 첫 줄에 TAB이
    없으면 그 아래 TAB으로 구분된 줄들을 통째로 한 값처럼 다뤘다.
    """
    if not lines:
        return None

    # 1. TAB — 엑셀 클립보드의 실제 형식. 한 줄이라도 있으면 확정.
    if any(TAB in line for line in lines):
        return TAB

    # 2. 콤마 — 진짜 CSV처럼 보일 때만. 즉 모든 줄의 필드 수가 같고,
    #    필드가 MIN_CSV_FIELDS 개 이상일 때.
    counts = {line.count(COMMA) for line in lines}
    if len(counts) == 1:
        field_count = counts.pop() + 1
        if field_count >= MIN_CSV_FIELDS:
            return COMMA

    return None


def parse_rows(text):
    """붙여넣은 텍스트를 행 리스트로 만든다. 구분자가 없으면 한 줄 = 한 칸."""
    lines = split_lines(text)
    if not lines:
        return []

    delimiter = sniff_delimiter(lines)
    if delimiter is None:
        return [[line] for line in lines]

    return [line.split(delimiter) for line in lines]


def detect_vertical_block_size(lines, max_k=30):
    """세로로 죽 늘어선 1열 데이터에서 반복 주기 k를 찾는다.

    엑셀에서 N열짜리 표를 세로로 이어붙여 복사했을 때, k줄마다 같은 값이
    반복되는 패턴을 보고 원래 열 수를 되돌린다.
    """
    total = len(lines)
    for k in range(2, max_k + 1):
        if total < k * 2:
            continue
        checks = matches = 0
        for idx in range(k, total - k, k):
            checks += 1
            if lines[idx] == lines[idx + k]:
                matches += 1
        if checks >= 2 and (matches / checks) >= 0.5:
            return k
    return 0


def parse_table(text, detect_vertical=True):
    """Concat 탭용: 구분자 → 세로 패턴 → 다중 공백 순으로 표를 복원한다."""
    lines = split_lines(text)
    if not lines:
        return []

    delimiter = sniff_delimiter(lines)
    if delimiter is not None:
        return [line.split(delimiter) for line in lines]

    if detect_vertical:
        k = detect_vertical_block_size(lines)
        if k >= 2:
            rows = []
            for i in range(0, len(lines), k):
                chunk = lines[i:i + k]
                if len(chunk) < k:
                    chunk = chunk + [""] * (k - len(chunk))
                rows.append(chunk)
            return rows

    # 콘솔/리포트에서 복사한 고정폭 표: 대부분의 줄에 2칸 이상 공백이 있을 때만.
    sample = lines[:20]
    multi_space = [line for line in sample if re.search(r"\s{2,}", line)]
    if len(multi_space) >= min(len(lines), 4):
        return [re.split(r"\s{2,}", line) for line in lines]

    return [[line] for line in lines]


def column_letter(index):
    """0 -> A, 25 -> Z, 26 -> AA (엑셀식 열 이름)."""
    result = ""
    while index >= 0:
        result = chr((index % 26) + 65) + result
        index = (index // 26) - 1
    return result
