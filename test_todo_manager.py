# -*- coding: utf-8 -*-
"""
TodoManager 테스트 — 특히 데이터 유실 경로.
"""
import json
import os
from datetime import date, timedelta

import pytest

from todo_manager import TodoManager


@pytest.fixture
def manager(tmp_path):
    return TodoManager(filepath=str(tmp_path / "todos.json"))


def days_ago(n):
    return (date.today() - timedelta(days=n)).isoformat()


def days_ahead(n):
    return (date.today() + timedelta(days=n)).isoformat()


class TestBasics:

    def test_add_and_list(self, manager):
        task = manager.add_task("보고서 작성", category="업무", priority="높음")
        assert task["title"] == "보고서 작성"
        assert task["completed"] is False
        assert len(manager.get_filtered_tasks("all")) == 1

    def test_blank_title_rejected(self, manager):
        assert manager.add_task("   ") is None
        assert manager.get_filtered_tasks("all") == []

    def test_toggle_and_delete(self, manager):
        task = manager.add_task("할 일")
        manager.toggle_complete(task["id"])
        assert manager.get_filtered_tasks("completed")[0]["id"] == task["id"]

        manager.delete_task(task["id"])
        assert manager.get_filtered_tasks("all") == []

    def test_persisted_across_instances(self, manager):
        manager.add_task("유지되어야 함")
        reloaded = TodoManager(filepath=manager.filepath)
        assert len(reloaded.get_filtered_tasks("all")) == 1


class TestPersistenceSafety:
    """예전에는 저장 파일이 깨지면 조용히 전부 사라졌다."""

    def test_corrupt_file_recovers_from_backup(self, manager):
        manager.add_task("소중한 할 일")
        manager.add_task("두번째")           # 첫 저장본이 .bak 으로 남는다
        assert os.path.exists(manager.backup_path)

        with open(manager.filepath, 'w', encoding='utf-8') as f:
            f.write("{ this is not json")

        recovered = TodoManager(filepath=manager.filepath)
        assert recovered.load_error is not None
        assert len(recovered.get_filtered_tasks("all")) >= 1

    def test_unreadable_file_is_quarantined_not_overwritten(self, tmp_path):
        path = tmp_path / "todos.json"
        path.write_text("{{{ broken", encoding='utf-8')

        manager = TodoManager(filepath=str(path))
        assert manager.load_error is not None

        quarantined = list(tmp_path.glob("todos.json.corrupt-*"))
        assert quarantined, "손상된 파일이 보존되지 않았다"
        assert "broken" in quarantined[0].read_text(encoding='utf-8')

    def test_save_is_atomic_no_temp_files_left(self, manager):
        manager.add_task("a")
        manager.add_task("b")
        leftovers = [
            f for f in os.listdir(os.path.dirname(manager.filepath))
            if f.endswith(".tmp")
        ]
        assert leftovers == []

    def test_saved_file_is_valid_json(self, manager):
        manager.add_task("확인")
        with open(manager.filepath, encoding='utf-8') as f:
            data = json.load(f)
        assert data["tasks"][0]["title"] == "확인"


class TestRollover:

    def test_overdue_task_rolls_to_today(self, manager):
        task = manager.add_task("밀린 일")
        task["due_date"] = days_ago(1)
        manager.save_data()

        manager.check_and_rollover_tasks()
        assert task["due_date"] == date.today().isoformat()
        assert task["rollover_count"] == 1

    def test_rollover_count_reflects_actual_days(self, manager):
        # 회귀: 예전에는 며칠이 밀렸든 실행할 때마다 1씩만 올랐다.
        task = manager.add_task("5일 밀린 일")
        task["due_date"] = days_ago(5)
        manager.save_data()

        manager.check_and_rollover_tasks()
        assert task["rollover_count"] == 5

    def test_rollover_is_idempotent_within_a_day(self, manager):
        # 회귀: 하루에 앱을 세 번 켜면 "3일 이월됨"이 됐다.
        task = manager.add_task("밀린 일")
        task["due_date"] = days_ago(2)
        manager.save_data()

        manager.check_and_rollover_tasks()
        manager.check_and_rollover_tasks()
        manager.check_and_rollover_tasks()
        assert task["rollover_count"] == 2

    def test_completed_tasks_do_not_roll(self, manager):
        task = manager.add_task("끝난 일")
        manager.toggle_complete(task["id"])
        task["due_date"] = days_ago(3)

        manager.check_and_rollover_tasks()
        assert task["due_date"] == days_ago(3)
        assert task.get("rollover_count", 0) == 0

    def test_future_tasks_are_untouched(self, manager):
        task = manager.add_task("다음주 일", due_date=days_ahead(7))
        manager.check_and_rollover_tasks()
        assert task["due_date"] == days_ahead(7)


class TestSimulateNextDay:

    def test_future_due_dates_are_preserved(self, manager):
        # 회귀: 예전 구현은 미래 마감일까지 어제로 끌어내려 일정을 파괴했다.
        future = manager.add_task("다음주 발표", due_date=days_ahead(7))
        today = manager.add_task("오늘 할 일")

        manager.simulate_next_day()

        assert future["due_date"] == days_ahead(7), "미래 일정이 파괴됐다"
        assert today["due_date"] == date.today().isoformat()
        assert today["rollover_count"] == 1

    def test_returns_zero_when_nothing_pending(self, manager):
        assert manager.simulate_next_day() == 0


class TestFiltersAndStats:

    def test_category_filter(self, manager):
        manager.add_task("업무 일", category="업무")
        manager.add_task("개인 일", category="개인")
        assert len(manager.get_filtered_tasks("all", category_filter="업무")) == 1
        assert len(manager.get_filtered_tasks("all", category_filter="전체")) == 2
        assert len(manager.get_filtered_tasks("all", category_filter="전체 카테고리")) == 2

    def test_search_matches_title_and_notes(self, manager):
        manager.add_task("회의 준비", notes="회의실 예약")
        manager.add_task("다른 일")
        assert len(manager.get_filtered_tasks("all", search_query="회의")) == 1
        assert len(manager.get_filtered_tasks("all", search_query="예약")) == 1

    def test_priority_sort_order(self, manager):
        manager.add_task("낮음 일", priority="낮음")
        manager.add_task("높음 일", priority="높음")
        manager.add_task("보통 일", priority="보통")
        titles = [t["title"] for t in manager.get_filtered_tasks("all")]
        assert titles == ["높음 일", "보통 일", "낮음 일"]

    def test_progress_stats(self, manager):
        a = manager.add_task("a")
        manager.add_task("b")
        manager.toggle_complete(a["id"])

        stats = manager.get_stats()
        assert stats["total_today"] == 2
        assert stats["completed_today"] == 1
        assert stats["progress_pct"] == 50
        assert stats["total_pending"] == 1

    def test_stats_survive_legacy_records_without_keys(self, manager):
        # 회귀: get_stats 만 직접 키 접근이라 예전 스키마에서 KeyError 로 터졌다.
        manager.tasks.append({"id": "legacy", "title": "옛날 항목"})
        stats = manager.get_stats()
        assert stats["total_all"] == 1
