@echo off
title DRES Submission Portal - AI Challenge 2026
echo ========================================================
echo   DRES Submission Portal - AI Challenge 2026
echo ========================================================
echo.
echo Dang khoi dong cong submit tai http://localhost:8080/dres_submitter.html ...
echo (De dung server, hay dong cua so nay)
echo.
start http://localhost:8080/dres_submitter.html
python -m http.server 8080
