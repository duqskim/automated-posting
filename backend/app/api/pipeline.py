"""파이프라인 실행 API"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.models.base import get_db
from app.models.project import Project
from app.models.user import User
from app.dependencies import get_current_user
from app.agents.pipeline import PipelineController

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])


class PipelineResponse(BaseModel):
    project_id: int
    stage: str
    score: float | None = None
    platforms_completed: int = 0
    platforms_total: int = 0
    error: str | None = None


class ResearchPreview(BaseModel):
    keywords: list[str]
    top_content_count: int
    hook_patterns: list[str]
    content_gaps: list[str]


class HookPreview(BaseModel):
    hooks: list[dict]
    thumbnail_copies: list[dict]
    recommended_index: int


class ContentPreview(BaseModel):
    platform: str
    hook: str
    body_parts: int
    caption_preview: str
    hashtags: list[str]


@router.post("/{project_id}/research", response_model=ResearchPreview)
async def run_research(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Stage 1: 리서치 실행"""
    project = await _get_user_project(project_id, current_user.id, db)

    controller = PipelineController(project.market)
    research = await controller.researcher.research(project.topic)

    # 프로젝트 상태 업데이트
    project.status = "researching"
    await db.commit()

    return ResearchPreview(
        keywords=research.keywords[:15],
        top_content_count=len(research.top_content),
        hook_patterns=research.winning_formula.hook_patterns,
        content_gaps=research.winning_formula.content_gaps,
    )


@router.post("/{project_id}/run", response_model=PipelineResponse)
async def run_full_pipeline(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """전체 파이프라인 실행 (리서치 → 훅 → 콘텐츠 → 검증)"""
    project = await _get_user_project(project_id, current_user.id, db)

    controller = PipelineController(project.market)
    state = await controller.run(
        topic=project.topic,
        target_platforms=project.target_platforms,
    )

    # 프로젝트 상태 업데이트
    project.status = state.stage
    await db.commit()

    return PipelineResponse(
        project_id=project.id,
        stage=state.stage,
        score=state.quality.score if state.quality else None,
        platforms_completed=len(state.content.platform_contents) if state.content else 0,
        platforms_total=len(project.target_platforms or []),
        error=state.error,
    )


@router.get("/{project_id}/preview", response_model=list[ContentPreview])
async def preview_content(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """생성된 콘텐츠 미리보기"""
    # 실제로는 DB에서 저장된 콘텐츠를 가져와야 하지만,
    # 현재는 파이프라인 재실행으로 대체
    project = await _get_user_project(project_id, current_user.id, db)

    controller = PipelineController(project.market)
    state = await controller.run(
        topic=project.topic,
        target_platforms=project.target_platforms,
    )

    if not state.content:
        raise HTTPException(status_code=500, detail=state.error or "콘텐츠 생성 실패")

    return [
        ContentPreview(
            platform=c.platform,
            hook=c.hook,
            body_parts=len(c.body),
            caption_preview=c.caption[:100] + "..." if len(c.caption) > 100 else c.caption,
            hashtags=c.hashtags,
        )
        for c in state.content.platform_contents
    ]


async def _get_user_project(project_id: int, user_id: int, db: AsyncSession) -> Project:
    """사용자의 프로젝트 조회 (권한 확인)"""
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
