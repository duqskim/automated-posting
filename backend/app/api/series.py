"""Series API — 시리즈 + 에피소드 + 캐릭터 CRUD"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.models.base import get_db
from app.models.user import User
from app.models.project import ContentSeries, SeriesEpisode, SeriesCharacter, Project
from app.dependencies import get_current_user

router = APIRouter(prefix="/api/series", tags=["series"])


# ─── 스키마 ────────────────────────────────────────────────

class SeriesCreate(BaseModel):
    name: str
    description: str | None = None
    market: str = "global"
    language: str = "en"
    category: str = "custom"          # history | finance | kids | drama | science | custom
    visual_style: str = "modern"      # cinematic | modern | cartoon | documentary | minimal
    fact_mode: str = "standard"       # standard | strict | none
    target_platforms: list[str] | None = None


class SeriesUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    market: str | None = None
    language: str | None = None
    category: str | None = None
    visual_style: str | None = None
    fact_mode: str | None = None
    target_platforms: list[str] | None = None


class EpisodeCreate(BaseModel):
    episode_number: int
    title: str
    part_name: str | None = None
    era_tag: str | None = None
    drama_ref: str | None = None
    notes: str | None = None


class EpisodeBatchCreate(BaseModel):
    episodes: list[EpisodeCreate]


class EpisodeUpdate(BaseModel):
    title: str | None = None
    part_name: str | None = None
    era_tag: str | None = None
    drama_ref: str | None = None
    notes: str | None = None
    summary: str | None = None
    status: str | None = None


class CharacterCreate(BaseModel):
    name: str
    concept: str | None = None
    personality: str | None = None
    visual_description: str | None = None
    base_image_prompt: str | None = None
    voice_id: str | None = None


class CharacterUpdate(BaseModel):
    name: str | None = None
    concept: str | None = None
    personality: str | None = None
    visual_description: str | None = None
    base_image_prompt: str | None = None
    voice_id: str | None = None
    reference_image_url: str | None = None


# ─── 직렬화 헬퍼 ───────────────────────────────────────────

def _episode_dict(ep: SeriesEpisode) -> dict:
    return {
        "id": ep.id,
        "episode_number": ep.episode_number,
        "title": ep.title,
        "part_name": ep.part_name,
        "era_tag": ep.era_tag,
        "drama_ref": ep.drama_ref,
        "notes": ep.notes,
        "summary": ep.summary,
        "status": ep.status,
        "project_id": ep.project_id,
    }


def _character_dict(c: SeriesCharacter) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "status": getattr(c, "status", "draft"),
        "concept": c.concept,
        "personality": c.personality,
        "visual_description": c.visual_description,
        "base_image_prompt": c.base_image_prompt,
        "voice_id": c.voice_id,
        "reference_image_url": c.reference_image_url,
    }


def _series_dict(s: ContentSeries, include_episodes: bool = False) -> dict:
    d = {
        "id": s.id,
        "name": s.name,
        "description": s.description,
        "market": s.market,
        "language": s.language,
        "category": s.category,
        "visual_style": s.visual_style,
        "fact_mode": s.fact_mode,
        "target_platforms": s.target_platforms or [],
        "current_episode": s.current_episode,
        "episode_count": len(s.episodes) if s.episodes else 0,
        "characters": [_character_dict(c) for c in (s.characters or [])],
    }
    if include_episodes:
        d["episodes"] = [_episode_dict(ep) for ep in (s.episodes or [])]
    return d


# ─── 시리즈 CRUD ───────────────────────────────────────────

@router.get("")
async def list_series(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """사용자의 시리즈 목록"""
    result = await db.execute(
        select(ContentSeries)
        .where(ContentSeries.user_id == current_user.id)
        .options(selectinload(ContentSeries.episodes), selectinload(ContentSeries.characters))
        .order_by(ContentSeries.created_at.desc())
    )
    series_list = result.scalars().all()
    return [_series_dict(s) for s in series_list]


@router.post("", status_code=201)
async def create_series(
    body: SeriesCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """새 시리즈 생성"""
    s = ContentSeries(
        user_id=current_user.id,
        name=body.name,
        description=body.description,
        market=body.market,
        language=body.language,
        category=body.category,
        visual_style=body.visual_style,
        fact_mode=body.fact_mode,
        target_platforms=body.target_platforms,
    )
    db.add(s)
    await db.commit()
    # selectinload로 재조회 (refresh는 relationships를 로드하지 않음)
    result = await db.execute(
        select(ContentSeries)
        .where(ContentSeries.id == s.id)
        .options(selectinload(ContentSeries.episodes), selectinload(ContentSeries.characters))
    )
    s = result.scalar_one()
    return _series_dict(s)


@router.get("/{series_id}")
async def get_series(
    series_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """시리즈 상세 (에피소드 목록 포함)"""
    s = await _get_user_series(series_id, current_user.id, db)
    return _series_dict(s, include_episodes=True)


@router.patch("/{series_id}")
async def update_series(
    series_id: int,
    body: SeriesUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """시리즈 정보 수정"""
    s = await _get_user_series(series_id, current_user.id, db)
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(s, field, value)
    await db.commit()
    return _series_dict(s)


@router.delete("/{series_id}", status_code=204)
async def delete_series(
    series_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """시리즈 삭제 (에피소드 + 캐릭터 cascade)"""
    s = await _get_user_series(series_id, current_user.id, db)
    await db.delete(s)
    await db.commit()


# ─── 에피소드 CRUD ─────────────────────────────────────────

@router.post("/{series_id}/episodes", status_code=201)
async def add_episodes(
    series_id: int,
    body: EpisodeBatchCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """에피소드 추가 (단건 or 일괄 — 기획 단계, 프로젝트 생성 전)"""
    s = await _get_user_series(series_id, current_user.id, db)

    created = []
    for ep_data in body.episodes:
        ep = SeriesEpisode(
            series_id=s.id,
            episode_number=ep_data.episode_number,
            title=ep_data.title,
            part_name=ep_data.part_name,
            era_tag=ep_data.era_tag,
            drama_ref=ep_data.drama_ref,
            notes=ep_data.notes,
        )
        db.add(ep)
        created.append(ep)

    s.current_episode = max(s.current_episode, max(e.episode_number for e in created))
    await db.commit()
    for ep in created:
        await db.refresh(ep)
    return [_episode_dict(ep) for ep in created]


@router.patch("/{series_id}/episodes/{episode_id}")
async def update_episode(
    series_id: int,
    episode_id: int,
    body: EpisodeUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """에피소드 정보 수정"""
    ep = await _get_episode(series_id, episode_id, current_user.id, db)
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(ep, field, value)
    await db.commit()
    return _episode_dict(ep)


@router.delete("/{series_id}/episodes/{episode_id}", status_code=204)
async def delete_episode(
    series_id: int,
    episode_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """에피소드 삭제"""
    ep = await _get_episode(series_id, episode_id, current_user.id, db)
    await db.delete(ep)
    await db.commit()


@router.post("/{series_id}/episodes/{episode_id}/generate", status_code=201)
async def generate_episode(
    series_id: int,
    episode_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """에피소드 → 프로젝트 생성 (파이프라인 시작 준비)

    이전 회차 요약을 자동으로 stage_results에 주입해
    글쓰기 단계에서 series_context로 활용됩니다.
    """
    ep = await _get_episode(series_id, episode_id, current_user.id, db)
    s = await _get_user_series(series_id, current_user.id, db)

    if ep.project_id:
        raise HTTPException(status_code=400, detail="이미 프로젝트가 생성된 에피소드입니다")

    # 이전 회차 요약 수집 (series_context)
    prev_episodes = [
        e for e in (s.episodes or [])
        if e.episode_number < ep.episode_number and e.summary
    ]
    prev_episodes.sort(key=lambda e: e.episode_number)
    series_context = None
    if prev_episodes:
        lines = [
            f"EP{e.episode_number} ({e.era_tag or ''}): {e.summary}"
            for e in prev_episodes[-3:]  # 최근 3회차만
        ]
        series_context = "\n".join(lines)

    # 마켓 프로필에서 언어 결정
    from app.config.market_profile import load_market_profile
    try:
        profile = load_market_profile(s.market)
        language = profile.language
    except Exception:
        language = "en" if s.market in ("us", "global") else "ko"
    project = Project(
        user_id=current_user.id,
        topic=ep.title,
        market=s.market,
        language=language,
        series_id=series_id,
        series_episode=ep.episode_number,
        target_platforms=s.target_platforms,
        stage_results={"series_context": series_context} if series_context else None,
    )
    db.add(project)
    await db.flush()  # project.id 확보

    ep.project_id = project.id
    ep.status = "generating"
    await db.commit()

    return {
        "project_id": project.id,
        "episode_id": ep.id,
        "series_context_episodes": len(prev_episodes),
    }


# ─── 캐릭터 CRUD ───────────────────────────────────────────

@router.post("/{series_id}/characters", status_code=201)
async def create_character(
    series_id: int,
    body: CharacterCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """시리즈 캐릭터 생성"""
    s = await _get_user_series(series_id, current_user.id, db)
    c = SeriesCharacter(
        series_id=s.id,
        name=body.name,
        concept=body.concept,
        personality=body.personality,
        visual_description=body.visual_description,
        base_image_prompt=body.base_image_prompt,
        voice_id=body.voice_id,
    )
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return _character_dict(c)


@router.patch("/{series_id}/characters/{character_id}")
async def update_character(
    series_id: int,
    character_id: int,
    body: CharacterUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """캐릭터 정보 수정"""
    await _get_user_series(series_id, current_user.id, db)
    result = await db.execute(
        select(SeriesCharacter).where(
            SeriesCharacter.id == character_id,
            SeriesCharacter.series_id == series_id,
        )
    )
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="캐릭터를 찾을 수 없습니다")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(c, field, value)
    await db.commit()
    return _character_dict(c)


@router.delete("/{series_id}/characters/{character_id}", status_code=204)
async def delete_character(
    series_id: int,
    character_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """캐릭터 삭제"""
    await _get_user_series(series_id, current_user.id, db)
    result = await db.execute(
        select(SeriesCharacter).where(
            SeriesCharacter.id == character_id,
            SeriesCharacter.series_id == series_id,
        )
    )
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="캐릭터를 찾을 수 없습니다")
    await db.delete(c)
    await db.commit()


# ─── 헬퍼 ─────────────────────────────────────────────────

async def _get_user_series(series_id: int, user_id: int, db: AsyncSession) -> ContentSeries:
    result = await db.execute(
        select(ContentSeries)
        .where(ContentSeries.id == series_id, ContentSeries.user_id == user_id)
        .options(selectinload(ContentSeries.episodes), selectinload(ContentSeries.characters))
    )
    s = result.scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="시리즈를 찾을 수 없습니다")
    return s


async def _get_episode(
    series_id: int, episode_id: int, user_id: int, db: AsyncSession
) -> SeriesEpisode:
    await _get_user_series(series_id, user_id, db)
    result = await db.execute(
        select(SeriesEpisode).where(
            SeriesEpisode.id == episode_id,
            SeriesEpisode.series_id == series_id,
        )
    )
    ep = result.scalar_one_or_none()
    if not ep:
        raise HTTPException(status_code=404, detail="에피소드를 찾을 수 없습니다")
    return ep
