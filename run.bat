@echo off
echo.
echo ==========================================
echo   Starting File Processing Web App
echo ==========================================
echo.
echo The application will be available at:
echo http://localhost:8000
echo.
echo Press CTRL+C to stop the server.
echo.

docker compose up --build

echo.
echo Application stopped.
pause
