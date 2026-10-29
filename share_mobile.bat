@echo off
title DriveAlert - Public HTTPS Link (Any Device / Any Network)
color 0B
echo.
echo  ============================================================
echo    DriveAlert - Share on ANY Device, ANY Network
echo    Works on: Mobile 4G/5G, Home Wi-Fi, Office, Hotspot
echo  ============================================================
echo.

REM -- Check if DriveAlert server is running --
curl -s http://127.0.0.1:5000 >nul 2>&1
if errorlevel 1 (
    echo [!] DriveAlert server is NOT running.
    echo     Please double-click  run.bat  first, then run this.
    echo.
    pause
    exit /b 1
)

echo [OK] Server is running on port 5000.
echo.
echo  Connecting to secure HTTPS tunnel...
echo  A public https://....lhr.life link will appear below.
echo.
echo  Open that link on ANY phone, tablet, or laptop worldwide!
echo  Share it via WhatsApp, SMS, or QR scanner.
echo.
echo  Press Ctrl+C to stop sharing.
echo  ============================================================
echo.

:tunnel
ssh -o StrictHostKeyChecking=no ^
    -o ServerAliveInterval=15 ^
    -o ServerAliveCountMax=3 ^
    -o ConnectTimeout=10 ^
    -R 80:127.0.0.1:5000 nokey@localhost.run

echo.
echo [!] Tunnel disconnected. Reconnecting in 5 seconds...
timeout /t 5 >nul
goto tunnel
