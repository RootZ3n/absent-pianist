@echo off
REM Absent Pianist - Start the web interface (Windows)
REM Double-click this file to start Absent Pianist.

cd /d "%~dp0"

echo.
echo   =============================
echo    Absent Pianist
echo    Hymn Accompaniment Generator
echo   =============================
echo.

REM Find Python. Prefer "python" on PATH; fall back to the "py" launcher.
REM Avoids the classic batch pitfall of nested %ERRORLEVEL% inside an IF block.
set "PYTHON="
where python >nul 2>nul && set "PYTHON=python"
if not defined PYTHON where py >nul 2>nul && set "PYTHON=py -3"

if not defined PYTHON (
  echo   ERROR: Python is not installed.
  echo   Download it from: https://www.python.org/downloads/
  echo   During install, tick "Add python.exe to PATH".
  echo.
  pause
  exit /b 1
)

REM Install Python dependencies if not already present.
%PYTHON% -c "import flask, mido, music21, requests" 1>nul 2>nul
if errorlevel 1 (
  echo   Installing Python dependencies (first time only)...
  %PYTHON% -m pip install --quiet -r requirements.txt
  if errorlevel 1 (
    echo   ERROR: Could not install Python dependencies. Check your internet connection.
    echo.
    pause
    exit /b 1
  )
)

if "%ABSENT_PIANIST_PORT%"=="" set "ABSENT_PIANIST_PORT=5111"

echo   Starting web server...
echo   Open your browser to: http://localhost:%ABSENT_PIANIST_PORT%
echo   Local-only by default. Press Ctrl+C to stop.
echo.

REM Open the browser after a short delay so Flask has time to bind.
start "" /b cmd /c "timeout /t 4 /nobreak >nul & start "" http://localhost:%ABSENT_PIANIST_PORT%"

%PYTHON% app.py

pause
