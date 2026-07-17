@echo off
setlocal
cd /d "%~dp0"

REM ============================================================
REM   Video face-sort - one-click runner
REM   1. Put reference photos in  search_pics\
REM   2. Double-click this file and answer the questions.
REM   (Edit extensions.txt / negation.txt / target.txt to tune.)
REM ============================================================

set "SCRIPT=sort_videos_by_face.py"
set "VENV=.venv"

REM --- make sure the reference folder exists ---
if not exist "search_pics\" mkdir "search_pics"

REM --- find Python ---
set "PY="
where py     >nul 2>&1 && set "PY=py"
if not defined PY  where python >nul 2>&1 && set "PY=python"
if not defined PY (
  echo.
  echo Python is not installed. Get it from https://www.python.org/downloads/
  echo During install, TICK "Add Python to PATH".
  echo.
  pause & exit /b 1
)

REM --- create the virtual environment once ---
if not exist "%VENV%\Scripts\python.exe" (
  echo Creating environment ^(first run only^)...
  %PY% -m venv "%VENV%"
)
set "VPY=%VENV%\Scripts\python.exe"

REM --- install dependencies once ---
if not exist "%VENV%\.ready" (
  echo Installing dependencies ^(first run only, a few minutes^)...
  "%VPY%" -m pip install --upgrade pip
  "%VPY%" -m pip install insightface onnxruntime opencv-python numpy
  if errorlevel 1 (
    echo.
    echo Dependency install failed. Check your internet connection and re-run.
    pause & exit /b 1
  )
  echo ready> "%VENV%\.ready"
)

REM --- check reference photos exist ---
dir /b /a-d "search_pics\*" >nul 2>&1
if errorlevel 1 (
  echo.
  echo No reference photos found. Add photos to the "search_pics" folder,
  echo then re-run.
  echo.
  start "" "search_pics"
  pause & exit /b 1
)

REM --- run the interactive wizard ---
"%VPY%" "%SCRIPT%" --wizard --known "search_pics" --report "results.csv" --txt "results.txt"

echo.
echo Finished. See results.txt in this folder.
if exist "results.txt" start "" "results.txt"
pause
