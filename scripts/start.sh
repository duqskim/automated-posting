#!/bin/bash
# automated-posting 서버 시작 스크립트
# 실행: ./scripts/start.sh

BACKEND="$(cd "$(dirname "$0")/../backend" && pwd)"
cd "$BACKEND"

# 1. Redis 시작
echo "[1/3] Redis 시작..."
if ! redis-cli ping &>/dev/null; then
  redis-server --daemonize yes --logfile /tmp/redis.log
  sleep 1
fi
redis-cli ping && echo "Redis OK" || { echo "Redis 시작 실패"; exit 1; }

# 2. Celery worker 시작
echo "[2/3] Celery worker 시작..."
pkill -9 -f "celery worker" 2>/dev/null; sleep 1
REDIS_URL=redis://localhost:6379/0 PYTHONPATH=$BACKEND \
  nohup $BACKEND/.venv/bin/celery \
    -A app.tasks.celery_app:celery_app worker \
    --loglevel=info -c 2 \
    > /tmp/celery_worker.log 2>&1 &
sleep 2
echo "Celery worker started (log: /tmp/celery_worker.log)"

# 3. uvicorn 서버 시작
echo "[3/3] uvicorn 서버 시작..."
pkill -f "uvicorn app.main" 2>/dev/null; sleep 1
REDIS_URL=redis://localhost:6379/0 nohup $BACKEND/.venv/bin/uvicorn \
  app.main:app --host 0.0.0.0 --port 8000 --log-level info \
  > /tmp/uvicorn.log 2>&1 &
sleep 3

echo ""
echo "=== 서버 실행 완료 ==="
echo "API:    http://localhost:8000"
echo "Redis:  redis://localhost:6379"
echo "Celery: /tmp/celery_worker.log"
