@echo off
cd /d "%~dp0"
if not exist ".venv\" (
  echo Membuat virtual environment...
  python -m venv .venv
  call .venv\Scripts\pip install -r requirements.txt >nul
)
.venv\Scripts\python -m src.narasi %*
