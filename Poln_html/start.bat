@echo off
echo Stopping any Python servers...
taskkill /F /IM python.exe 2>nul
timeout /t 2 /nobreak >nul
echo Starting Flask server...
python server.py
pause