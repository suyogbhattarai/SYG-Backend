@echo off
REM ----------------------------
REM Start Redis server (inside WSL)
REM ----------------------------
echo Starting Redis server in WSL...
start "Redis Server (WSL)" wsl bash -c "sudo service redis-server start && tail -f /var/log/redis/redis-server.log"

REM Wait for Redis to initialize
echo Waiting for Redis to initialize...
timeout /t 3 /nobreak

REM ----------------------------
REM Start Celery worker
REM ----------------------------
echo Starting Celery worker...
start "Celery Worker" cmd /k "celery -A Dawlogs_backend worker --loglevel=info --pool=solo"

REM ----------------------------
REM Start Django development server
REM ----------------------------
echo Starting Django server...
start "Django Server" cmd /k "python manage.py runserver 0.0.0.0:8000"

echo All processes started.
pause
