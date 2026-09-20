@echo off
rem Start the serial monitor window.
rem Uses pyqt_side_all_0328 env: PyQt5 is only installed there.
rem ASCII only - cmd.exe reads this file as the system locale codepage.
rem
rem Usage:
rem   start_monitor.bat                     -> COM11 self port, HEX view
rem   start_monitor.bat --view ascii        -> ASCII view
rem   start_monitor.bat --port 39528 --view ascii --title "COM7 log"
setlocal
set "PYW=D:\Anaconda3\envs\pyqt_side_all_0328\pythonw.exe"
set "PROJ=%~dp0..\.."
pushd "%PROJ%"
"%PYW%" -m bmu_testkit.watch_serial %*
if errorlevel 1 (
    echo.
    echo [ERROR] failed to start. Run this to see the reason:
    echo     D:\Anaconda3\envs\pyqt_side_all_0328\python.exe -m bmu_testkit.watch_serial
    pause
)
popd
endlocal
