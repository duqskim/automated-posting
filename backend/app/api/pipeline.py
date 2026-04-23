"""파이프라인 API — 풀 실행 + 단계별 실행 + DB 저장"""
from fastapi import APIRouter, Depends, HTTPException
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
    current_step: str  # idle / research_done / hooks_done / write_done / render_done
    research: dict | None = None
    hooks: dict | None = None
    selected_hook_index: int = 0
    content: dict | None = None
    image_urls: list[str] = []
    quality_score: float | None = None


class SelectHookRequest(BaseModel):
    selected_hook_index: int


class SaveSlidesRequest(BaseModel):
    platform: str
    slides: list[str]


# ─── 단계 판별 ──────────────────────────────────────────────

def _current_step(stage_results: dict | None) -> str:
    if not stage_results:
        return "idle"
    if stage_results.get("images"):
        return "render_done"
    if stage_results.get("content"):
        return "write_done"
    if stage_results.get("hooks"):
        return "hooks_done"
    if stage_results.get("research"):
        return "research_done"
    return "idle"


def _image_urls_from_paths(paths: list[str]) -> list[str]:
    return [f"/api/images/{p.split('/')[-1]}" for p in paths]


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
    return StageStateResponse(
        current_step=_current_step(sr),
        research=sr.get("research"),
        hooks=sr.get("hooks"),
        selected_hook_index=sr.get("selected_hook_index", 0),
        content=sr.get("content"),
        image_urls=_image_urls_from_paths(images),
        quality_score=sr.get("quality_score"),
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


@router.post("/{project_id}/stage/write")
async def run_stage_write(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Stage 3+4: 글쓰기 + 품질 검수 → 결과 저장"""
    project = await _get_user_project(project_id, current_user.id, db)
    sr = project.stage_results or {}

    if not sr.get("hooks"):
        raise HTTPException(status_code=400, detail="훅 생성을 먼저 실행해주세요")

    controller = PipelineController(project.market)
    platforms = project.target_platforms or controller.profile.active_platforms

    try:
        result = await controller.run_write(
            research_dict=sr["research"],
            hooks_dict=sr["hooks"],
            selected_hook_index=sr.get("selected_hook_index", 0),
            target_platforms=list(platforms) if isinstance(platforms, (list, dict)) else platforms,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"글쓰기 실패: {e}")

    sr = dict(sr)
    sr["content"] = result["content"]
    sr["quality_score"] = result["quality_score"]
    sr.pop("images", None)
    project.stage_results = sr
    project.status = "writing"
    await db.commit()

    return {
        "step": "write_done",
        "content": result["content"],
        "quality_score": result["quality_score"],
        "quality_passed": result["quality_passed"],
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


@router.post("/{project_id}/stage/render")
async def run_stage_render(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Stage 5+6: 디자인 + 이미지 렌더링 → 결과 저장 + GeneratedContent DB 저장"""
    project = await _get_user_project(project_id, current_user.id, db)
    sr = project.stage_results or {}

    if not sr.get("content"):
        raise HTTPException(status_code=400, detail="글쓰기를 먼저 실행해주세요")

    controller = PipelineController(project.market)

    try:
        image_paths = await controller.run_render(
            content_dict=sr["content"],
            topic=project.topic,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"렌더링 실패: {e}")

    # stage_results에 이미지 경로 저장
    sr = dict(sr)
    sr["images"] = image_paths
    project.stage_results = sr
    project.status = "passed"
    await db.commit()

    # GeneratedContent DB 저장 (기존 방식과 동일)
    from app.agents.pipeline import content_plan_from_dict
    content_plan = content_plan_from_dict(sr["content"])
    image_filenames = [p.split("/")[-1] for p in image_paths]

    await db.execute(
        delete(GeneratedContent).where(GeneratedContent.project_id == project_id)
    )

    score = int(sr.get("quality_score", 0))
    for pc in content_plan.platform_contents:
        platform_images = []
        if pc.platform in ("instagram", "threads", "linkedin"):
            platform_images = [f"/api/images/{f}" for f in image_filenames]

        record = GeneratedContent(
            project_id=project_id,
            platform=pc.platform,
            hook=pc.hook,
            body=pc.body,
            caption=pc.caption,
            hashtags=pc.hashtags,
            cta=pc.cta,
            quality_score=score,
            image_paths=platform_images,
        )
        db.add(record)

    await db.commit()

    image_urls = [f"/api/images/{f}" for f in image_filenames]
    return {
        "step": "render_done",
        "image_urls": image_urls,
        "images_count": len(image_paths),
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
