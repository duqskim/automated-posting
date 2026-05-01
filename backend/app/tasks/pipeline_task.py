"""
파이프라인 Celery 태스크
Redis 없으면 동기 실행 (서버 블로킹 주의)
"""
import asyncio
import json
from loguru import logger

from app.tasks.celery_app import celery_app, ASYNC_MODE
from app.agents.pipeline import PipelineController


# ─── DB 직접 쓰기 (Celery worker용) ──────────────────────────

def _write_video_result_to_db(project_id: int, video_result: dict):
    """Celery worker 프로세스에서 직접 SQLite에 영상 결과 저장"""
    from sqlalchemy import create_engine, text
    from app.settings import settings

    # aiosqlite → 동기 드라이버로 변환
    db_url = settings.database_url.replace("+aiosqlite", "")
    engine = create_engine(db_url)
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT stage_results FROM projects WHERE id = :id"),
                {"id": project_id},
            ).fetchone()
            if not row:
                logger.error(f"[Celery] 프로젝트 {project_id}를 DB에서 찾을 수 없음")
                return
            sr = json.loads(row[0]) if row[0] else {}
            sr["video"] = video_result
            conn.execute(
                text("UPDATE projects SET stage_results = :sr WHERE id = :id"),
                {"sr": json.dumps(sr, ensure_ascii=False), "id": project_id},
            )
            conn.commit()
            logger.info(f"[Celery] DB 업데이트 완료: project_id={project_id}")
    finally:
        engine.dispose()


# ─── 공통 동기 실행 헬퍼 ─────────────────────────────────────

def _run_pipeline_sync(market: str, topic: str, target_platforms: list[str] | None = None) -> dict:
    controller = PipelineController(market)
    state = asyncio.run(controller.run(topic=topic, target_platforms=target_platforms))
    return {
        "stage": state.stage,
        "score": state.quality.score if state.quality else None,
        "platforms_completed": len(state.content.platform_contents) if state.content else 0,
        "error": state.error,
    }


def _run_video_sync(
    market: str,
    topic: str,
    content_dict: dict,
    platform: str,
    scene_image_paths: list,
    scene_image_prompts: list | None = None,
    tts_provider: str = "none",
    video_plan_dict: dict | None = None,
    bgm_category: str = "none",
    video_prompts: list | None = None,
    shot_script_dict: dict | None = None,
    frame_image_paths: dict | None = None,
    frame_motion_prompts: list | None = None,
) -> dict:
    controller = PipelineController(market)
    return asyncio.run(controller.run_video(
        content_dict=content_dict,
        topic=topic,
        platform=platform,
        scene_image_paths=scene_image_paths,
        scene_image_prompts=scene_image_prompts,
        tts_provider=tts_provider,
        video_plan_dict=video_plan_dict,
        bgm_category=bgm_category,
        video_prompts=video_prompts,
        shot_script_dict=shot_script_dict,
        frame_image_paths=frame_image_paths,
        frame_motion_prompts=frame_motion_prompts,
    ))


# ─── Celery 태스크 (Redis 있을 때) ────────────────────────────

if ASYNC_MODE and celery_app:
    @celery_app.task(bind=True, name="pipeline.run")
    def run_pipeline_task(self, market: str, topic: str, target_platforms: list[str] | None = None):
        logger.info(f"[Celery] 파이프라인 시작: {topic} ({market})")
        self.update_state(state="PROGRESS", meta={"stage": "researching"})
        result = _run_pipeline_sync(market, topic, target_platforms)
        logger.info(f"[Celery] 파이프라인 완료: {result['stage']}")
        return result

    @celery_app.task(bind=True, name="pipeline.video")
    def run_video_task(
        self,
        project_id: int,
        market: str,
        topic: str,
        content_dict: dict,
        platform: str,
        scene_image_paths: list,
        scene_image_prompts: list | None = None,
        tts_provider: str = "none",
        video_plan_dict: dict | None = None,
        bgm_category: str = "none",
        video_prompts: list | None = None,
        shot_script_dict: dict | None = None,
        frame_image_paths: dict | None = None,
        frame_motion_prompts: list | None = None,
    ):
        """Celery 비동기 영상 제작 태스크 — 완료 시 DB에 직접 저장"""
        logger.info(f"[Celery] 영상 제작 시작: project_id={project_id}")
        self.update_state(state="PROGRESS", meta={"stage": "video_processing"})

        try:
            result = _run_video_sync(
                market=market,
                topic=topic,
                content_dict=content_dict,
                platform=platform,
                scene_image_paths=scene_image_paths,
                scene_image_prompts=scene_image_prompts,
                tts_provider=tts_provider,
                video_plan_dict=video_plan_dict,
                bgm_category=bgm_category,
                video_prompts=video_prompts,
                shot_script_dict=shot_script_dict,
                frame_image_paths=frame_image_paths,
                frame_motion_prompts=frame_motion_prompts,
            )
            video_data = {
                "platform": platform,
                "full_video": result.get("full_video"),
                "shorts_video": result.get("shorts_video"),
                "auto_shorts": result.get("auto_shorts"),
                "duration": result.get("duration"),
                "clips_count": result.get("clips_count", 0),
                "error": result.get("error"),
                "video_review": result.get("video_review"),
            }
        except Exception as e:
            logger.error(f"[Celery] 영상 제작 실패: project_id={project_id}, error={e}")
            video_data = {
                "platform": platform,
                "error": str(e),
                "clips_count": 0,
            }

        _write_video_result_to_db(project_id, video_data)
        logger.info(f"[Celery] 영상 제작 태스크 종료: project_id={project_id}")
        return video_data

else:
    # ─── 폴백 (Redis 없을 때 — 동기 직접 실행) ──────────────────

    def run_pipeline_task(market: str, topic: str, target_platforms: list[str] | None = None):
        logger.info(f"[Sync] 파이프라인 시작: {topic} ({market})")
        return _run_pipeline_sync(market, topic, target_platforms)

    def run_video_task(
        project_id: int,
        market: str,
        topic: str,
        content_dict: dict,
        platform: str,
        scene_image_paths: list,
        scene_image_prompts: list | None = None,
        tts_provider: str = "none",
        video_plan_dict: dict | None = None,
        bgm_category: str = "none",
        video_prompts: list | None = None,
        shot_script_dict: dict | None = None,
        frame_image_paths: dict | None = None,
        frame_motion_prompts: list | None = None,
    ):
        """동기 폴백 — 서버 블로킹 발생, Redis 설치 권장"""
        logger.warning(f"[Sync] 영상 제작 동기 실행 (블로킹) project_id={project_id}")
        try:
            result = _run_video_sync(
                market=market,
                topic=topic,
                content_dict=content_dict,
                platform=platform,
                scene_image_paths=scene_image_paths,
                scene_image_prompts=scene_image_prompts,
                tts_provider=tts_provider,
                video_plan_dict=video_plan_dict,
                bgm_category=bgm_category,
                video_prompts=video_prompts,
                shot_script_dict=shot_script_dict,
                frame_image_paths=frame_image_paths,
                frame_motion_prompts=frame_motion_prompts,
            )
            return {
                "platform": platform,
                "full_video": result.get("full_video"),
                "shorts_video": result.get("shorts_video"),
                "auto_shorts": result.get("auto_shorts"),
                "duration": result.get("duration"),
                "clips_count": result.get("clips_count", 0),
                "error": result.get("error"),
                "video_review": result.get("video_review"),
            }
        except Exception as e:
            return {"platform": platform, "error": str(e), "clips_count": 0}
