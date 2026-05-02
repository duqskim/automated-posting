"""파이프라인 API — 풀 실행 + 단계별 실행 + DB 저장"""
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.models.base import get_db
from app.models.project import Project, SeriesCharacter
from app.models.content import GeneratedContent
from app.models.user import User
from app.dependencies import get_current_user
from app.agents.pipeline import PipelineController
from app.tasks.celery_app import ASYNC_MODE

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])


# ─── 공통 스키마 ────────────────────────────────────────────

class ContentPreview(BaseModel):
    id: int | None = None
    platform: str
    hook: str
    body: list[str]
    caption: str
    hashtags: list[str]
    cta: str
    image_urls: list[str] = []


class PipelineResponse(BaseModel):
    project_id: int
    stage: str
    score: float | None = None
    platforms_completed: int = 0
    platforms_total: int = 0
    error: str | None = None
    contents: list[ContentPreview] = []


# ─── 단계별 스키마 ──────────────────────────────────────────

class StageStateResponse(BaseModel):
    """GET /{id}/stage → 현재 단계 상태 전체"""
    current_step: str  # idle / research_done / hooks_done / write_done / render_done / video_done
    research: dict | None = None
    hooks: dict | None = None
    selected_hook_index: int = 0
    content: dict | None = None
    image_urls: list[str] = []
    image_prompts: list[str] = []      # 슬라이드별 현재 이미지 프롬프트 (협업 수정용)
    thumbnail_url: str | None = None
    quality_score: float | None = None
    quality_status: str | None = None  # "pass" | "warn" | "block"
    fact_check: dict | None = None
    video: dict | None = None
    metadata: dict | None = None       # YouTube SEO 메타데이터 (MetadataAgent)
    thumbnail_spec: dict | None = None  # 썸네일 스펙 (ThumbnailAgent)


class SelectHookRequest(BaseModel):
    selected_hook_index: int


class SaveSlidesRequest(BaseModel):
    platform: str
    slides: list[str]
    image_prompts: list[str] | None = None


# ─── 단계 판별 ──────────────────────────────────────────────

def _current_step(stage_results: dict | None) -> str:
    if not stage_results:
        return "idle"
    video = stage_results.get("video")
    if video:
        if isinstance(video, dict) and video.get("status") == "processing":
            return "video_processing"
        return "video_done"
    if stage_results.get("render_status") == "processing":
        return "render_processing"
    if stage_results.get("images") or stage_results.get("frame_image_paths"):
        return "render_done"
    if stage_results.get("content"):
        return "write_done"
    if stage_results.get("hooks"):
        return "hooks_done"
    if stage_results.get("research"):
        return "research_done"
    return "idle"


def _image_urls_from_paths(paths: list[str], render_type: str = "scene") -> list[str]:
    if render_type == "carousel":
        prefix = "/api/carousel"
    else:
        # "scene" | "text_image" 모두 scenes 디렉토리 사용
        prefix = "/api/scenes"
    return [f"{prefix}/{p.split('/')[-1]}" for p in paths]


# ─── 단계별 엔드포인트 ──────────────────────────────────────

@router.get("/{project_id}/stage", response_model=StageStateResponse)
async def get_stage_state(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """현재 단계 결과 전체 조회 (페이지 리로드 시 상태 복원용)"""
    project = await _get_user_project(project_id, current_user.id, db)
    sr = project.stage_results or {}
    images = sr.get("images", [])

    # 영상 결과: DB엔 절대경로(full_video)로 저장, 프론트는 URL(full_video_url) 기대
    video_raw = sr.get("video")
    def _vurl(p: str | None) -> str | None:
        return f"/api/videos/{Path(p).name}" if p else None

    video_out = None
    if video_raw:
        if isinstance(video_raw, dict) and video_raw.get("status") == "processing":
            # 백그라운드 처리 중 — 프론트에 processing 상태 전달
            video_out = {"status": "processing", "platform": video_raw.get("platform", "")}
        else:
            video_out = {
                "platform": video_raw.get("platform"),
                "full_video_url": _vurl(video_raw.get("full_video")),
                "shorts_video_url": _vurl(video_raw.get("shorts_video")),
                "auto_shorts_url": _vurl(video_raw.get("auto_shorts")),
                "duration": video_raw.get("duration"),
                "clips_count": video_raw.get("clips_count", 0),
                "error": video_raw.get("error"),
                "video_review": video_raw.get("video_review"),
            }

    render_type = sr.get("images_render_type", "scene")

    # 플랫폼 첫 번째 콘텐츠에서 image_prompts 추출
    image_prompts: list[str] = []
    content_data = sr.get("content")
    if content_data:
        platform_contents = content_data.get("platform_contents", [])
        if platform_contents:
            image_prompts = platform_contents[0].get("image_prompts") or []

    return StageStateResponse(
        current_step=_current_step(sr),
        research=sr.get("research"),
        hooks=sr.get("hooks"),
        selected_hook_index=sr.get("selected_hook_index", 0),
        content=sr.get("content"),
        image_urls=_image_urls_from_paths(images, render_type),
        image_prompts=image_prompts,
        thumbnail_url=sr.get("thumbnail_url"),
        quality_score=sr.get("quality_score"),
        quality_status=sr.get("quality_status"),
        fact_check=sr.get("fact_check"),
        video=video_out,
        metadata=sr.get("metadata"),
        thumbnail_spec=sr.get("thumbnail_spec"),
    )


@router.post("/{project_id}/stage/research")
async def run_stage_research(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Stage 1: 리서치 실행 → 결과 저장"""
    project = await _get_user_project(project_id, current_user.id, db)
    controller = PipelineController(project.market)

    try:
        research_dict = await controller.run_research(project.topic)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"리서치 실패: {e}")

    sr = dict(project.stage_results or {})
    sr["research"] = research_dict
    # 이후 단계 초기화 (재실행 시)
    sr.pop("hooks", None)
    sr.pop("selected_hook_index", None)
    sr.pop("content", None)
    sr.pop("images", None)
    project.stage_results = sr
    project.status = "researching"
    await db.commit()

    return {"step": "research_done", "research": research_dict}


@router.post("/{project_id}/stage/hooks")
async def run_stage_hooks(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Stage 2: 훅 생성 → 결과 저장"""
    project = await _get_user_project(project_id, current_user.id, db)
    sr = project.stage_results or {}

    if not sr.get("research"):
        raise HTTPException(status_code=400, detail="먼저 리서치를 실행해주세요")

    controller = PipelineController(project.market)
    try:
        hooks_dict = await controller.run_hooks(sr["research"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"훅 생성 실패: {e}")

    sr = dict(sr)
    sr["hooks"] = hooks_dict
    sr["selected_hook_index"] = hooks_dict.get("recommended_hook_index", 0)
    sr.pop("content", None)
    sr.pop("images", None)
    project.stage_results = sr
    await db.commit()

    return {"step": "hooks_done", "hooks": hooks_dict}


@router.patch("/{project_id}/stage/hooks")
async def select_hook(
    project_id: int,
    body: SelectHookRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """사용자가 훅 선택 → selected_hook_index 저장"""
    project = await _get_user_project(project_id, current_user.id, db)
    sr = dict(project.stage_results or {})

    if not sr.get("hooks"):
        raise HTTPException(status_code=400, detail="훅 생성을 먼저 실행해주세요")

    hooks = sr["hooks"].get("hooks", [])
    if body.selected_hook_index >= len(hooks):
        raise HTTPException(status_code=400, detail="유효하지 않은 훅 인덱스")

    sr["selected_hook_index"] = body.selected_hook_index
    project.stage_results = sr
    await db.commit()

    return {"selected_hook_index": body.selected_hook_index}


class WriteRequest(BaseModel):
    fix_facts: bool = False


@router.post("/{project_id}/stage/write")
async def run_stage_write(
    project_id: int,
    body: WriteRequest = WriteRequest(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Stage 3+4: 글쓰기 + 품질 검수 → 결과 저장
    fix_facts=True 시 이전 팩트체크에서 발견된 오류를 반영해 재작성
    """
    project = await _get_user_project(project_id, current_user.id, db)
    sr = project.stage_results or {}

    if not sr.get("hooks"):
        raise HTTPException(status_code=400, detail="훅 생성을 먼저 실행해주세요")

    # fix_facts=True 이면 이전 팩트체크에서 disputed 항목만 추출
    fact_corrections = None
    if body.fix_facts and sr.get("fact_check"):
        disputed = [
            c for c in sr["fact_check"].get("claims", [])
            if c.get("status") == "disputed"
        ]
        if disputed:
            fact_corrections = disputed
            logger.info(f"[write] 팩트 기반 재작성 — 수정 항목 {len(disputed)}개")

    controller = PipelineController(project.market)
    platforms = project.target_platforms or controller.profile.active_platforms

    # 시리즈 캐릭터 로드 (있으면 목소리/비주얼에 반영)
    character = await _load_series_character(project, db)
    if character:
        logger.info(f"[write] 캐릭터 적용: {character['name']}")

    try:
        result = await controller.run_write(
            research_dict=sr["research"],
            hooks_dict=sr["hooks"],
            selected_hook_index=sr.get("selected_hook_index", 0),
            target_platforms=list(platforms) if isinstance(platforms, (list, dict)) else platforms,
            fact_corrections=fact_corrections,
            character=character,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"글쓰기 실패: {e}")

    sr = dict(sr)
    sr["content"] = result["content"]
    sr["quality_score"] = result["quality_score"]
    sr["quality_status"] = result.get("quality_status")
    sr["fact_check"] = result.get("fact_check")
    sr.pop("images", None)
    project.stage_results = sr
    project.status = "writing"
    await db.commit()

    return {
        "step": "write_done",
        "content": result["content"],
        "quality_score": result["quality_score"],
        "quality_status": result.get("quality_status"),
        "quality_passed": result["quality_passed"],
        "fact_check": result.get("fact_check"),
    }


@router.patch("/{project_id}/stage/write")
async def save_slides(
    project_id: int,
    body: SaveSlidesRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """사용자 편집 슬라이드 저장 → content.platform_contents 업데이트"""
    project = await _get_user_project(project_id, current_user.id, db)
    sr = dict(project.stage_results or {})

    if not sr.get("content"):
        raise HTTPException(status_code=400, detail="글쓰기를 먼저 실행해주세요")

    content = dict(sr["content"])
    platform_contents = [dict(pc) for pc in content.get("platform_contents", [])]

    updated = False
    for pc in platform_contents:
        if pc["platform"] == body.platform:
            pc["body"] = body.slides
            if body.image_prompts is not None:
                pc["image_prompts"] = body.image_prompts
            updated = True
            break

    if not updated:
        raise HTTPException(status_code=404, detail=f"플랫폼 '{body.platform}'을 찾을 수 없습니다")

    content["platform_contents"] = platform_contents
    sr["content"] = content
    sr.pop("images", None)  # 슬라이드 수정 시 이미지 무효화
    project.stage_results = sr
    await db.commit()

    return {"platform": body.platform, "slides_count": len(body.slides)}


# ─── 이미지 프롬프트 협업 수정 ─────────────────────────────────

class PromptRewriteRequest(BaseModel):
    slide_index: int
    correction_intent: str        # 사용자 수정 요청 (한국어/영어 모두 가능)
    platform: str = "youtube"


class PromptPatchRequest(BaseModel):
    prompt: str                   # 확정된 프롬프트
    platform: str = "youtube"
    regenerate: bool = True       # True면 이미지 즉시 재생성


@router.post("/{project_id}/stage/prompts/rewrite")
async def rewrite_image_prompt(
    project_id: int,
    body: PromptRewriteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    이미지 프롬프트 협업 수정 (Step 1: AI 재작성)

    사용자가 수정 의도를 입력하면 AI가 현재 프롬프트를 재작성해 반환합니다.
    반환된 프롬프트는 사용자 확인 후 PATCH /stage/prompts/{slide_index}로 확정합니다.
    """
    from app.agents.media.image_prompter import rewrite_prompt
    from app.agents.pipeline import content_plan_from_dict

    project = await _get_user_project(project_id, current_user.id, db)
    sr = project.stage_results or {}

    if not sr.get("content"):
        raise HTTPException(status_code=400, detail="글쓰기를 먼저 실행해주세요")

    content_plan = content_plan_from_dict(sr["content"])
    target = next(
        (pc for pc in content_plan.platform_contents if pc.platform == body.platform),
        content_plan.platform_contents[0] if content_plan.platform_contents else None,
    )
    if not target:
        raise HTTPException(status_code=400, detail="콘텐츠 플랜 없음")
    if body.slide_index >= len(target.body):
        raise HTTPException(status_code=400, detail="슬라이드 인덱스 초과")

    # 현재 저장된 프롬프트 가져오기
    image_prompts: list[str] = target.image_prompts or []
    current_prompt = (
        image_prompts[body.slide_index]
        if body.slide_index < len(image_prompts)
        else f"Cinematic scene: {target.body[body.slide_index][:80]}"
    )

    character = await _load_series_character(project, db)
    character_dict = character.model_dump() if character else None

    try:
        new_prompt = await rewrite_prompt(
            current_prompt=current_prompt,
            correction_intent=body.correction_intent,
            slide_text=target.body[body.slide_index],
            topic=project.topic,
            character=character_dict,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"프롬프트 재작성 실패: {e}")

    return {
        "slide_index": body.slide_index,
        "original_prompt": current_prompt,
        "rewritten_prompt": new_prompt,
        "correction_intent": body.correction_intent,
    }


@router.patch("/{project_id}/stage/prompts/{slide_index}")
async def confirm_image_prompt(
    project_id: int,
    slide_index: int,
    body: PromptPatchRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    이미지 프롬프트 협업 수정 (Step 2: 확정 + 선택적 재생성)

    사용자가 확정한 프롬프트를 저장하고, regenerate=True면 이미지를 즉시 재생성합니다.
    """
    from app.agents.pipeline import content_plan_from_dict, _make_slug
    from app.agents.media.image_generation import generate_scene_image, SCENES_DIR, PLATFORM_ASPECT

    project = await _get_user_project(project_id, current_user.id, db)
    sr = project.stage_results or {}

    if not sr.get("content"):
        raise HTTPException(status_code=400, detail="글쓰기를 먼저 실행해주세요")

    content = sr["content"]
    platform_contents = content.get("platform_contents", [])

    # 해당 플랫폼 콘텐츠에서 image_prompts 업데이트
    updated = False
    for pc in platform_contents:
        if pc.get("platform") == body.platform:
            prompts = list(pc.get("image_prompts") or [])
            while len(prompts) <= slide_index:
                prompts.append("")
            prompts[slide_index] = body.prompt
            pc["image_prompts"] = prompts
            updated = True
            break

    if not updated:
        raise HTTPException(status_code=404, detail=f"플랫폼 '{body.platform}'을 찾을 수 없습니다")

    content["platform_contents"] = platform_contents
    sr = dict(sr)
    sr["content"] = content

    image_url: str | None = None

    # 즉시 이미지 재생성
    if body.regenerate:
        content_plan = content_plan_from_dict(content)
        target = next((pc for pc in content_plan.platform_contents if pc.platform == body.platform), None)
        if target and slide_index < len(target.body):
            slug = _make_slug(project.topic)
            path = SCENES_DIR / f"{slug}_{body.platform}_{slide_index:02d}.jpg"
            aspect_ratio = PLATFORM_ASPECT.get(body.platform, "16:9")
            try:
                result = await generate_scene_image(
                    slide_text=target.body[slide_index],
                    image_prompt=body.prompt,
                    output_path=path,
                    topic=project.topic,
                    language=PipelineController(project.market).profile.language,
                    aspect_ratio=aspect_ratio,
                )
                if result:
                    images = list(sr.get("images", []))
                    while len(images) <= slide_index:
                        images.append("")
                    images[slide_index] = str(result)
                    sr["images"] = images
                    image_url = f"/api/scenes/{Path(result).name}"
            except Exception as e:
                logger.warning(f"[prompts] 이미지 재생성 실패 (프롬프트는 저장됨): {e}")

    project.stage_results = sr
    await db.commit()

    return {
        "slide_index": slide_index,
        "prompt_saved": True,
        "image_regenerated": body.regenerate and image_url is not None,
        "image_url": image_url,
    }


class RenderRequest(BaseModel):
    platform: str = "youtube"
    image_provider: str = "auto"  # "auto" | "imagen" | "dalle"


@router.post("/{project_id}/stage/render")
async def run_stage_render(
    project_id: int,
    body: RenderRequest = RenderRequest(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Stage 4: 씬 이미지 생성 — Celery 백그라운드 작업으로 즉시 반환"""
    from app.tasks.pipeline_task import run_render_task, ASYNC_MODE

    project = await _get_user_project(project_id, current_user.id, db)
    sr = project.stage_results or {}

    if not sr.get("content"):
        raise HTTPException(status_code=400, detail="글쓰기를 먼저 실행해주세요")

    character = await _load_series_character(project, db)
    character_dict = character.model_dump() if character else None

    # Celery 작업 디스패치 (Redis 있을 때) — 즉시 반환
    if ASYNC_MODE:
        from app.tasks.celery_app import celery_app as _celery
        task = _celery.send_task(
            "pipeline.render",
            kwargs={
                "project_id": project_id,
                "market": project.market,
                "topic": project.topic,
                "content_dict": sr["content"],
                "platform": body.platform,
                "image_provider": body.image_provider,
                "character": character_dict,
            },
        )
        # 렌더링 중 상태 저장
        sr = dict(sr)
        sr["render_status"] = "processing"
        sr["render_task_id"] = task.id
        project.stage_results = sr
        await db.commit()
        return {
            "step": "render_processing",
            "task_id": task.id,
            "message": "렌더링이 백그라운드에서 시작됐습니다. /stage로 진행 상황을 확인하세요.",
        }

    # Redis 없을 때 — 인라인 실행 (블로킹)
    logger.warning(f"[render] Redis 없음 — 인라인 실행 (project_id={project_id})")
    result = run_render_task(
        project_id=project_id,
        market=project.market,
        topic=project.topic,
        content_dict=sr["content"],
        platform=body.platform,
        image_provider=body.image_provider,
        character=character_dict,
    )
    sr = dict(sr)
    sr.update({k: v for k, v in result.items() if v is not None})
    project.stage_results = sr
    project.status = "passed"
    await db.commit()

    image_paths = result.get("images", [])
    render_type = result.get("images_render_type", "scene")
    return {
        "step": "render_done",
        "platform": body.platform,
        "render_type": render_type,
        "image_urls": _image_urls_from_paths(image_paths, render_type),
        "images_count": len(image_paths),
        "thumbnail_url": result.get("thumbnail_url"),
        "metadata": result.get("metadata"),
        "thumbnail_spec": result.get("thumbnail_spec"),
    }


@router.post("/{project_id}/stage/render/{slide_index}")
async def regenerate_single_image(
    project_id: int,
    slide_index: int,
    body: RenderRequest = RenderRequest(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """단일 슬라이드 이미지 재생성"""
    from app.agents.media.image_generation import generate_scene_image, SCENES_DIR, PLATFORM_ASPECT
    from app.agents.pipeline import content_plan_from_dict, _make_slug

    project = await _get_user_project(project_id, current_user.id, db)
    sr = project.stage_results or {}

    if not sr.get("content"):
        raise HTTPException(status_code=400, detail="글쓰기를 먼저 실행해주세요")

    content_plan = content_plan_from_dict(sr["content"])

    target = next((pc for pc in content_plan.platform_contents if pc.platform == body.platform), None)
    if not target:
        target = content_plan.platform_contents[0]

    if slide_index >= len(target.body):
        raise HTTPException(status_code=400, detail="슬라이드 인덱스 초과")

    slug = _make_slug(project.topic)
    path = SCENES_DIR / f"{slug}_{body.platform}_{slide_index:02d}.jpg"
    aspect_ratio = PLATFORM_ASPECT.get(body.platform, "16:9")

    image_prompts = target.image_prompts or []
    img_prompt = image_prompts[slide_index] if slide_index < len(image_prompts) else ""

    try:
        result = await generate_scene_image(
            slide_text=target.body[slide_index],
            image_prompt=img_prompt,
            output_path=path,
            topic=project.topic,
            language=PipelineController(project.market).profile.language,
            aspect_ratio=aspect_ratio,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"이미지 재생성 실패: {e}")

    if not result:
        raise HTTPException(status_code=500, detail="이미지 생성 실패 (안전 필터 또는 API 오류)")

    # stage_results 이미지 목록 업데이트
    sr = dict(sr)
    images = list(sr.get("images", []))
    if slide_index < len(images):
        images[slide_index] = str(result)
    else:
        while len(images) < slide_index:
            images.append("")
        images.append(str(result))
    sr["images"] = images
    project.stage_results = sr
    await db.commit()

    return {
        "slide_index": slide_index,
        "image_url": f"/api/scenes/{Path(result).name}",
    }


class VideoRequest(BaseModel):
    platform: str = "youtube"
    tts_provider: str = "none"   # "none" | "gemini" | "elevenlabs"
    bgm_category: str = "none"   # "none" | "cinematic" | "ambient" | "upbeat" | "dramatic"


@router.post("/{project_id}/stage/video")
async def run_stage_video(
    project_id: int,
    body: VideoRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Stage 7: 영상 제작 — Celery 비동기 (Redis 있을 때) 또는 동기 폴백"""
    from app.tasks.celery_app import ASYNC_MODE
    from app.tasks.pipeline_task import run_video_task

    project = await _get_user_project(project_id, current_user.id, db)
    sr = project.stage_results or {}

    if not sr.get("content"):
        raise HTTPException(status_code=400, detail="글쓰기를 먼저 실행해주세요")
    has_images = sr.get("images") or sr.get("frame_image_paths")
    if not has_images:
        raise HTTPException(status_code=400, detail="씬 이미지를 먼저 생성해주세요 (Step 4)")

    if ASYNC_MODE:
        # ── Celery 모드: 즉시 반환, 백그라운드에서 처리 ──
        task = run_video_task.delay(
            project_id=project_id,
            market=project.market,
            topic=project.topic,
            content_dict=sr["content"],
            platform=body.platform,
            scene_image_paths=sr.get("images", []),
            scene_image_prompts=sr.get("scene_image_prompts"),
            tts_provider=body.tts_provider,
            video_plan_dict=sr.get("video_plan"),
            bgm_category=body.bgm_category,
            video_prompts=sr.get("video_prompts"),
            shot_script_dict=sr.get("shot_script"),
            frame_image_paths=sr.get("frame_image_paths"),
            frame_motion_prompts=sr.get("frame_motion_prompts"),
        )
        logger.info(f"[API] 영상 제작 Celery 태스크 시작: task_id={task.id}")

        # DB에 processing 상태 저장
        sr = dict(sr)
        sr["video"] = {"status": "processing", "platform": body.platform, "task_id": task.id}
        project.stage_results = sr
        await db.commit()

        return {
            "step": "video_processing",
            "task_id": task.id,
            "status": "processing",
            "message": "영상 제작이 백그라운드에서 시작됐습니다. 완료되면 자동으로 업데이트됩니다.",
        }
    else:
        # ── 동기 폴백: 서버 블로킹 (Redis 없을 때) ──
        logger.warning(f"[API] Redis 없음 — 영상 제작 동기 실행 (블로킹): project_id={project_id}")
        controller = PipelineController(project.market)

        try:
            result = await controller.run_video(
                content_dict=sr["content"],
                topic=project.topic,
                platform=body.platform,
                scene_image_paths=sr.get("images", []),
                scene_image_prompts=sr.get("scene_image_prompts"),
                tts_provider=body.tts_provider,
                video_plan_dict=sr.get("video_plan"),
                bgm_category=body.bgm_category,
                video_prompts=sr.get("video_prompts"),
                shot_script_dict=sr.get("shot_script"),
                frame_image_paths=sr.get("frame_image_paths"),
                frame_motion_prompts=sr.get("frame_motion_prompts"),
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"영상 제작 실패: {e}")

        def _video_url(path: str | None) -> str | None:
            return f"/api/videos/{Path(path).name}" if path else None

        sr = dict(sr)
        sr["video"] = {
            "platform": body.platform,
            "full_video": result.get("full_video"),
            "shorts_video": result.get("shorts_video"),
            "auto_shorts": result.get("auto_shorts"),
            "duration": result.get("duration"),
            "clips_count": result.get("clips_count", 0),
            "error": result.get("error"),
            "video_review": result.get("video_review"),
            "srt_paths": result.get("srt_paths"),
        }
        project.stage_results = sr
        await db.commit()

        return {
            "step": "video_done",
            "platform": body.platform,
            "full_video_url": _video_url(result.get("full_video")),
            "shorts_video_url": _video_url(result.get("shorts_video")),
            "auto_shorts_url": _video_url(result.get("auto_shorts")),
            "duration": result.get("duration"),
            "clips_count": result.get("clips_count", 0),
            "error": result.get("error"),
            "video_review": result.get("video_review"),
            "srt_paths": result.get("srt_paths"),
        }


# ─── Stage 8: 발행 ────────────────────────────────────────────

class PublishRequest(BaseModel):
    platform: str = "youtube"
    dry_run: bool = True


@router.post("/{project_id}/stage/publish")
async def run_stage_publish(
    project_id: int,
    body: PublishRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Stage 8: 발행 — YouTube 업로드 + SRT 자막"""
    from app.agents.publisher.agent import PublisherAgent
    from app.agents.writer.copywriter import ContentPlan, PlatformContent
    from app.config.market_profile import load_market_profile

    project = await _get_user_project(project_id, current_user.id, db)
    sr = project.stage_results or {}

    if not sr.get("content"):
        raise HTTPException(status_code=400, detail="글쓰기를 먼저 실행해주세요")

    video_data = sr.get("video", {})
    if not video_data.get("full_video") and not body.dry_run and body.platform in ("youtube", "youtube_shorts"):
        raise HTTPException(status_code=400, detail="영상 제작을 먼저 실행해주세요")

    # 콘텐츠 플랜 재구성
    content_dict = sr["content"]
    platform_contents = []
    for pc in content_dict.get("platform_contents", []):
        if pc.get("platform") == body.platform:
            platform_contents.append(PlatformContent(
                platform=pc["platform"],
                hook=pc.get("hook", ""),
                body=pc.get("body", []),
                caption=pc.get("caption", ""),
                hashtags=pc.get("hashtags", []),
                cta=pc.get("cta", ""),
                image_prompts=pc.get("image_prompts"),
            ))

    if not platform_contents:
        raise HTTPException(
            status_code=400,
            detail=f"플랫폼 {body.platform} 콘텐츠 없음 — 글쓰기 단계에서 해당 플랫폼을 포함해주세요",
        )

    content_plan = ContentPlan(
        topic=content_dict.get("topic", project.topic),
        platform_contents=platform_contents,
    )

    # SNS 계정 자격증명 (환경변수에서)
    import os
    sns_credentials = {
        "x": {
            "api_key": os.environ.get("X_API_KEY"),
            "api_secret": os.environ.get("X_API_SECRET"),
            "access_token": os.environ.get("X_ACCESS_TOKEN"),
            "access_secret": os.environ.get("X_ACCESS_SECRET"),
        }
    }

    profile = load_market_profile(project.market)
    publisher = PublisherAgent(profile, sns_credentials)

    image_paths = sr.get("images", []) or sr.get("frame_image_paths", [])

    try:
        result = await publisher.publish(
            content_plan=content_plan,
            dry_run=body.dry_run,
            video_path=video_data.get("full_video"),
            srt_paths=video_data.get("srt_paths"),
            metadata=sr.get("metadata"),
            image_paths=image_paths or None,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"발행 실패: {e}")

    # stage_results 업데이트
    sr = dict(sr)
    sr["publish"] = {
        "platform": body.platform,
        "dry_run": body.dry_run,
        "results": [
            {
                "platform": r.platform,
                "success": r.success,
                "post_url": r.post_url,
                "post_id": r.post_id,
                "error": r.error,
                "published_at": r.published_at,
            }
            for r in result.results
        ],
        "success_count": result.success_count,
        "fail_count": result.fail_count,
    }
    if result.success_count > 0:
        project.status = "published"
    project.stage_results = sr
    await db.commit()

    return {
        "step": "publish_done",
        "dry_run": body.dry_run,
        "total": result.total,
        "success_count": result.success_count,
        "fail_count": result.fail_count,
        "results": sr["publish"]["results"],
    }


# ─── 기존 풀 파이프라인 (호환) ────────────────────────────────

@router.post("/{project_id}/run", response_model=PipelineResponse)
async def run_full_pipeline(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """풀 파이프라인 실행 (기존 방식 유지)"""
    project = await _get_user_project(project_id, current_user.id, db)

    controller = PipelineController(project.market)
    state = await controller.run(
        topic=project.topic,
        target_platforms=project.target_platforms,
    )

    project.status = state.stage
    await db.commit()

    contents = []
    if state.content and state.content.platform_contents:
        await db.execute(
            delete(GeneratedContent).where(GeneratedContent.project_id == project_id)
        )

        score = int(state.quality.score) if state.quality else 0
        image_filenames = [p.split("/")[-1] for p in (state.image_paths or [])]

        for c in state.content.platform_contents:
            platform_images = []
            if c.platform in ("instagram", "threads", "linkedin"):
                platform_images = [f"/api/images/{f}" for f in image_filenames]

            record = GeneratedContent(
                project_id=project_id,
                platform=c.platform,
                hook=c.hook,
                body=c.body,
                caption=c.caption,
                hashtags=c.hashtags,
                cta=c.cta,
                quality_score=score,
                image_paths=platform_images,
            )
            db.add(record)

        await db.commit()

        result = await db.execute(
            select(GeneratedContent)
            .where(GeneratedContent.project_id == project_id)
            .order_by(GeneratedContent.id)
        )
        for row in result.scalars().all():
            contents.append(ContentPreview(
                id=row.id,
                platform=row.platform,
                hook=row.hook,
                body=row.body,
                caption=row.caption,
                hashtags=row.hashtags,
                cta=row.cta,
                image_urls=row.image_paths or [],
            ))

    return PipelineResponse(
        project_id=project.id,
        stage=state.stage,
        score=state.quality.score if state.quality else None,
        platforms_completed=len(contents),
        platforms_total=len(project.target_platforms or []),
        error=state.error,
        contents=contents,
    )


@router.get("/{project_id}/contents", response_model=list[ContentPreview])
async def get_contents(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """DB에 저장된 콘텐츠 조회"""
    await _get_user_project(project_id, current_user.id, db)

    result = await db.execute(
        select(GeneratedContent)
        .where(GeneratedContent.project_id == project_id)
        .order_by(GeneratedContent.id)
    )
    rows = result.scalars().all()

    return [
        ContentPreview(
            id=row.id,
            platform=row.platform,
            hook=row.hook,
            body=row.body,
            caption=row.caption,
            hashtags=row.hashtags,
            cta=row.cta,
            image_urls=row.image_paths or [],
        )
        for row in rows
    ]


@router.get("/{project_id}/stage/log")
async def get_stage_log(
    project_id: int,
    lines: int = 30,
    current_user: User = Depends(get_current_user),
):
    """Celery worker 로그 최신 N줄 반환 (영상 제작 진행 현황용)"""
    import os
    log_path = "/tmp/celery_worker.log"
    if not os.path.exists(log_path):
        return {"lines": [], "running": False}

    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
        all_lines = f.readlines()

    recent = [l.rstrip() for l in all_lines[-lines:] if l.strip()]

    # 간단한 진행 단계 파싱
    step = "대기 중"
    for line in reversed(recent):
        if "영상 조립" in line or "Assembly" in line:
            step = "영상 조립 중 (ffmpeg)"
            break
        if "TTS" in line and "완료" in line:
            step = "나레이션 완료 → 영상 조립 준비"
            break
        if "TTS" in line and "슬라이드" in line:
            import re
            m = re.search(r"슬라이드 (\d+)", line)
            step = f"나레이션 생성 중 (슬라이드 {m.group(1)})" if m else "나레이션 생성 중"
            break
        if "Veo" in line or "veo" in line:
            step = "씬 영상 생성 중 (Veo)"
            break

    return {"lines": recent, "step": step, "running": True}


async def _get_user_project(project_id: int, user_id: int, db: AsyncSession) -> Project:
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.user_id == user_id,
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다")
    return project


async def _load_series_character(project: Project, db: AsyncSession) -> dict | None:
    """프로젝트의 시리즈에서 active 캐릭터 1개 로드 → dict 반환"""
    if not project.series_id:
        return None
    result = await db.execute(
        select(SeriesCharacter).where(
            SeriesCharacter.series_id == project.series_id,
            SeriesCharacter.status == "active",
        ).limit(1)
    )
    char = result.scalar_one_or_none()
    if not char:
        return None
    return {
        "id": char.id,
        "name": char.name,
        "concept": char.concept,
        "personality": char.personality,
        "visual_description": char.visual_description,
        "base_image_prompt": char.base_image_prompt,
        "reference_image_url": char.reference_image_url,
        "bible": char.bible,
    }
