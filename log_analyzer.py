# -*- coding: utf-8 -*-
"""
로그 분석 엔진 (순수 파이썬 — Qt 의존성 없음)

설계 근거
---------
klogg / lnav / glogg 같은 기존 로그 도구는 전부 '빠른 뷰어'다. GB급 파일을 열고
grep·less·tail 을 묶어준다. 훌륭하지만, **어디를 봐야 하는지 이미 알고 있어야**
쓸모가 있다.

"유의미한 로그만 골라 한눈에" 는 다른 문제다. 순진하게 만들면 이렇게 된다:

    ERROR 로 필터 → 똑같은 에러 10,000줄

정보량은 한 줄과 다를 게 없다. 반대로 진짜 신호는 INFO 에 숨어 있기도 하다.

그래서 여기서는 **로그 템플릿 마이닝**(Drain 알고리즘, He et al. ICWS 2017)을 쓴다.
가변 토큰(숫자·ID·경로·IP…)을 <*> 로 치환해 같은 모양의 로그를 한 클러스터로 접으면:

    "Connection failed to <*> after <*> ms"   × 10,000
    "Disk quota exceeded on <*>"              × 1        ← 이게 진짜 신호

빈도가 낮은 템플릿, 뒤늦게 처음 나타난 템플릿, 갑자기 몰린 구간 —
이 세 가지가 사람이 실제로 봐야 하는 것이다.
"""
import io
import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta

# ---------------------------------------------------------------------------
# 인코딩
# ---------------------------------------------------------------------------
# 국내 윈도우 환경 로그는 UTF-8 만큼이나 CP949 가 흔하다. 잘못 잡으면 전부 깨진다.
ENCODING_CANDIDATES = ("utf-8", "cp949", "euc-kr", "latin-1")

BOM_ENCODINGS = (
    (b"\xef\xbb\xbf", "utf-8-sig"),
    (b"\xff\xfe\x00\x00", "utf-32-le"),
    (b"\x00\x00\xfe\xff", "utf-32-be"),
    (b"\xff\xfe", "utf-16-le"),
    (b"\xfe\xff", "utf-16-be"),
)


def detect_encoding(path, sample_size=262144):
    """BOM → UTF-8 → CP949 순으로 인코딩을 추정한다."""
    with open(path, "rb") as f:
        sample = f.read(sample_size)

    for bom, encoding in BOM_ENCODINGS:
        if sample.startswith(bom):
            return encoding

    # 샘플이 문자 중간에서 잘렸을 수 있으므로 끝 몇 바이트는 빼고 검사한다.
    for encoding in ENCODING_CANDIDATES:
        for trim in range(0, 4):
            chunk = sample[: len(sample) - trim] if trim else sample
            try:
                chunk.decode(encoding)
                return encoding
            except UnicodeDecodeError:
                continue
    return "utf-8"


# ---------------------------------------------------------------------------
# 한 줄 파싱
# ---------------------------------------------------------------------------
LEVEL_ALIASES = {
    "FATAL": "FATAL", "CRITICAL": "FATAL", "CRIT": "FATAL", "SEVERE": "FATAL",
    "ERROR": "ERROR", "ERR": "ERROR", "EXCEPTION": "ERROR",
    "WARN": "WARN", "WARNING": "WARN",
    "INFO": "INFO", "INFORMATION": "INFO", "NOTICE": "INFO",
    "DEBUG": "DEBUG", "FINE": "DEBUG", "VERBOSE": "DEBUG", "TRACE": "TRACE",
}
LEVEL_ORDER = ["FATAL", "ERROR", "WARN", "INFO", "DEBUG", "TRACE", "UNKNOWN"]
PROBLEM_LEVELS = ("FATAL", "ERROR", "WARN")

_LEVEL_RE = re.compile(
    r"(?<![A-Za-z])(" + "|".join(sorted(LEVEL_ALIASES, key=len, reverse=True)) + r")(?![A-Za-z])",
    re.IGNORECASE,
)

# 흔한 타임스탬프 형식들. (패턴, strptime 포맷)
_TIMESTAMP_PATTERNS = [
    (re.compile(r"(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})(?:[.,](\d{1,6}))?"), "%Y-%m-%d %H:%M:%S"),
    (re.compile(r"(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2})(?:[.,](\d{1,6}))?"), "%Y/%m/%d %H:%M:%S"),
    (re.compile(r"(\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2})(?:[.,](\d{1,6}))?"), "%m/%d/%Y %H:%M:%S"),
    (re.compile(r"(\d{8}[ T]\d{2}:\d{2}:\d{2})(?:[.,](\d{1,6}))?"), "%Y%m%d %H:%M:%S"),
    (re.compile(r"([A-Z][a-z]{2} [ \d]\d \d{2}:\d{2}:\d{2})"), "%b %d %H:%M:%S"),  # syslog
]


def match_timestamp(line):
    """줄 앞부분에서 타임스탬프를 뽑는다.

    (datetime|None, 매치가 끝난 위치) 를 돌려준다. 끝 위치를 같이 주는 이유는
    본문만 남길 때 정규식 5개를 다시 돌리는 대신 그냥 잘라내기 위해서다.
    """
    head = line[:64]
    for pattern, fmt in _TIMESTAMP_PATTERNS:
        match = pattern.search(head)
        if not match:
            continue
        text = match.group(1).replace("T", " ")
        try:
            stamp = datetime.strptime(text, fmt)
        except ValueError:
            continue
        if len(match.groups()) > 1 and match.group(2):
            micro = match.group(2).ljust(6, "0")[:6]
            stamp = stamp.replace(microsecond=int(micro))
        return stamp, match.end()
    return None, 0


def parse_timestamp(line):
    """줄 앞부분에서 타임스탬프를 뽑는다. 없으면 None."""
    return match_timestamp(line)[0]


def parse_level(line):
    """줄에서 로그 레벨을 뽑는다. 앞부분 위주로 본다(본문 오탐 방지)."""
    match = _LEVEL_RE.search(line[:120])
    if match:
        return LEVEL_ALIASES[match.group(1).upper()]
    return "UNKNOWN"


# 스택 트레이스 이어지는 줄 판정.
# 스택 트레이스는 '하나의 사건'이다. 30줄로 세면 통계가 통째로 망가진다.
_CONTINUATION_RE = re.compile(
    r"^(\s+|at\s|Caused by:|\.{3}\s|Traceback|\s*File\s\"|##|\||\+|	)"
)


def is_continuation(line):
    if not line.strip():
        return False
    if parse_timestamp(line) is not None:
        return False
    return bool(_CONTINUATION_RE.match(line))


# 파이썬 트레이스백은 마지막 줄이 들여쓰기 없이 "ValueError: bad" 로 끝난다.
# 줄 하나만 봐서는 새 로그와 구분할 수 없으므로, 트레이스백에 들어갔다는
# 상태를 기억했다가 이 종료 줄에서 빠져나온다.
_TRACEBACK_START_RE = re.compile(r"^\s*Traceback \(most recent call last\)\s*:")
_EXCEPTION_END_RE = re.compile(
    r"^[A-Za-z_][\w.]*(?:Error|Exception|Exit|Interrupt|Warning|Fault|Abort)\b"
)


@dataclass
class LogEntry:
    line_no: int                      # 1-based, 원본 파일 기준
    timestamp: datetime = None
    level: str = "UNKNOWN"
    message: str = ""
    raw: str = ""
    extra_lines: list = field(default_factory=list)   # 스택 트레이스 등

    @property
    def line_count(self):
        return 1 + len(self.extra_lines)

    @property
    def full_text(self):
        return "\n".join([self.raw] + self.extra_lines)


_LEAD_PUNCT_RE = re.compile(r"^[\s\-:\|\]\[]+")
_LEAD_BRACKET_RE = re.compile(r"^\[[^\]]{0,40}\]\s*")
_LEAD_PAREN_RE = re.compile(r"^\([^)]{0,60}\)\s*")


def strip_prefix(line, timestamp_end=0):
    """타임스탬프/레벨/스레드 등 앞쪽 상용구를 걷어내고 메시지 본문만 남긴다.

    timestamp_end 는 match_timestamp() 가 알려준 끝 위치다. 이미 아는 걸
    다시 찾지 않도록 그 지점부터 자른다.
    """
    text = line[timestamp_end:] if timestamp_end else line
    text = _LEVEL_RE.sub("", text, count=1)
    # [thread-1] (Class.java:42) 같은 머리말 제거
    text = _LEAD_PUNCT_RE.sub("", text)
    text = _LEAD_BRACKET_RE.sub("", text)
    text = _LEAD_PAREN_RE.sub("", text)
    return text.strip() or line.strip()


def iter_entries(lines):
    """줄 목록을 로그 '사건' 단위로 접는다."""
    entries = []
    in_traceback = False

    for idx, raw in enumerate(lines, start=1):
        if not raw.strip():
            continue

        # 타임스탬프는 줄마다 한 번만 찾는다 (예전에는 이어짐 판정에서 한 번,
        # 항목 생성에서 또 한 번 — 같은 정규식을 두 배로 돌리고 있었다).
        stamp, stamp_end = match_timestamp(raw)

        # 트레이스백 안이라면, 타임스탬프가 나오기 전까지는 전부 같은 사건이다.
        if entries and in_traceback and stamp is None:
            entries[-1].extra_lines.append(raw.rstrip("\n"))
            if _EXCEPTION_END_RE.match(raw):
                in_traceback = False
            continue

        if entries and stamp is None and _CONTINUATION_RE.match(raw):
            entries[-1].extra_lines.append(raw.rstrip("\n"))
            if _TRACEBACK_START_RE.match(raw):
                in_traceback = True
            continue

        in_traceback = False
        stripped = raw.rstrip("\n")
        entry = LogEntry(
            line_no=idx,
            timestamp=stamp,
            level=parse_level(raw),
            message=strip_prefix(stripped, stamp_end),
            raw=stripped,
        )
        entries.append(entry)
    return entries


# ---------------------------------------------------------------------------
# 토큰 마스킹
# ---------------------------------------------------------------------------
# 순서가 중요하다. 넓은 패턴을 먼저 두면 좁은 패턴이 먹히지 않는다.
_MASKS = [
    (re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"), "<UUID>"),
    (re.compile(r"\b\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?"), "<TIME>"),
    (re.compile(r"\b\d{2}:\d{2}:\d{2}(?:[.,]\d+)?"), "<TIME>"),
    (re.compile(r"\b\d{4}-\d{2}-\d{2}\b"), "<DATE>"),
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b"), "<EMAIL>"),
    (re.compile(r"\bhttps?://\S+"), "<URL>"),
    (re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?\b"), "<IP>"),
    (re.compile(r"\b[A-Za-z]:\\[^\s,;)\]]+"), "<PATH>"),
    (re.compile(r"(?<![\w.])/(?:[\w.-]+/){2,}[\w.-]*"), "<PATH>"),
    (re.compile(r"\b0x[0-9a-fA-F]+\b"), "<HEX>"),
    (re.compile(r"\b[0-9a-fA-F]{16,}\b"), "<HEX>"),
    # 단위가 붙은 수치(300s, 1.5MB, 20ms). 이걸 먼저 잡지 않으면 뒤의 숫자 패턴이
    # 글자 앞에서 멈춰버려 "300s" 가 통째로 변수로 남고, 템플릿이 <*> 로 뭉개진다.
    (re.compile(r"(?<![\w.])[-+]?\d+(?:\.\d+)?\s?"
                r"(?:ms|ns|us|μs|sec|secs|s|min|mins|m|hr|hrs|h|d"
                r"|kb|mb|gb|tb|kib|mib|gib|b)(?![\w.])", re.IGNORECASE), "<QTY>"),
    (re.compile(r"(?<![\w.])[-+]?\d+\.\d+(?![\w.])"), "<NUM>"),
    (re.compile(r"(?<![\w.])[-+]?\d+(?![\w.])"), "<NUM>"),
]


def mask_variables(message):
    """로그 본문에서 값이 매번 달라지는 부분을 자리표시자로 바꾼다."""
    text = message
    for pattern, placeholder in _MASKS:
        text = pattern.sub(placeholder, text)
    return text


# ---------------------------------------------------------------------------
# Drain 스타일 템플릿 마이닝
# ---------------------------------------------------------------------------
WILDCARD = "<*>"


@dataclass
class Template:
    template_id: int
    tokens: list
    count: int = 0
    level_counts: Counter = field(default_factory=Counter)
    first_line: int = 0
    last_line: int = 0
    first_seen: datetime = None
    last_seen: datetime = None
    samples: list = field(default_factory=list)     # LogEntry (최대 SAMPLE_LIMIT 개)

    SAMPLE_LIMIT = 20

    @property
    def text(self):
        return " ".join(self.tokens)

    @property
    def level(self):
        """이 템플릿의 대표 레벨 (가장 심각한 쪽)."""
        for level in LEVEL_ORDER:
            if self.level_counts.get(level):
                return level
        return "UNKNOWN"

    @property
    def is_problem(self):
        return self.level in PROBLEM_LEVELS

    def absorb(self, entry, masked_tokens):
        """새 로그를 이 템플릿에 흡수하고, 달라진 토큰은 와일드카드로 일반화한다."""
        if self.count:
            self.tokens = [
                a if a == b else WILDCARD
                for a, b in zip(self.tokens, masked_tokens)
            ]
        else:
            self.tokens = list(masked_tokens)

        self.count += 1
        self.level_counts[entry.level] += 1

        if not self.first_line:
            self.first_line = entry.line_no
        self.last_line = entry.line_no

        if entry.timestamp:
            if self.first_seen is None or entry.timestamp < self.first_seen:
                self.first_seen = entry.timestamp
            if self.last_seen is None or entry.timestamp > self.last_seen:
                self.last_seen = entry.timestamp

        if len(self.samples) < self.SAMPLE_LIMIT:
            self.samples.append(entry)


class TemplateMiner:
    """고정 깊이 트리 기반 온라인 로그 템플릿 마이너 (Drain).

    전체를 서로 비교하면 O(n²)이라 큰 로그에서 못 쓴다. Drain 은
    '토큰 개수 → 앞쪽 토큰들' 로 트리를 타서 후보를 좁힌 뒤, 그 안에서만
    유사도를 비교한다. 깊이를 고정해 트리가 한없이 깊어지는 것도 막는다.
    """

    def __init__(self, depth=4, similarity_threshold=0.4, max_children=100):
        # 루트/리프를 뺀 실제 비교 깊이
        self.depth = max(depth - 2, 1)
        self.threshold = similarity_threshold
        self.max_children = max_children
        self._root = {}
        self.templates = []

    def _tree_leaf(self, tokens, create):
        """토큰 개수 + 앞쪽 토큰들로 리프(템플릿 후보 목록)를 찾는다."""
        node = self._root.setdefault(len(tokens), {}) if create else self._root.get(len(tokens))
        if node is None:
            return None

        for depth_idx in range(min(self.depth, len(tokens))):
            token = tokens[depth_idx]
            # 숫자가 섞인 토큰은 값일 가능성이 높아 한 갈래로 몰아준다.
            if any(ch.isdigit() for ch in token):
                token = WILDCARD

            child = node.get(token)
            if child is None:
                if not create:
                    child = node.get(WILDCARD)
                    if child is None:
                        return None
                    node = child
                    continue
                if len(node) >= self.max_children:
                    token = WILDCARD
                    child = node.setdefault(token, {})
                else:
                    child = node.setdefault(token, {})
            node = child

        return node.setdefault("\x00leaf", []) if create else node.get("\x00leaf")

    @staticmethod
    def _similarity(template_tokens, tokens):
        """같은 자리 토큰이 얼마나 일치하는지 (와일드카드는 0점으로 센다)."""
        if not template_tokens:
            return 0.0
        matched = sum(
            1 for a, b in zip(template_tokens, tokens)
            if a == b and a != WILDCARD
        )
        return matched / len(template_tokens)

    def add(self, entry):
        """로그 하나를 넣고, 매칭된 템플릿을 돌려준다."""
        tokens = mask_variables(entry.message).split()
        if not tokens:
            tokens = ["<empty>"]

        leaf = self._tree_leaf(tokens, create=True)

        best, best_score = None, -1.0
        for template in leaf:
            score = self._similarity(template.tokens, tokens)
            if score > best_score:
                best, best_score = template, score

        if best is None or best_score < self.threshold:
            best = Template(template_id=len(self.templates), tokens=list(tokens))
            self.templates.append(best)
            leaf.append(best)

        best.absorb(entry, tokens)
        return best


# ---------------------------------------------------------------------------
# 리포트
# ---------------------------------------------------------------------------
@dataclass
class Highlight:
    kind: str          # rare | problem | burst | newcomer
    title: str
    detail: str
    template: Template = None
    line_no: int = 0


@dataclass
class TimeBucket:
    start: datetime
    total: int = 0
    problems: int = 0


@dataclass
class LogReport:
    path: str = ""
    encoding: str = ""
    total_lines: int = 0
    parsed_entries: int = 0
    truncated: bool = False
    level_counts: Counter = field(default_factory=Counter)
    templates: list = field(default_factory=list)
    buckets: list = field(default_factory=list)
    highlights: list = field(default_factory=list)
    first_seen: datetime = None
    last_seen: datetime = None
    entries: list = field(default_factory=list)

    @property
    def problem_count(self):
        return sum(self.level_counts.get(lv, 0) for lv in PROBLEM_LEVELS)

    @property
    def compression_ratio(self):
        """몇 줄이 템플릿 하나로 접혔는지 — '한눈에' 가 가능한 이유."""
        if not self.templates:
            return 0.0
        return self.parsed_entries / len(self.templates)


# 이 횟수 이하로 나타난 템플릿은 '드문 것' = 볼 가치가 있는 것으로 본다.
RARE_MAX_COUNT = 3
MAX_HIGHLIGHTS_PER_KIND = 8


def _build_buckets(entries, target_buckets=60):
    """시간축 히스토그램. 타임스탬프가 없으면 빈 목록."""
    stamped = [e for e in entries if e.timestamp]
    if len(stamped) < 2:
        return []

    start = min(e.timestamp for e in stamped)
    end = max(e.timestamp for e in stamped)
    span = (end - start).total_seconds()
    if span <= 0:
        return []

    width = max(span / target_buckets, 1.0)
    buckets = {}
    for entry in stamped:
        idx = int((entry.timestamp - start).total_seconds() // width)
        bucket = buckets.get(idx)
        if bucket is None:
            bucket = TimeBucket(start=start + timedelta(seconds=idx * width))
            buckets[idx] = bucket
        bucket.total += 1
        if entry.level in PROBLEM_LEVELS:
            bucket.problems += 1

    return [buckets[k] for k in sorted(buckets)]


def _find_bursts(buckets):
    """문제 로그가 평소보다 튀어 오른 구간을 찾는다."""
    problem_counts = [b.problems for b in buckets]
    if len(problem_counts) < 4 or not any(problem_counts):
        return []

    mean = sum(problem_counts) / len(problem_counts)
    variance = sum((c - mean) ** 2 for c in problem_counts) / len(problem_counts)
    std = variance ** 0.5
    if std == 0:
        return []

    threshold = mean + 2 * std
    return [b for b in buckets if b.problems > threshold and b.problems > 1]


def _build_highlights(report):
    """사람이 실제로 봐야 할 것만 골라낸다."""
    highlights = []
    templates = report.templates
    if not templates:
        return highlights

    # 1) 심각한데 자주 터진 것 — 지금 무너지고 있는 것
    problems = sorted(
        [t for t in templates if t.is_problem],
        key=lambda t: -t.count,
    )
    for template in problems[:MAX_HIGHLIGHTS_PER_KIND]:
        highlights.append(Highlight(
            kind="problem",
            title=f"[{template.level}] {template.count:,}회",
            detail=template.text,
            template=template,
            line_no=template.first_line,
        ))

    # 2) 드문 템플릿 — 파묻혀서 안 보이던 것. 여기가 핵심이다.
    rare = sorted(
        [t for t in templates if t.count <= RARE_MAX_COUNT],
        key=lambda t: (t.count, -LEVEL_ORDER.index(t.level)),
    )
    for template in rare[:MAX_HIGHLIGHTS_PER_KIND]:
        highlights.append(Highlight(
            kind="rare",
            title=f"드묾 · {template.count}회 · {template.level}",
            detail=template.text,
            template=template,
            line_no=template.first_line,
        ))

    # 3) 뒤늦게 처음 나타난 템플릿 — 새로 생긴 고장
    if report.parsed_entries > 50:
        late_start = report.parsed_entries * 0.8
        newcomers = [
            t for t in templates
            if t.first_line >= late_start and t.count >= 2
        ]
        newcomers.sort(key=lambda t: -t.count)
        for template in newcomers[:MAX_HIGHLIGHTS_PER_KIND]:
            highlights.append(Highlight(
                kind="newcomer",
                title=f"후반부에 처음 등장 · {template.count}회",
                detail=template.text,
                template=template,
                line_no=template.first_line,
            ))

    # 4) 급증 구간
    for bucket in _find_bursts(report.buckets)[:MAX_HIGHLIGHTS_PER_KIND]:
        highlights.append(Highlight(
            kind="burst",
            title=f"급증 · {bucket.start:%Y-%m-%d %H:%M:%S}",
            detail=f"이 구간에서 문제 로그 {bucket.problems:,}건 (전체 {bucket.total:,}건)",
        ))

    return highlights


def read_log_lines(path, max_lines=0, encoding=None):
    """로그 파일을 줄 목록으로 읽는다. (읽은 줄, 인코딩, 잘렸는지)"""
    encoding = encoding or detect_encoding(path)
    lines = []
    truncated = False

    with io.open(path, "r", encoding=encoding, errors="replace", newline="") as f:
        for idx, line in enumerate(f):
            if max_lines and idx >= max_lines:
                truncated = True
                break
            lines.append(line.rstrip("\r\n"))

    return lines, encoding, truncated


def analyze_log(path, max_lines=0, encoding=None, progress=None,
                similarity_threshold=0.4):
    """로그 파일 하나를 분석해 LogReport 를 돌려준다."""
    progress = progress or (lambda *_: None)

    if not os.path.exists(path):
        raise FileNotFoundError(f"로그 파일을 찾을 수 없습니다: {path}")

    progress(5, "파일 읽는 중...")
    lines, encoding, truncated = read_log_lines(path, max_lines, encoding)

    progress(25, "로그 항목 파싱 중...")
    entries = iter_entries(lines)

    progress(45, "템플릿 추출 중...")
    miner = TemplateMiner(similarity_threshold=similarity_threshold)
    level_counts = Counter()
    step = max(len(entries) // 20, 1)

    for idx, entry in enumerate(entries):
        miner.add(entry)
        level_counts[entry.level] += 1
        if idx % step == 0:
            progress(45 + int(idx / max(len(entries), 1) * 40), "템플릿 추출 중...")

    progress(88, "요약 만드는 중...")
    stamped = [e.timestamp for e in entries if e.timestamp]

    report = LogReport(
        path=path,
        encoding=encoding,
        total_lines=len(lines),
        parsed_entries=len(entries),
        truncated=truncated,
        level_counts=level_counts,
        templates=sorted(miner.templates, key=lambda t: -t.count),
        first_seen=min(stamped) if stamped else None,
        last_seen=max(stamped) if stamped else None,
        entries=entries,
    )
    report.buckets = _build_buckets(entries)
    report.highlights = _build_highlights(report)

    progress(100, "완료")
    return report
