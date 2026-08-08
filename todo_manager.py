import json
import os
import shutil
import tempfile
import uuid
from datetime import date, datetime, timedelta


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
        self.load_error = None
        self.load_data()
        self.check_and_rollover_tasks()

    @property
    def backup_path(self):
        return self.filepath + ".bak"

    def load_data(self):
        """할 일을 읽어온다. 파일이 깨졌으면 백업 → 그래도 안 되면 손상본을 보존한다.

        예전에는 JSON 이 깨지면 조용히 빈 목록으로 시작했고, 다음 저장이 그
        파일을 덮어써서 사용자의 할 일이 전부 사라졌다. 무엇이 잘못됐는지
        알 방법조차 없었다.
        """
        self.load_error = None

        if not os.path.exists(self.filepath):
            self.tasks = []
            self.last_check_date = date.today().isoformat()
            self.save_data()
            return

        data = self._read_json(self.filepath)

        if data is None and os.path.exists(self.backup_path):
            data = self._read_json(self.backup_path)
            if data is not None:
                self.load_error = (
                    "할 일 파일이 손상되어 직전 백업에서 복구했습니다."
                )

        if data is None:
            # 어느 쪽도 못 읽었다. 손상된 파일은 절대 덮어쓰지 않고 옆으로 치워둔다.
            quarantine = (
                f"{self.filepath}.corrupt-"
                f"{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            )
            try:
                shutil.copy2(self.filepath, quarantine)
                self.load_error = (
                    "할 일 파일을 읽을 수 없어 빈 목록으로 시작합니다.\n"
                    f"손상된 원본은 여기 보관했습니다:\n{quarantine}"
                )
            except Exception as exc:
                self.load_error = f"할 일 파일을 읽을 수도, 백업할 수도 없습니다: {exc}"

            self.tasks = []
            self.last_check_date = date.today().isoformat()
            return

        tasks = data.get("tasks", [])
        self.tasks = tasks if isinstance(tasks, list) else []
        self.last_check_date = data.get("last_check_date", date.today().isoformat())

    @staticmethod
    def _read_json(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    def save_data(self):
        """원자적으로 저장한다: 임시 파일에 쓰고 → fsync → 제자리 교체.

        예전에는 실제 파일을 직접 열어서 썼다. 그 사이에 프로세스가 죽거나
        디스크가 차면 반쯤 쓰인 JSON 이 남고, 다음 실행에서 전부 날아갔다.
        os.replace() 는 같은 볼륨 안에서 원자적이라, 파일은 항상 '이전 내용'
        아니면 '새 내용' 둘 중 하나다.
        """
        data = {
            "last_check_date": self.last_check_date,
            "tasks": self.tasks,
        }

        directory = os.path.dirname(os.path.abspath(self.filepath))
        try:
            os.makedirs(directory, exist_ok=True)

            # 직전 정상본을 백업으로 남긴다.
            if os.path.exists(self.filepath):
                try:
                    shutil.copy2(self.filepath, self.backup_path)
                except Exception:
                    pass

            fd, tmp_path = tempfile.mkstemp(
                dir=directory, prefix=".todos-", suffix=".tmp"
            )
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp_path, self.filepath)
            except Exception:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                raise

            return True
        except Exception as e:
            print(f"Error saving todo data: {e}")
            return False

    def check_and_rollover_tasks(self, today_str=None):
        """마감일이 지난 미완료 항목을 오늘로 이월한다.

        rollover_count 는 '실제로 밀린 날 수'다. 예전에는 앱을 켤 때마다 1씩
        올랐기 때문에, 5일 밀린 할 일도 앱을 한 번만 켰으면 "1일 이월됨"으로
        보였고, 하루에 앱을 세 번 켜면 "3일 이월됨"이 됐다.
        """
        if today_str is None:
            today_str = date.today().isoformat()

        rolled_over_tasks = []
        for task in self.tasks:
            if task.get("completed", False):
                continue

            due_date = task.get("due_date", today_str)
            if due_date >= today_str:
                continue

            days_late = self._days_between(due_date, today_str)
            task["due_date"] = today_str
            task["rollover_count"] = task.get("rollover_count", 0) + max(days_late, 1)
            rolled_over_tasks.append(task)

        self.last_check_date = today_str
        if rolled_over_tasks:
            self.save_data()
        return rolled_over_tasks

    @staticmethod
    def _days_between(from_str, to_str):
        """두 ISO 날짜 사이의 일수. 형식이 이상하면 1일로 본다."""
        try:
            start = date.fromisoformat(str(from_str)[:10])
            end = date.fromisoformat(str(to_str)[:10])
            return max((end - start).days, 1)
        except Exception:
            return 1

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
            if task.get("id") == task_id:
                task["completed"] = not task.get("completed", False)
                task["completed_date"] = today_str if task["completed"] else None
                self.save_data()
                return task
        return None

    def delete_task(self, task_id):
        self.tasks = [t for t in self.tasks if t.get("id") != task_id]
        self.save_data()

    def update_task(self, task_id, title=None, category=None, priority=None, due_date=None, notes=None):
        for task in self.tasks:
            if task.get("id") == task_id:
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

    def get_filtered_tasks(self, filter_type="today", category_filter="전체 카테고리", search_query=""):
        today_str = date.today().isoformat()
        results = []

        for task in self.tasks:
            # 검색어 필터
            if search_query:
                sq = search_query.lower()
                if sq not in task.get("title", "").lower() and sq not in task.get("notes", "").lower():
                    continue

            # 카테고리 필터 ("전체", "전체 카테고리"는 전체 항목 통과)
            if category_filter and category_filter not in ("전체", "전체 카테고리") and task.get("category") != category_filter:
                continue

            # 날짜 및 상태 필터
            if filter_type == "today":
                due = task.get("due_date", today_str)
                if due == today_str or (not task.get("completed") and due <= today_str):
                    results.append(task)
            elif filter_type == "rollover":
                if task.get("rollover_count", 0) > 0 and not task.get("completed"):
                    results.append(task)
            elif filter_type == "completed":
                if task.get("completed"):
                    results.append(task)
            elif filter_type == "pending":
                if not task.get("completed"):
                    results.append(task)
            elif filter_type == "all":
                results.append(task)

        # 정렬: 미완료 우선 -> 우선순위(높음>보통>낮음) -> 작성일/마감일
        priority_map = {"높음": 0, "보통": 1, "낮음": 2}
        results.sort(key=lambda t: (
            1 if t.get("completed", False) else 0,
            priority_map.get(t.get("priority", "보통"), 1),
            t.get("due_date", "")
        ))
        return results

    def get_stats(self, today_str=None):
        if today_str is None:
            today_str = date.today().isoformat()

        # 다른 곳은 전부 .get() 을 쓰는데 여기만 직접 접근이라, 예전 스키마의
        # 항목이 하나라도 섞이면 통계 전체가 KeyError 로 터졌다.
        today_tasks = [t for t in self.tasks if t.get("due_date") == today_str]
        total_today = len(today_tasks)
        completed_today = len([t for t in today_tasks if t.get("completed", False)])
        progress_pct = int(completed_today / total_today * 100) if total_today else 0
        total_rolled_over = len([
            t for t in self.tasks
            if t.get("rollover_count", 0) > 0 and not t.get("completed", False)
        ])

        return {
            "total_today": total_today,
            "completed_today": completed_today,
            "progress_pct": progress_pct,
            "total_rolled_over": total_rolled_over,
            "total_pending": len([
                t for t in self.tasks if not t.get("completed", False)
            ]),
            "total_all": len(self.tasks)
        }

    def simulate_next_day(self):
        """검증용: 하루가 지난 것처럼 이월 동작을 돌려본다.

        예전 구현은 '모든' 미완료 항목의 마감일을 어제로 덮어썼다. 다음 주가
        마감인 할 일까지 어제로 끌어내린 뒤 오늘로 이월시켜, 사용자가 직접
        잡아둔 일정을 시뮬레이션 버튼 한 번으로 지워버렸다.

        지금은 미래 마감일은 건드리지 않고, 오늘 마감인 항목만 어제로 밀어
        '내일이 됐을 때' 벌어질 일을 그대로 재현한다.
        """
        today_str = date.today().isoformat()
        yesterday_str = (date.today() - timedelta(days=1)).isoformat()

        moved = 0
        for task in self.tasks:
            if task.get("completed", False):
                continue
            # 오늘(또는 그 이전) 마감인 것만 대상. 미래 일정은 보존한다.
            if task.get("due_date", today_str) <= today_str:
                task["due_date"] = yesterday_str
                moved += 1

        if moved == 0:
            return 0

        self.save_data()
        return len(self.check_and_rollover_tasks())
