@echo off
rem --- diagnostic launcher -------------------------------------------------
rem Starts the two monitor windows and records what happened to a log next to
rem this file, so a failure can be diagnosed afterwards.
rem
rem Run it by double-clicking, then send me: bmu_testkit\tools\start_monitor_dual.log
rem
rem ASCII only - cmd.exe reads this file as the system locale codepage.
setlocal
set "PYW=D:\Anaconda3\envs\pyqt_side_all_0328\pythonw.exe"
set "LOG=%~dp0start_monitor_dual.log"

echo ==== launcher run %DATE% %TIME% > "%LOG%"
pushd "%~dp0..\.."
echo cwd=%CD% >> "%LOG%"
echo pyw=%PYW% >> "%LOG%"
if not exist "%PYW%" echo !! pythonw NOT FOUND >> "%LOG%"

echo --- start A (39527) --- >> "%LOG%"
start "A - HEX" "%PYW%" -m bmu_testkit.watch_serial --port 39527 --view hex
echo start A returned errorlevel=%errorlevel% >> "%LOG%"

ping -n 2 127.0.0.1 >nul

echo --- start B (39528) --- >> "%LOG%"
start "B - ASCII" "%PYW%" -m bmu_testkit.watch_serial --port 39528 --view ascii
echo start B returned errorlevel=%errorlevel% >> "%LOG%"

echo --- netstat --- >> "%LOG%"
netstat -ano -p UDP | findstr "3952" >> "%LOG%" 2>&1

echo --- tasklist --- >> "%LOG%"
tasklist | findstr /i python >> "%LOG%" 2>&1

echo ==== launcher done >> "%LOG%"
popd
endlocal
