@echo off
chcp 65001 >nul
setlocal
set "BASE=%~dp0"
set "URL=file:///%BASE:\=/%index.html"
set "PROFILE=%BASE%profile"
set "EDGE=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
if not exist "%EDGE%" set "EDGE=%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"

if exist "%EDGE%" goto useedge
echo 没找到 Microsoft Edge，改用系统默认浏览器打开。
start "" "%BASE%index.html"
goto done

:useedge
start "" "%EDGE%" --app="%URL%" --user-data-dir="%PROFILE%" --no-first-run --no-default-browser-check --no-service-autorun --disable-component-update --disable-background-networking --disable-sync --disk-cache-size=52428800 --window-size=1300,900

:done
endlocal
