"""프로젝트 API — 주제 입력, 파이프라인 관리"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.models.base import get_db
from app.models.project import Project
from app.models.user import User
from app.dependencies import get_current_user
from app.config.market_profile import load_market_profile, MarketCode

router = APIRouter(prefix="/api/projects", tags=["projects"])


class ProjectCreate(BaseModel):
    topic: str
    market: MarketCode  # kr, us, jp
    target_platforms: list[str] | None = None  # None이면 market의 primary+secondary 사용
    is_urgent: bool = False
    series_id: int | None = None
    brand_profile_id: int | None = None
    preferences: dict | None = None


class ProjectResponse(BaseModel):
    id: int
    topic: str
    market: str
    language: str
    status: str
    target_platforms: list[str] | None
    is_urgent: bool
    series_id: int | None
    series_episode: int | None


class MarketInfo(BaseModel):
    code: str
    display_name: str
    language: str
    primary_platforms: list[str]
    secondary_platforms: list[str]


@router.get("/markets", response_model=list[MarketInfo])
async def list_markets():
    """사용 가능한 시장 목록 + 플랫폼 정보"""
    markets = []
    for code in ["kr", "us", "jp"]:
        profile = load_market_profile(code)
        markets.append(MarketInfo(
            code=profile.market,
            display_name=profile.display_name,
            language=profile.language,
            primary_platforms=profile.platforms.get("primary", []),
            secondary_platforms=profile.platforms.get("secondary", []),
        ))
    return markets


@router.post("", response_model=ProjectResponse, status_code=201)
async def create_project(
    req: ProjectCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """프로젝트 생성 (주제 + 시장 선택)"""
    profile = load_market_profile(req.market)

    # 타겟 플랫폼: 지정 없으면 시장의 active_platforms 사용
    target_platforms = req.target_platforms or profile.active_platforms

    project = Project(
        user_id=current_user.id,
        topic=req.topic,
        market=req.market,
        language=profile.language,
        target_platforms=target_platforms,
        is_urgent=req.is_urgent,
        series_id=req.series_id,
        brand_profile_id=req.brand_profile_id,
        preferences=req.preferences,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)

    return ProjectResponse(
        id=project.id,
        topic=project.topic,
        market=project.market,
        language=project.language,
        status=project.status,
        target_platforms=project.target_platforms,
        is_urgent=project.is_urgent,
        series_id=project.series_id,
        series_episode=project.series_episode,
    )


@router.get("", response_model=list[ProjectResponse])
async def list_projects(
    market: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """프로젝트 목록"""
    query = select(Project).where(Project.user_id == current_user.id)
    if market:
        query = query.where(Project.market == market)
    result = await db.execute(query.order_by(Project.created_at.desc()))
    projects = result.scalars().all()
    return [
        ProjectResponse(
            id=p.id,
            topic=p.topic,
            market=p.market,
            language=p.language,
            status=p.status,
            target_platforms=p.target_platforms,
            is_urgent=p.is_urgent,
            series_id=p.series_id,
            series_episode=p.series_episode,
        )
        for p in projects
    ]


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """프로젝트 상세"""
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.user_id == current_user.id,
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다")

    return ProjectResponse(
        id=project.id,
        topic=project.topic,
        market=project.market,
        language=project.language,
        status=project.status,
        target_platforms=project.target_platforms,
        is_urgent=project.is_urgent,
        series_id=project.series_id,
        series_episode=project.series_episode,
    )
