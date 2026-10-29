@echo off
title DriveAlert - Allow Port 5000 in Windows Firewall
echo ================================================================
echo   DriveAlert - Enable Mobile and Network Access
echo ================================================================
echo.
echo Checking administrator privileges...

net session >nul 2>&1
if %errorLevel% neq 0 (
    echo Requesting Administrator permission...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

echo Adding Windows Defender Firewall Rule for Port 5000 (Flask)...
netsh advfirewall firewall delete rule name="DriveAlert Flask Port 5000" >nul 2>&1
netsh advfirewall firewall add rule name="DriveAlert Flask Port 5000" dir=in action=allow protocol=TCP localport=5000 >nul 2>&1

echo Unblocking Python in Windows Firewall...
powershell -Command "Get-NetFirewallRule | Where-Object { $_.DisplayName -like '*python*' -and $_.Direction -eq 'Inbound' } | Set-NetFirewallRule -Action Allow -Enabled True" >nul 2>&1

echo.
echo ================================================================
echo   SUCCESS! Windows Firewall has been configured.
echo   You can now connect to this web app from:
echo   - Mobile phones on the same Wi-Fi
echo   - Other laptops or PCs on the same Wi-Fi
echo ================================================================
echo.
pause
