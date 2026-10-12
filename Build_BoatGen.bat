@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title BoatGen - сборка BoatGen.exe
echo.
echo   ==============================================
echo     BoatGen: сборка программы BoatGen.exe
echo   ==============================================
echo.

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
  where python >nul 2>nul && set "PY=python"
)
if not defined PY (
  echo   Python не найден.
  echo   Установите Python 3.10 или новее с сайта https://www.python.org/downloads/
  echo   При установке отметьте галочку "Add python.exe to PATH", потом запустите этот файл снова.
  echo.
  pause
  exit /b 1
)

echo   [1/3] Установка pywebview и PyInstaller...
%PY% -m pip install --disable-pip-version-check -q -r "%~dp0source\requirements.txt" pyinstaller
if errorlevel 1 goto fail

echo   [2/3] Сборка BoatGen.exe (1-3 минуты)...
if exist "%~dp0build" rmdir /s /q "%~dp0build"
%PY% -m PyInstaller --noconfirm --clean --windowed --log-level WARN --name BoatGen ^
  --icon "%~dp0source\assets\boatgen.ico" ^
  --add-data "%~dp0source\ui;ui" ^
  --add-data "%~dp0source\engine\data;engine\data" ^
  --distpath "%~dp0build\dist" --workpath "%~dp0build\work" --specpath "%~dp0build" ^
  "%~dp0source\app.py"
if errorlevel 1 goto fail

echo   [3/3] Копирование...
if exist "%~dp0_internal" rmdir /s /q "%~dp0_internal"
xcopy /e /i /y /q "%~dp0build\dist\BoatGen\*" "%~dp0." >nul
if errorlevel 1 goto fail
rmdir /s /q "%~dp0build"

echo.
echo   Готово! Запускайте BoatGen.exe в этой папке.
echo.
start "" "%~dp0BoatGen.exe"
pause
exit /b 0

:fail
echo.
echo   Ошибка сборки. Проверьте подключение к интернету и попробуйте снова.
echo   Можно запустить программу и без сборки: "Запустить без сборки.bat".
echo.
pause
exit /b 1
