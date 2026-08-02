import json
import os
import uuid
from datetime import datetime, date


class TodoManager:
    """스마트 Todo List & 자동 일일 이월 (Daily Rollover) 데이터 관리자"""
    def __init__(self, filepath=None):
        if filepath is None:
            home_dir = os.path.expanduser("~")
            self.filepath = os.path.join(home_dir, ".excel_set_analyzer_todos.json")
        else:
            self.filepath = filepath

        self.tasks = []
        self.last_check_date = date.today().isoformat()
        self.load_data()
        self.check_and_rollover_tasks()

    def load_data(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.tasks = data.get("tasks", [])
                    self.last_check_date = data.get("last_check_date", date.today().isoformat())
            except Exception as e:
                print(f"Error loading todo data: {e}")
                self.tasks = []
                self.last_check_date = date.today().isoformat()
        else:
            self.tasks = []
            self.last_check_date = date.today().isoformat()
            self.save_data()

    def save_data(self):
        data = {
            "last_check_date": self.last_check_date,
            "tasks": self.tasks
        }
        try:
            with open(self.filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error saving todo data: {e}")

    def check_and_rollover_tasks(self, today_str=None):
        """
        날짜가 변경되었거나, due_date가 오늘 이전인 미완료 항목들을 오늘로 이월합니다.
        """
        if today_str is None:
            today_str = date.today().isoformat()

        rolled_over_tasks = []
        for task in self.tasks:
            if not task.get("completed", False):
                due_date = task.get("due_date", today_str)
                if due_date < today_str:
                    # 마감일이 지나도록 미완료된 항목 -> 오늘로 자동 이월
                    task["due_date"] = today_str
                    task["rollover_count"] = task.get("rollover_count", 0) + 1
                    rolled_over_tasks.append(task)

        self.last_check_date = today_str
        if rolled_over_tasks:
            self.save_data()
        return rolled_over_tasks

    def add_task(self, title, category="업무", priority="보통", due_date=None, notes=""):
        if not title or not title.strip():
            return None

        today_str = date.today().isoformat()
        if due_date is None:
            due_date = today_str

        task = {
            "id": str(uuid.uuid4()),
            "title": title.strip(),
            "category": category if category else "업무",
            "priority": priority if priority else "보통",  # 높음, 보통, 낮음
            "created_date": today_str,
            "original_due_date": due_date,
            "due_date": due_date,
            "completed": False,
            "completed_date": None,
            "rollover_count": 0,
            "notes": notes.strip() if notes else ""
        }
        self.tasks.append(task)
        self.save_data()
        return task

    def toggle_complete(self, task_id):
        today_str = date.today().isoformat()
        for task in self.tasks:
            if task["id"] == task_id:
                task["completed"] = not task["completed"]
                task["completed_date"] = today_str if task["completed"] else None
                self.save_data()
                return task
        return None

    def delete_task(self, task_id):
        self.tasks = [t for t in self.tasks if t["id"] != task_id]
        self.save_data()

    def update_task(self, task_id, title=None, category=None, priority=None, due_date=None, notes=None):
        for task in self.tasks:
            if task["id"] == task_id:
                if title is not None:
                    task["title"] = title.strip()
                if category is not None:
                    task["category"] = category
                if priority is not None:
                    task["priority"] = priority
                if due_date is not None:
                    task["due_date"] = due_date
                if notes is not None:
                    task["notes"] = notes.strip()
                self.save_data()
                return task
        return None

    def get_filtered_tasks(self, filter_type="today", category_filter="전체", search_query=""):
        today_str = date.today().isoformat()
        results = []

        for task in self.tasks:
            # 검색어 필터
            if search_query and search_query.lower() not in task["title"].lower() and search_query.lower() not in task.get("notes", "").lower():
                continue

            # 카테고리 필터
            if category_filter != "전체" and task["category"] != category_filter:
                continue

            # 날짜 및 상태 필터
            if filter_type == "today":
                if task["due_date"] == today_str:
                    results.append(task)
            elif filter_type == "rollover":
                if task.get("rollover_count", 0) > 0 and not task["completed"]:
                    results.append(task)
            elif filter_type == "completed":
                if task["completed"]:
                    results.append(task)
            elif filter_type == "pending":
                if not task["completed"]:
                    results.append(task)
            elif filter_type == "all":
                results.append(task)

        # 정렬: 미완료 우선 -> 우선순위(높음>보통>낮음) -> 작성일/마감일
        priority_map = {"높음": 0, "보통": 1, "낮음": 2}
        results.sort(key=lambda t: (
            1 if t["completed"] else 0,
            priority_map.get(t.get("priority", "보통"), 1),
            t.get("due_date", "")
        ))
        return results

    def get_stats(self, today_str=None):
        if today_str is None:
            today_str = date.today().isoformat()

        today_tasks = [t for t in self.tasks if t["due_date"] == today_str]
        total_today = len(today_tasks)
        completed_today = len([t for t in today_tasks if t["completed"]])
        progress_pct = int((completed_today / total_today * 100)) if total_today > 0 else 0
        total_rolled_over = len([t for t in self.tasks if t.get("rollover_count", 0) > 0 and not t["completed"]])

        return {
            "total_today": total_today,
            "completed_today": completed_today,
            "progress_pct": progress_pct,
            "total_rolled_over": total_rolled_over,
            "total_pending": len([t for t in self.tasks if not t["completed"]]),
            "total_all": len(self.tasks)
        }

    def simulate_next_day(self):
        """테스트 및 검증용: 미완료 항목의 마감일을 어제로 변경하여 이월 동작 시뮬레이션"""
        from datetime import timedelta
        yesterday_str = (date.today() - timedelta(days=1)).isoformat()
        count = 0
        for task in self.tasks:
            if not task["completed"]:
                task["due_date"] = yesterday_str
                count += 1

        if count == 0:
            return 0

        self.save_data()
        rolled = self.check_and_rollover_tasks()
        return len(rolled)
