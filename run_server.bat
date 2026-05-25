@echo off
title Railway Project Server

if exist "venv\Scripts\activate.bat" (
    call "venv\Scripts\activate.bat"
)

python manage.py runserver

echo.
echo "--- Server stopped. Console remains open. ---"
cmd /k
