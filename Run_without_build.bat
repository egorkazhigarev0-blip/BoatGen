@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PY="
set "PYW="
where py >nul 2>nul && (set "PY=py -3" & set "PYW=pyw -3")
if not defined PY (
  where python >nul 2>nul && (set "PY=python" & set "PYW=pythonw")
)
if not defined PY (
  echo Python не найден. Установите Python 3.10+ с https://www.python.org/downloads/
  echo При установке отметьте "Add python.exe to PATH".
  pause
  exit /b 1
)
%PY% -c "import webview" >nul 2>nul || %PY% -m pip install --disable-pip-version-check -q pywebview
start "" %PYW% "%~dp0source\app.py"
