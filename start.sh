#!/bin/bash
# automated-posting 개발 서버 시작 스크립트

BACKEND_DIR="/Users/sol/.gemini/antigravity/playground/automated-posting/backend"
cd "$BACKEND_DIR"

echo "=== 기존 프로세스 정리 ==="
# 포트 8000 점유 프로세스 종료
lsof -ti:8000 | xargs kill -9 2>/dev/null
# 이전 Celery 워커 종료
pkill -9 -f "celery.*celery_app\|app.tasks.celery_app" 2>/dev/null
sleep 2

echo "=== Celery 워커 시작 ==="
"$BACKEND_DIR/.venv/bin/celery" -A app.tasks.celery_app worker \
    --loglevel=info \
    --concurrency=2 \
    > /tmp/celery_worker.log 2>&1 &
CELERY_PID=$!
echo "Celery PID: $CELERY_PID"
sleep 2

echo "=== FastAPI 백엔드 시작 ==="
"$BACKEND_DIR/.venv/bin/uvicorn" app.main:app \
    --reload \
    --port 8000 \
    --host 0.0.0.0 \
    2>&1 | tee /tmp/uvicorn.log &
UVICORN_PID=$!
echo "Uvicorn PID: $UVICORN_PID"

echo ""
echo "✅ 서버 시작 완료"
echo "   백엔드: http://localhost:8000"
echo "   프론트엔드는 별도로 실행: cd frontend && npm run dev"
echo "   Celery 로그: tail -f /tmp/celery_worker.log"
echo "   Uvicorn 로그: tail -f /tmp/uvicorn.log"
echo ""
echo "종료하려면 Ctrl+C 후: pkill -f 'uvicorn\|celery.*celery_app'"
wait $UVICORN_PID
