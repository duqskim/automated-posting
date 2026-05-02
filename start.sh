#!/bin/bash
# automated-posting 개발 서버 시작 스크립트
# 포트: 8001 (8000은 shadow-meteorite가 사용)

BACKEND_DIR="/Users/sol/.gemini/antigravity/playground/automated-posting/backend"
PORT=8001

cd "$BACKEND_DIR"

echo "=== 기존 프로세스 정리 ==="
# automated-posting 백엔드 uvicorn만 종료 (shadow-meteorite 건드리지 않음)
lsof -ti:$PORT | xargs kill -9 2>/dev/null
sleep 1

# automated-posting의 Celery 워커만 종료 (PID 기반)
VENV_PYTHON="$BACKEND_DIR/.venv/bin/python"
pkill -9 -f "$VENV_PYTHON.*celery" 2>/dev/null
pkill -9 -f "celery.*app.tasks.celery_app" 2>/dev/null
sleep 2

echo "=== Celery 워커 시작 (concurrency=1) ==="
PYTHONPATH="$BACKEND_DIR" "$BACKEND_DIR/.venv/bin/celery" -A app.tasks.celery_app worker \
    --loglevel=info \
    --concurrency=1 \
    -Q celery \
    > /tmp/automated_celery.log 2>&1 &
CELERY_PID=$!
echo "Celery PID: $CELERY_PID"
sleep 2

echo "=== FastAPI 백엔드 시작 (포트 $PORT) ==="
PYTHONPATH="$BACKEND_DIR" "$BACKEND_DIR/.venv/bin/uvicorn" app.main:app \
    --port $PORT \
    --host 0.0.0.0 \
    2>&1 | tee /tmp/automated_uvicorn.log &
UVICORN_PID=$!
echo "Uvicorn PID: $UVICORN_PID"

echo ""
echo "서버 시작 완료"
echo "  백엔드: http://localhost:$PORT"
echo "  헬스체크: http://localhost:$PORT/api/health"
echo "  프론트엔드는 별도 실행: cd frontend && npm run dev"
echo "  Celery 로그: tail -f /tmp/automated_celery.log"
echo "  Uvicorn 로그: tail -f /tmp/automated_uvicorn.log"
echo ""
echo "종료: kill $UVICORN_PID $CELERY_PID"

wait $UVICORN_PID
