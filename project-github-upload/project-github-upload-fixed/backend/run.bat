@echo off
echo ==========================================
echo Capstone Design Server Starter
echo ==========================================
echo.

cd /d "%~dp0"

set "PYTHON_EXE=.venv\Scripts\python.exe"

IF NOT EXIST "%PYTHON_EXE%" (
    echo [INFO] Creating virtual environment in .venv ...
    py -m venv .venv
    IF ERRORLEVEL 1 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
)

echo [INFO] Checking backend dependencies...
"%PYTHON_EXE%" -c "import fastapi, uvicorn" >nul 2>nul
IF ERRORLEVEL 1 (
    echo [INFO] Installing backend dependencies...
    "%PYTHON_EXE%" -m pip install -r requirements.txt
    IF ERRORLEVEL 1 (
        echo [ERROR] Failed to install backend dependencies.
        pause
        exit /b 1
    )
)

echo [INFO] Starting FastAPI server...
IF "%SERVER_HOST%"=="" set "SERVER_HOST=127.0.0.1"
IF "%SERVER_PORT%"=="" set "SERVER_PORT=8000"
IF "%SERVER_RELOAD%"=="" set "SERVER_RELOAD=1"

set "UVICORN_RELOAD=--reload"
IF /I "%SERVER_RELOAD%"=="0" set "UVICORN_RELOAD="
IF /I "%SERVER_RELOAD%"=="false" set "UVICORN_RELOAD="
IF /I "%SERVER_RELOAD%"=="no" set "UVICORN_RELOAD="
IF /I "%SERVER_RELOAD%"=="off" set "UVICORN_RELOAD="

"%PYTHON_EXE%" -m uvicorn main:app %UVICORN_RELOAD% --host %SERVER_HOST% --port %SERVER_PORT%
pause
