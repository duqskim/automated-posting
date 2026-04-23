"""파이프라인 실행 API — 결과를 DB에 저장하고 언제든 조회 가능"""
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


class ContentPreview(BaseModel):
    id: int | None = None
    platform: str
    hook: str
    body: list[str]
    caption: str
    hashtags: list[str]
    cta: str


class PipelineResponse(BaseModel):
    project_id: int
    stage: str
    score: float | None = None
    platforms_completed: int = 0
    platforms_total: int = 0
    error: str | None = None
    contents: list[ContentPreview] = []


@router.post("/{project_id}/run", response_model=PipelineResponse)
async def run_full_pipeline(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """파이프라인 실행 → 결과를 DB에 저장"""
    project = await _get_user_project(project_id, current_user.id, db)

    controller = PipelineController(project.market)
    state = await controller.run(
        topic=project.topic,
        target_platforms=project.target_platforms,
    )

    # 프로젝트 상태 업데이트
    project.status = state.stage
    await db.commit()

    contents = []
    if state.content and state.content.platform_contents:
        # 기존 콘텐츠 삭제 후 새로 저장
        await db.execute(
            delete(GeneratedContent).where(GeneratedContent.project_id == project_id)
        )

        score = int(state.quality.score) if state.quality else 0

        for c in state.content.platform_contents:
            record = GeneratedContent(
                project_id=project_id,
                platform=c.platform,
                hook=c.hook,
                body=c.body,
                caption=c.caption,
                hashtags=c.hashtags,
                cta=c.cta,
                quality_score=score,
            )
            db.add(record)

        await db.commit()

        # 저장된 데이터 조회
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
    """DB에 저장된 콘텐츠 조회 (파이프라인 재실행 없이)"""
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
