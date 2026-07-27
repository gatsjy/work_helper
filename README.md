# 💻 엑셀 집합 분석 & 컬럼 Concat 윈도우 데스크톱 프로그램 (ExcelSetAnalyzer)

> **⚠️ 본 프로젝트는 PySide6(Qt for Python) 기반의 100% 윈도우 데스크톱 GUI 프로그램 (.exe)입니다.**
> 엑셀에서 복사(`Ctrl+C`)한 클립보드 데이터를 프로그램에 붙여넣어(`Ctrl+V`) 집합 비교 및 컬럼 병합(Concat)을 즉시 수행하고, 결과를 엑셀로 원클릭 복사할 수 있는 업무 자동화 프로그램입니다.

---

## 🌟 주요 기능 (Key Features)

### 1. 📊 엑셀 집합 비교 분석 (Set Analyzer 탭)
- **클립보드(`Ctrl+V`) 전용 연산**: 데이터 A와 데이터 B 텍스트 창에 `Ctrl+V`로 붙여넣는 즉시 실시간 연산 수행.
- 🔵 **교집합 ($A \cap B$)**: 데이터 A와 B 모두에 존재하는 공통 데이터
- 🟡 **A전용 / 차집합 A ($A - B$)**: A에만 존재하고 B에는 없는 데이터
- 🔴 **B전용 / 차집합 B ($B - A$)**: B에만 존재하고 A에는 없는 데이터
- 🟣 **통합 대칭차집합 ($A \Delta B$)**: 불일치 데이터 전체 (출처 태그 자동 부여)
- 🟢 **합집합 ($A \cup B$)**: A 또는 B 전체 고유 데이터

### 2. 🔗 컬럼 Concat / 병합 툴 (Column Concat 탭)
- **클립보드 표 데이터 자동 파싱**: 엑셀의 복수 열(Table)을 붙여넣으면 헤더 및 열 목록을 감지하여 클릭 가능한 버튼(Chip)으로 생성.
- **인터랙티브 순서 결합**: 컬럼 버튼을 클릭한 순서대로 병합 순서(`1. [A] 이름 ➔ 2. [B] 직급 ➔ 3. [C] 부서`)가 지정되고 즉시 행별 결합 결과 계산.
- **다양한 구분자 지원**: 공백(` `), 하이픈(`-`), 언더바(`_`), 콤마(`,`), 슬래시(`/`), 없음(`""`), 사용자 지정 구분자 선택 및 Trim 옵션.

### 3. ⚡ 원클릭 클립보드 복사 (`Ctrl + V Ready`)
- **📋 데이터 값만 복사 (1줄에 1개씩)**: 엑셀의 단일 열(A열)에 바로 붙여넣기 최적화.
- **📊 엑셀 표 형태 복사 (탭 구분 TSV)**: 엑셀의 여러 셀에 한꺼번에 붙여넣기 최적화.

---

## 💻 실행 방법 (Getting Started)

### 1. 윈도우 무설치 실행 파일 (`ExcelSetAnalyzer.exe`)
파이썬 설치 필요 없이 `dist/ExcelSetAnalyzer.exe`를 더블 클릭하여 실행합니다.

```path
dist/ExcelSetAnalyzer.exe
```

### 2. 파이썬 소스로 실행 (개발자용)
```bash
python gui.py
```

---

## 🛠️ 개발 환경 및 빌드 (Build Instructions)

- **개발 언어**: Python 3.11+
- **GUI 프레임워크**: PySide6 (Qt for Python)
- **데이터 엔진**: pandas, openpyxl
- **패키징 툴**: PyInstaller

### .exe 재빌드 커맨드
```bash
pyinstaller --noconsole --onefile --name "ExcelSetAnalyzer" gui.py
```

---

## 📁 프로젝트 파일 구조

```
c:/Users/KNUH/work_helper/
├── dist/
│   └── ExcelSetAnalyzer.exe  # 윈도우 독립 실행형 프로그램 (.exe)
├── gui.py                     # PySide6 데스크톱 GUI 메인 애플리케이션
├── excel_processor.py         # pandas/openpyxl 기반 집합 연산 코어 엔진
├── AGENTS.md                  # 개발 에이전트 지침 및 아키텍처 규칙
└── README.md                  # 프로젝트 설명 문서
```
