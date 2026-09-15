@echo off
:: Simple alias - calls START.bat
set "DIR=%~dp0"
call "%DIR%START.bat" %*
