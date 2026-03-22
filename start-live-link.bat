@echo off
echo ==============================================================
echo WSAS Permanent Link Generator
echo ==============================================================
echo Your permanent link is: https://wsas-safety-app.loca.lt
echo.
echo Please wait while the tunnel connects...
npx localtunnel --port 5000 --subdomain wsas-safety-app
pause
