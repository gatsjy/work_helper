@echo off
chcp 65001 > nul
title Excel Set Analyzer
echo ========================================================
echo   📊 엑셀 집합 분석 자동화 툴 (Excel Set Analyzer)
echo   교집합 / 차집합(A-B, B-A) / 대칭차집합 / 합집합 분석
echo ========================================================
echo.
echo 프로그램 서버를 실행 중입니다...
python app.py
pause
