#!/bin/bash
# automated-posting 서버 종료 스크립트

BACKEND_DIR="/Users/sol/.gemini/antigravity/playground/automated-posting/backend"
PORT=8001

echo "=== automated-posting 종료 ==="

# 포트 8001 uvicorn 종료
UVICORN_PIDS=$(lsof -ti:$PORT 2>/dev/null)
if [ -n "$UVICORN_PIDS" ]; then
    echo "Uvicorn 종료 (PID: $UVICORN_PIDS)"
    echo "$UVICORN_PIDS" | xargs kill -TERM 2>/dev/null
    sleep 2
    echo "$UVICORN_PIDS" | xargs kill -9 2>/dev/null
fi

# automated-posting venv의 Celery만 종료
VENV_PYTHON="$BACKEND_DIR/.venv/bin/python"
CELERY_PIDS=$(pgrep -f "$VENV_PYTHON.*celery" 2>/dev/null)
if [ -n "$CELERY_PIDS" ]; then
    echo "Celery 종료 (PID: $CELERY_PIDS)"
    echo "$CELERY_PIDS" | xargs kill -TERM 2>/dev/null
    sleep 2
    echo "$CELERY_PIDS" | xargs kill -9 2>/dev/null
fi

echo "종료 완료"
