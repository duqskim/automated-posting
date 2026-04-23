"""
파이프라인 Celery 태스크
Redis 없으면 동기 실행
"""
import asyncio
from loguru import logger

from app.tasks.celery_app import celery_app, ASYNC_MODE
from app.agents.pipeline import PipelineController


def _run_pipeline_sync(market: str, topic: str, target_platforms: list[str] | None = None) -> dict:
    """동기 실행 (Redis 없을 때)"""
    controller = PipelineController(market)
    state = asyncio.run(controller.run(topic=topic, target_platforms=target_platforms))

    return {
        "stage": state.stage,
        "score": state.quality.score if state.quality else None,
        "platforms_completed": len(state.content.platform_contents) if state.content else 0,
        "error": state.error,
    }


if ASYNC_MODE and celery_app:
    @celery_app.task(bind=True, name="pipeline.run")
    def run_pipeline_task(self, market: str, topic: str, target_platforms: list[str] | None = None):
        """Celery 비동기 태스크"""
        logger.info(f"[Celery] 파이프라인 시작: {topic} ({market})")
        self.update_state(state="PROGRESS", meta={"stage": "researching"})

        result = _run_pipeline_sync(market, topic, target_platforms)

        logger.info(f"[Celery] 파이프라인 완료: {result['stage']}")
        return result
else:
    def run_pipeline_task(market: str, topic: str, target_platforms: list[str] | None = None):
        """동기 폴백 (Redis 없을 때 직접 실행)"""
        logger.info(f"[Sync] 파이프라인 시작: {topic} ({market})")
        return _run_pipeline_sync(market, topic, target_platforms)
