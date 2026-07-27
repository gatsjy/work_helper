# 📊 엑셀 클립보드 집합 분석 & 컬럼 Concat 자동화 툴 (Excel Helper)

> **엑셀에서 복사(Ctrl+C)한 클립보드 데이터를 붙여넣기(Ctrl+V)하여 두 데이터 간 집합 비교(교집합, 차집합, 대칭차집합, 합집합) 및 인터랙티브 컬럼 병합(Concat)을 수행하고, 결과를 클릭 한번으로 엑셀에 다시 복사할 수 있는 100% 클립보드 전용 업무 자동화 툴입니다.**

---

## 🌟 주요 기능 (Key Features)

### 1. 📊 엑셀 집합 비교 분석 (Set Analyzer)
- **100% 클립보드(`Ctrl+V`) 전용**: 별도의 엑셀 파일 업로드 없이, 데이터 A와 데이터 B 텍스트 창에 `Ctrl+V`로 붙여넣는 즉시 실시간 연산 수행.
- 🔵 **교집합 ($A \cap B$)**: 데이터 A와 B 모두에 존재하는 공통 데이터
- 🟡 **A전용 / 차집합 A ($A - B$)**: A에만 존재하고 B에는 없는 데이터
- 🔴 **B전용 / 차집합 B ($B - A$)**: B에만 존재하고 A에는 없는 데이터
- 🟣 **통합 대칭차집합 ($A \Delta B$)**: 불일치 데이터 전체 (출처 태그 자동 부여)
- 🟢 **합집합 ($A \cup B$)**: A 또는 B 전체 고유 데이터

### 2. 🔗 컬럼 Concat / 병합 툴 (Column Concat)
- **클립보드 표 데이터 파싱**: 엑셀의 복수 열(Table)을 붙여넣으면 헤더 및 열 목록을 감지하여 클릭 가능한 버튼(Chip)으로 생성.
- **인터랙티브 순서 결합**: 컬럼 버튼을 클릭한 순서대로 병합 순서(`1. [A] 이름 ➔ 2. [B] 직급 ➔ 3. [C] 부서`)가 지정되고 즉시 행별 결합 결과 계산.
- **다양한 구분자 지원**: 공백(` `), 하이픈(`-`), 언더바(`_`), 콤마(`,`), 슬래시(`/`), 없음(`""`), 사용자 지정 구분자 선택 및 Trim 옵션.

### 3. ⚡ 원클릭 클립보드 복사 (`Ctrl + V Ready`)
- **📋 데이터 값만 복사 (1줄에 1개씩)**: 엑셀의 단일 열(A열)에 바로 붙여넣기 최적화.
- **📊 엑셀 표 형태 복사 (탭 구분 TSV)**: 엑셀의 여러 셀에 한꺼번에 붙여넣기 최적화.

---

## 💻 실행 방법 (Getting Started)

### 방법 1: 윈도우 무설치 실행 파일 (`ExcelSetAnalyzer.exe`)
파이썬이나 별도 라이브러리 설치 없이 `dist/ExcelSetAnalyzer.exe`를 더블 클릭하여 윈도우 데스크톱 프로그램으로 실행합니다.

```path
dist/ExcelSetAnalyzer.exe
```

---

### 방법 2: PySide6 데스크톱 GUI 직접 실행
```bash
python gui.py
```

---

### 방법 3: 1-Click 배치 파일로 웹 브라우저 UI 실행
`run.bat` 파일 더블 클릭 시 웹 서버가 켜지면서 브라우저가 자동으로 열립니다.

```bash
python app.py
```

---

## 🛠️ 개발 및 빌드 안내 (Build Instructions)

- **언어**: Python 3.11+
- **GUI 라이브러리**: PySide6 (Qt for Python)
- **웹 백엔드/프론트엔드**: Python HTTP Server / HTML5, CSS3, JavaScript
- **패키징 툴**: PyInstaller

### .exe 재빌드 커맨드
```bash
pyinstaller --noconsole --onefile --name "ExcelSetAnalyzer" --clean gui.py
```

---

## 📝 라이선스 (License)
본 프로젝트는 자유롭게 수정 및 업무 자동화에 활용하실 수 있습니다.
