# -*- coding: utf-8 -*-
"""
로그 분석 엔진 테스트.

이 툴의 가치는 '노이즈에 파묻힌 신호를 끌어올리는 것'이므로,
테스트도 그 성질을 직접 검증한다.
"""
import pytest

from log_analyzer import (
    analyze_log, detect_encoding, iter_entries, is_continuation,
    mask_variables, parse_level, parse_timestamp, TemplateMiner, LogEntry,
)


def write(tmp_path, text, name="app.log", encoding="utf-8"):
    path = tmp_path / name
    path.write_text(text, encoding=encoding)
    return str(path)


class TestEncoding:

    def test_utf8(self, tmp_path):
        path = write(tmp_path, "정상 로그\n한글\n")
        assert detect_encoding(path) in ("utf-8", "utf-8-sig")

    def test_cp949_korean_log(self, tmp_path):
        # 국내 윈도우 로그에서 아주 흔한 경우. 잘못 잡으면 전부 깨진다.
        path = write(tmp_path, "접속 실패\n재시도 중\n", encoding="cp949")
        assert detect_encoding(path) in ("cp949", "euc-kr")

    def test_utf8_bom(self, tmp_path):
        path = write(tmp_path, "로그\n", encoding="utf-8-sig")
        assert detect_encoding(path) == "utf-8-sig"


class TestLineParsing:

    @pytest.mark.parametrize("line", [
        "2026-08-07 09:00:01 INFO started",
        "2026-08-07T09:00:01.123 INFO started",
        "2026/08/07 09:00:01 INFO started",
    ])
    def test_timestamp_formats(self, line):
        stamp = parse_timestamp(line)
        assert stamp is not None
        assert stamp.year == 2026 and stamp.hour == 9

    def test_no_timestamp(self):
        assert parse_timestamp("just a message") is None

    @pytest.mark.parametrize("text,expected", [
        ("2026-08-07 09:00:01 [ERROR] boom", "ERROR"),
        ("2026-08-07 09:00:01 WARN  careful", "WARN"),
        ("2026-08-07 09:00:01 CRITICAL down", "FATAL"),
        ("2026-08-07 09:00:01 warning: careful", "WARN"),
        ("2026-08-07 09:00:01 hello world", "UNKNOWN"),
    ])
    def test_levels(self, text, expected):
        assert parse_level(text) == expected

    def test_level_word_inside_another_word_is_not_matched(self):
        assert parse_level("2026-08-07 09:00:01 ERRORS_TABLE updated") == "UNKNOWN"


class TestMultilineFolding:
    """스택 트레이스는 하나의 사건이다. 30줄로 세면 통계가 망가진다."""

    def test_java_stack_trace_folds_into_one_entry(self):
        lines = [
            "2026-08-07 09:00:01 [ERROR] Failed to load",
            "    at com.hk.Loader.load(Loader.java:64)",
            "    at com.hk.Main.main(Main.java:12)",
            "Caused by: java.io.IOException: disk gone",
            "2026-08-07 09:00:02 [INFO] next event",
        ]
        entries = iter_entries(lines)
        assert len(entries) == 2
        assert entries[0].line_count == 4
        assert entries[1].message == "next event"

    def test_python_traceback_folds(self):
        lines = [
            "2026-08-07 09:00:01 [ERROR] task failed",
            "Traceback (most recent call last):",
            '  File "x.py", line 3, in <module>',
            "ValueError: bad",
        ]
        entries = iter_entries(lines)
        assert len(entries) == 1

    def test_timestamped_line_is_never_a_continuation(self):
        assert not is_continuation("2026-08-07 09:00:01 [INFO] hi")

    def test_blank_lines_ignored(self):
        entries = iter_entries(["2026-08-07 09:00:01 INFO a", "", "   ", ])
        assert len(entries) == 1


class TestMasking:

    @pytest.mark.parametrize("text,expected", [
        ("user 12345 logged in", "user <NUM> logged in"),
        ("connect to 10.0.0.5:5432", "connect to <IP>"),
        ("took 250ms", "took <QTY>"),
        ("ttl=300s", "ttl=<QTY>"),
        ("id 550e8400-e29b-41d4-a716-446655440000", "id <UUID>"),
        ("mail to a.b@c.co.kr", "mail to <EMAIL>"),
        ("addr 0xDEADBEEF", "addr <HEX>"),
    ])
    def test_masks(self, text, expected):
        assert mask_variables(text) == expected

    def test_windows_path(self):
        assert "<PATH>" in mask_variables(r"open C:\logs\app\today.log failed")

    def test_words_are_preserved(self):
        # 마스킹이 너무 공격적이면 서로 다른 사건이 한 템플릿으로 뭉개진다.
        assert mask_variables("disk full") == "disk full"


class TestTemplateMining:

    def make(self, message, level="INFO", line_no=1):
        return LogEntry(line_no=line_no, level=level, message=message, raw=message)

    def test_varying_values_collapse_to_one_template(self):
        miner = TemplateMiner()
        for i in range(50):
            miner.add(self.make(f"Request {i} handled in {i * 3} ms", line_no=i + 1))
        assert len(miner.templates) == 1
        assert miner.templates[0].count == 50

    def test_different_messages_stay_separate(self):
        miner = TemplateMiner()
        miner.add(self.make("Disk full on volume A"))
        miner.add(self.make("User login succeeded"))
        assert len(miner.templates) == 2

    def test_template_tracks_most_severe_level(self):
        miner = TemplateMiner()
        miner.add(self.make("thing broke", level="INFO"))
        miner.add(self.make("thing broke", level="ERROR"))
        assert miner.templates[0].level == "ERROR"
        assert miner.templates[0].is_problem

    def test_line_range_tracked(self):
        miner = TemplateMiner()
        miner.add(self.make("value is 1", line_no=10))
        miner.add(self.make("value is 2", line_no=99))
        template = miner.templates[0]
        assert template.first_line == 10
        assert template.last_line == 99


class TestEndToEnd:

    @pytest.fixture
    def noisy_log(self, tmp_path):
        """노이즈 500줄 안에 신호 3줄을 묻어둔다."""
        lines = []
        for i in range(500):
            lines.append(
                f"2026-08-07 09:{i // 60 % 60:02d}:{i % 60:02d} [INFO] "
                f"Handled request {1000 + i} in {i % 90} ms"
            )
        lines.insert(200, "2026-08-07 09:03:20 [WARN] Disk quota exceeded on /var/data")
        lines.insert(400, "2026-08-07 09:06:40 [FATAL] Shutting down, WAL corrupt")
        lines.append("2026-08-07 09:09:00 [ERROR] Replica lag 500s exceeds threshold")
        return write(tmp_path, "\n".join(lines))

    def test_massive_compression(self, noisy_log):
        report = analyze_log(noisy_log)
        assert report.parsed_entries == 503
        # 500줄의 노이즈가 템플릿 1개로 접혀야 한다
        assert len(report.templates) <= 6
        assert report.compression_ratio > 50

    def test_buried_signals_are_surfaced(self, noisy_log):
        report = analyze_log(noisy_log)
        rare_texts = " ".join(
            h.detail for h in report.highlights if h.kind == "rare"
        )
        assert "Disk quota exceeded" in rare_texts
        assert "WAL corrupt" in rare_texts

    def test_dominant_noise_is_not_in_rare(self, noisy_log):
        report = analyze_log(noisy_log)
        for highlight in report.highlights:
            if highlight.kind == "rare":
                assert "Handled request" not in highlight.detail

    def test_level_counts(self, noisy_log):
        report = analyze_log(noisy_log)
        assert report.level_counts["INFO"] == 500
        assert report.level_counts["WARN"] == 1
        assert report.level_counts["FATAL"] == 1
        assert report.problem_count == 3

    def test_time_span_and_buckets(self, noisy_log):
        report = analyze_log(noisy_log)
        assert report.first_seen is not None
        assert report.last_seen > report.first_seen
        assert report.buckets

    def test_progress_reaches_100(self, noisy_log):
        seen = []
        analyze_log(noisy_log, progress=lambda p, m: seen.append(p))
        assert seen[-1] == 100

    def test_max_lines_truncates(self, noisy_log):
        report = analyze_log(noisy_log, max_lines=100)
        assert report.truncated
        assert report.total_lines == 100

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            analyze_log(str(tmp_path / "nope.log"))

    def test_log_without_timestamps_still_works(self, tmp_path):
        path = write(tmp_path, "\n".join(f"plain message {i}" for i in range(30)))
        report = analyze_log(path)
        assert report.parsed_entries == 30
        assert report.buckets == []          # 타임라인 없이도 죽지 않아야 한다

    def test_empty_file(self, tmp_path):
        report = analyze_log(write(tmp_path, ""))
        assert report.parsed_entries == 0
        assert report.highlights == []
