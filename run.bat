@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

REM ============================================================
REM   Video face-sort - one-click runner
REM   Put reference photos in  search_pics\
REM   Put videos to scan in    videos\
REM   Then just double-click this file.
REM ============================================================

set "SCRIPT=sort_videos_by_face.py"
set "VENV=.venv"

REM ---------------- CONFIG ----------------
REM Video extensions to scan (comma-separated, no dots). Add/remove as needed.
set "EXTS=mp4,mov,m2ts,mts,avi,mkv,mxf,wmv,flv,webm,m4v,mpg,mpeg,3gp,ts"

REM Where to look for videos (in priority order):
REM
REM  (1) DATE RANGE via Everything - fastest, searches all drives by date.
REM      Fill BOTH dates (YYYY-MM-DD) to use this. Needs Everything + es.exe.
REM      Leave blank to skip.
set "DATE_FROM="
set "DATE_TO="
set "DATE_FIELD=modified"      REM modified = recording date, created = copy date
set "ES_PATH="                 REM full path to es.exe if it's not on PATH
REM
REM  (2) If no dates: 1 = search ALL drives, 0 = only the "videos" folder.
set "SEARCH_ALL=0"

REM Paths to SKIP (semicolon-separated). Files/folders under these are ignored.
REM e.g.  set "EXCLUDE=D:\Backups;E:\Proxies"
set "EXCLUDE="
REM ----------------------------------------

REM --- make sure the folders exist ---
if not exist "search_pics\" mkdir "search_pics"
if not exist "videos\"      mkdir "videos"

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
  echo name each file after the person ^(e.g. Bride.jpg, Groom.jpg^), then re-run.
  echo.
  start "" "search_pics"
  pause & exit /b 1
)

REM --- pick input source ---
if not "%DATE_FROM%"=="" if not "%DATE_TO%"=="" (
  set "INPUT=--from %DATE_FROM% --to %DATE_TO% --date-field %DATE_FIELD%"
  if not "%ES_PATH%"=="" set "INPUT=!INPUT! --es-path "%ES_PATH%""
  echo Searching all drives by date %DATE_FROM% .. %DATE_TO% via Everything...
  goto :haveinput
)
if "%SEARCH_ALL%"=="1" (
  set "INPUT=--all"
  echo Scanning ALL drives...
) else (
  set "INPUT=--videos videos"
  echo Scanning the "videos" folder...
)
:haveinput

REM --- optional exclude list ---
set "EXARG="
if not "%EXCLUDE%"=="" set "EXARG=--exclude "%EXCLUDE%""

REM --- run ---
echo.
"%VPY%" "%SCRIPT%" --known "search_pics" %INPUT% %EXARG% --copy --report "results.csv" --txt "results.txt" --ext "%EXTS%"

echo.
echo Finished. See results.txt in this folder.
start "" "results.txt"
pause
