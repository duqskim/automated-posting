"""파이프라인 API — 풀 실행 + 단계별 실행 + DB 저장"""
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.models.base import get_db
from app.models.project import Project
from app.models.content import GeneratedContent
from app.models.user import User
from app.dependencies import get_current_user
from app.agents.pipeline import PipelineController

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
    thumbnail_url: str | None = None
    quality_score: float | None = None
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
    if stage_results.get("video"):
        return "video_done"
    if stage_results.get("images"):
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

    return StageStateResponse(
        current_step=_current_step(sr),
        research=sr.get("research"),
        hooks=sr.get("hooks"),
        selected_hook_index=sr.get("selected_hook_index", 0),
        content=sr.get("content"),
        image_urls=_image_urls_from_paths(images, render_type),
        thumbnail_url=sr.get("thumbnail_url"),
        quality_score=sr.get("quality_score"),
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

    try:
        result = await controller.run_write(
            research_dict=sr["research"],
            hooks_dict=sr["hooks"],
            selected_hook_index=sr.get("selected_hook_index", 0),
            target_platforms=list(platforms) if isinstance(platforms, (list, dict)) else platforms,
            fact_corrections=fact_corrections,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"글쓰기 실패: {e}")

    sr = dict(sr)
    sr["content"] = result["content"]
    sr["quality_score"] = result["quality_score"]
    sr["fact_check"] = result.get("fact_check")
    sr.pop("images", None)
    project.stage_results = sr
    project.status = "writing"
    await db.commit()

    return {
        "step": "write_done",
        "content": result["content"],
        "quality_score": result["quality_score"],
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


class RenderRequest(BaseModel):
    platform: str = "youtube"  # 어떤 플랫폼용 씬 이미지를 만들지


@router.post("/{project_id}/stage/render")
async def run_stage_render(
    project_id: int,
    body: RenderRequest = RenderRequest(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Stage 4: Imagen 3으로 슬라이드별 씬 이미지 생성"""
    project = await _get_user_project(project_id, current_user.id, db)
    sr = project.stage_results or {}

    if not sr.get("content"):
        raise HTTPException(status_code=400, detail="글쓰기를 먼저 실행해주세요")

    controller = PipelineController(project.market)

    try:
        render_result = await controller.run_render(
            content_dict=sr["content"],
            topic=project.topic,
            platform=body.platform,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"이미지 생성 실패: {e}")

    image_paths = render_result["image_paths"]
    render_type = render_result["render_type"]  # "carousel" | "scene"
    thumbnail_path = render_result.get("thumbnail_path")

    thumbnail_url = None

    if render_type == "carousel" and thumbnail_path:
        # ArtDirector가 이미 썸네일 생성 완료
        thumbnail_url = f"/api/carousel/{Path(thumbnail_path).name}"
    elif render_type == "scene":
        # Imagen으로 YouTube 썸네일 별도 생성
        thumbnail_text = sr["content"].get("thumbnail_text", "")
        if thumbnail_text:
            try:
                from app.agents.media.image_generation import generate_scene_image, SCENES_DIR
                import re as _re
                slug = _re.sub(r"[^\w]", "_", project.topic, flags=_re.ASCII)[:25]
                thumb_path = SCENES_DIR / f"{slug}_thumbnail.jpg"
                thumb_prompt = (
                    f"{thumbnail_text}. YouTube thumbnail style, bold visual impact, "
                    "dramatic lighting, eye-catching composition, 16:9"
                )
                result = await generate_scene_image(
                    slide_text=thumbnail_text,
                    image_prompt=thumb_prompt,
                    output_path=thumb_path,
                    topic=project.topic,
                    language=controller.profile.language,
                    aspect_ratio="16:9",
                )
                if result:
                    thumbnail_url = f"/api/scenes/{thumb_path.name}"
            except Exception as e:
                logger.warning(f"썸네일 생성 실패 (무시): {e}")

    sr = dict(sr)
    sr["images"] = image_paths
    sr["images_platform"] = body.platform
    sr["images_render_type"] = render_type
    if thumbnail_url:
        sr["thumbnail_url"] = thumbnail_url
    # 씬 플랫폼 전용: 메타데이터 + 비디오 플랜 + 썸네일 스펙 저장
    if render_result.get("metadata"):
        sr["metadata"] = render_result["metadata"]
    if render_result.get("video_plan"):
        sr["video_plan"] = render_result["video_plan"]
    if render_result.get("thumbnail_spec"):
        sr["thumbnail_spec"] = render_result["thumbnail_spec"]
    project.stage_results = sr
    project.status = "passed"
    await db.commit()

    image_urls = _image_urls_from_paths(image_paths, render_type)
    return {
        "step": "render_done",
        "platform": body.platform,
        "render_type": render_type,
        "image_urls": image_urls,
        "images_count": len(image_paths),
        "thumbnail_url": thumbnail_url,
        "metadata": render_result.get("metadata"),
        "thumbnail_spec": render_result.get("thumbnail_spec"),
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
    import re

    project = await _get_user_project(project_id, current_user.id, db)
    sr = project.stage_results or {}

    if not sr.get("content"):
        raise HTTPException(status_code=400, detail="글쓰기를 먼저 실행해주세요")

    from app.agents.pipeline import content_plan_from_dict
    content_plan = content_plan_from_dict(sr["content"])

    target = next((pc for pc in content_plan.platform_contents if pc.platform == body.platform), None)
    if not target:
        target = content_plan.platform_contents[0]

    if slide_index >= len(target.body):
        raise HTTPException(status_code=400, detail="슬라이드 인덱스 초과")

    slug = re.sub(r"[^\w]", "_", project.topic)[:25]
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
    tts_provider: str = "none"  # "none" | "gemini" | "elevenlabs"


@router.post("/{project_id}/stage/video")
async def run_stage_video(
    project_id: int,
    body: VideoRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Stage 7: 영상 제작 (Veo 씬 클립 + TTS + moviepy 조립)"""
    project = await _get_user_project(project_id, current_user.id, db)
    sr = project.stage_results or {}

    if not sr.get("content"):
        raise HTTPException(status_code=400, detail="글쓰기를 먼저 실행해주세요")
    if not sr.get("images"):
        raise HTTPException(status_code=400, detail="씬 이미지를 먼저 생성해주세요 (Step 4)")

    controller = PipelineController(project.market)

    try:
        result = await controller.run_video(
            content_dict=sr["content"],
            topic=project.topic,
            platform=body.platform,
            scene_image_paths=sr.get("images", []),
            tts_provider=body.tts_provider,
            video_plan_dict=sr.get("video_plan"),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"영상 제작 실패: {e}")

    def _video_url(path: str | None) -> str | None:
        return f"/api/videos/{Path(path).name}" if path else None

    # stage_results에 영상 결과 저장
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
