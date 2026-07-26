# 📊 엑셀 집합 분석 및 클립보드 복사 자동화 툴 (Excel Set Analyzer)

> **엑셀 파일의 두 컬럼 간 교집합, 차집합(A/B), 대칭차집합, 합집합을 한눈에 비교하고, 결과를 클릭 한번으로 클립보드에 복사(Ctrl+V)할 수 있는 윈도우 데스크톱 및 웹 업무 자동화 프로그램입니다.**

---

## 🌟 주요 기능 (Key Features)

### 1. 5가지 집합 연산 원클릭 분석
- 🔵 **교집합 ($A \cap B$)**: 컬럼 A와 B 모두에 존재하는 공통 데이터
- 🟡 **A전용 / 차집합 A ($A - B$)**: 컬럼 A에만 존재하고 B에는 없음
- 🔴 **B전용 / 차집합 B ($B - A$)**: 컬럼 B에만 존재하고 A에는 없음
- 🟣 **통합 대칭차집합 ($A \Delta B$)**: 불일치 데이터 전체 (각 행별로 `[A전용]`, `[B전용]` 출처 태그 자동 부여)
- 🟢 **합집합 ($A \cup B$)**: A 또는 B에 존재하는 전체 고유 데이터

### 2. ⚡ 클립보드 원클릭 복사 (`Ctrl + V`)
- **📋 데이터 값만 복사 (1줄에 1개씩)**: 엑셀의 단일 열(A열)에 바로 붙여넣을 때 최적화된 형식
- **📊 엑셀 표 형태 복사 (탭 구분 TSV)**: 엑셀의 여러 셀에 번호, 데이터값, 구분태그, A존재 여부, B존재 여부를 한꺼번에 붙여넣을 때 최적화된 표 형식

### 3. 스마트 전처리 옵션
- **Trim Space**: 데이터 앞뒤 불필요한 공백 자동 제거
- **Case Sensitivity**: 대소문자 엄격 구분 여부 선택 (기본: 무시)
- **Drop Empty**: 빈 값 및 N/A 셀 자동 제외

---

## 💻 실행 방법 (Getting Started)

### 방법 1: 윈도우 실행 파일 (.exe)로 실행 (추천 / 무설치)
파이썬이나 별도 라이브러리 설치 없이 실행할 수 있습니다.

```path
dist/ExcelSetAnalyzer.exe
```
[ExcelSetAnalyzer.exe 실행하기](file:///c:/Users/gatsjy/Documents/work_helper/dist/ExcelSetAnalyzer.exe) 더블 클릭

---

### 방법 2: 윈도우 1-Click 배치 파일로 웹 UI 실행
[run.bat](file:///c:/Users/gatsjy/Documents/work_helper/run.bat) 더블 클릭 시 웹 서버가 켜지면서 브라우저가 자동으로 열립니다.

---

### 방법 3: 파이썬 소스 코드로 직접 실행

- **PySide6 데스크톱 GUI 모드**:
  ```bash
  python gui.py
  ```

- **웹 브라우저 UI 모드**:
  ```bash
  python app.py
  ```

---

## 📁 프로젝트 파일 구조 (Directory Structure)

```
c:/Users/gatsjy/Documents/work_helper/
├── dist/
│   └── ExcelSetAnalyzer.exe  # 윈도우 독립 실행형 패키지 (.exe)
├── gui.py                     # PySide6 데스크톱 GUI 엔트리포인트
├── app.py                     # 웹 서버 백엔드 & 자동 브라우저 실행기
├── excel_processor.py         # pandas/openpyxl 기반 집합 연산 코어 엔진
├── web/
│   ├── index.html             # 웹 UI 메인 레이아웃
│   ├── style.css              # 다크 글래스모피즘 CSS 스타일
│   └── app.js                 # 클립보드 복사 및 웹 프론트엔드 로직
├── sample_data.xlsx           # 바로 테스트 가능한 샘플 엑셀 파일
├── test_processor.py          # 코어 엔진 단위 테스트 스크립트
├── run.bat                    # 윈도우 1-클릭 실행 파일
└── README.md                  # 프로젝트 설명 문서
```

---

## 🛠️ 개발 환경 및 빌드 (Build Instructions)

- **언어**: Python 3.12
- **GUI 라이브러리**: PySide6 (Qt for Python)
- **데이터 처리**: pandas, openpyxl
- **패키징 툴**: PyInstaller

### .exe 재빌드 커맨드
```bash
pyinstaller --noconsole --onefile --name "ExcelSetAnalyzer" gui.py
```

---

## 📝 라이선스 (License)
본 프로젝트는 자유롭게 수정 및 업무 자동화에 활용하실 수 있습니다.
