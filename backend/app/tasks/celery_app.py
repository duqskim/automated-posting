"""
Celery 앱 설정
Redis 없으면 동기 모드로 폴백
"""
import os

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
        task_time_limit=600,  # 10분
    )
    ASYNC_MODE = True
else:
    celery_app = None
    ASYNC_MODE = False
