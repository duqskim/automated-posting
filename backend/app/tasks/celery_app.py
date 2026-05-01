"""
Celery 앱 설정
Redis 없으면 동기 모드로 폴백
"""
import os
from pathlib import Path

# Celery worker는 CWD가 다를 수 있으므로 .env를 절대경로로 명시적 로드
# (os.environ에 주입해야 os.environ.get("GEMINI_API_KEY") 등이 동작)
_env_path = Path(__file__).parent.parent.parent / ".env"
if _env_path.exists():
    from dotenv import load_dotenv
    load_dotenv(str(_env_path), override=True)

REDIS_URL = os.getenv("REDIS_URL", "")

if REDIS_URL:
    from celery import Celery
    celery_app = Celery(
        "automated_posting",
        broker=REDIS_URL,
        backend=REDIS_URL,
    )
    celery_app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="Asia/Seoul",
        task_track_started=True,
        task_time_limit=1800,  # 30분 (Veo 영상 생성 시간 고려)
        include=["app.tasks.pipeline_task"],  # 태스크 자동 등록
    )
    ASYNC_MODE = True
else:
    celery_app = None
    ASYNC_MODE = False
