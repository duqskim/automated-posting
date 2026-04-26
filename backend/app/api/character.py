"""
Character Design Studio API

5단계 파이프라인:
  1. audience   — 오디언스 리서치 (Gemini Pro)
  2. archetype  — 아키타입 3개 추천 (Claude)
  3. concepts   — 컨셉 3개 생성 (Claude)
  4. visual     — 이미지 생성 (Imagen 3)
  5. bible      — 캐릭터 바이블 작성 (Claude)

진행 상태는 SeriesCharacter.design_session (JSON)에 저장.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified
from loguru import logger

from app.models.base import get_db
from app.models.project import ContentSeries, SeriesCharacter
from app.dependencies import get_current_user
from app.models.user import User
from app.agents.character.audience_researcher import AudienceResearcher, audience_research_to_dict
from app.agents.character.archetype_advisor import ArchetypeAdvisor, archetype_advice_to_dict
from app.agents.character.concept_generator import ConceptGenerator, concept_options_to_dict
from app.agents.character.bible_writer import BibleWriter, bible_to_dict

router = APIRouter(prefix="/api/series/{series_id}/characters", tags=["character"])


# ── helpers ────────────────────────────────────────────────────────────────

async def _get_character(
    series_id: int,
    character_id: int,
    user: User,
    db: AsyncSession,
) -> SeriesCharacter:
    result = await db.execute(
        select(SeriesCharacter)
        .join(ContentSeries, SeriesCharacter.series_id == ContentSeries.id)
        .where(
            SeriesCharacter.id == character_id,
            SeriesCharacter.series_id == series_id,
            ContentSeries.user_id == user.id,
        )
    )
    char = result.scalar_one_or_none()
    if not char:
        raise HTTPException(404, "캐릭터를 찾을 수 없습니다")
    return char


async def _get_series(series_id: int, user: User, db: AsyncSession) -> ContentSeries:
    result = await db.execute(
        select(ContentSeries).where(
            ContentSeries.id == series_id,
            ContentSeries.user_id == user.id,
        )
    )
    s = result.scalar_one_or_none()
    if not s:
        raise HTTPException(404, "시리즈를 찾을 수 없습니다")
    return s


# ── GET session state ───────────────────────────────────────────────────────

@router.get("/{character_id}/design")
async def get_design_session(
    series_id: int,
    character_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    char = await _get_character(series_id, character_id, user, db)
    return {
        "id": char.id,
        "name": char.name,
        "status": char.status,
        "design_session": char.design_session or {"stage": "audience"},
        "bible": char.bible,
    }


# ── Stage 1: Audience Research ─────────────────────────────────────────────

@router.post("/{character_id}/design/audience")
async def run_audience_research(
    series_id: int,
    character_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    char = await _get_character(series_id, character_id, user, db)
    series = await _get_series(series_id, user, db)

    logger.info(f"[CharacterAPI] Stage 1: 오디언스 리서치 시작 — char={character_id}")

    researcher = AudienceResearcher()
    result = await researcher.research(
        series_name=series.name,
        series_category=series.category or "custom",
        market=series.market or "kr",
        language=series.language or "ko",
        description=series.description or "",
    )

    if not result:
        raise HTTPException(500, "오디언스 리서치 실패")

    research_dict = audience_research_to_dict(result)

    session = char.design_session or {}
    session["stage"] = "archetype"
    session["audience_research"] = research_dict
    char.design_session = session
    flag_modified(char, "design_session")

    db.add(char)
    await db.commit()
    await db.refresh(char)

    return {"stage": "archetype", "audience_research": research_dict}


# ── Stage 2: Archetype Advice ──────────────────────────────────────────────

@router.post("/{character_id}/design/archetypes")
async def run_archetype_advice(
    series_id: int,
    character_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    char = await _get_character(series_id, character_id, user, db)
    series = await _get_series(series_id, user, db)
    session = char.design_session or {}

    audience_research = session.get("audience_research")
    if not audience_research:
        raise HTTPException(400, "오디언스 리서치를 먼저 실행하세요")

    logger.info(f"[CharacterAPI] Stage 2: 아키타입 분석 시작 — char={character_id}")

    advisor = ArchetypeAdvisor()
    result = await advisor.advise(
        series_name=series.name,
        series_category=series.category or "custom",
        market=series.market or "kr",
        audience_research=audience_research,
    )

    if not result:
        raise HTTPException(500, "아키타입 분석 실패")

    advice_dict = archetype_advice_to_dict(result)

    session["stage"] = "archetype_select"
    session["archetypes"] = advice_dict
    char.design_session = session
    flag_modified(char, "design_session")

    db.add(char)
    await db.commit()
    await db.refresh(char)

    return {"stage": "archetype_select", "archetypes": advice_dict}


# ── Stage 2 선택: Archetype Select ─────────────────────────────────────────

class SelectArchetypeRequest(BaseModel):
    index: int  # 0, 1, 2


@router.post("/{character_id}/design/archetypes/select")
async def select_archetype(
    series_id: int,
    character_id: int,
    body: SelectArchetypeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    char = await _get_character(series_id, character_id, user, db)
    session = char.design_session or {}

    archetypes = session.get("archetypes", {})
    options = archetypes.get("options", [])
    if body.index >= len(options):
        raise HTTPException(400, "잘못된 인덱스")

    session["selected_archetype_index"] = body.index
    session["stage"] = "concepts"
    char.design_session = session
    flag_modified(char, "design_session")

    db.add(char)
    await db.commit()

    return {"stage": "concepts", "selected_index": body.index}


# ── Stage 3: Concept Generation ────────────────────────────────────────────

@router.post("/{character_id}/design/concepts")
async def run_concept_generation(
    series_id: int,
    character_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    char = await _get_character(series_id, character_id, user, db)
    series = await _get_series(series_id, user, db)
    session = char.design_session or {}

    audience_research = session.get("audience_research")
    archetypes = session.get("archetypes", {})
    archetype_index = session.get("selected_archetype_index", 0)
    archetype_options = archetypes.get("options", [])

    if not audience_research:
        raise HTTPException(400, "오디언스 리서치를 먼저 실행하세요")
    if not archetype_options:
        raise HTTPException(400, "아키타입 분석을 먼저 실행하세요")
    if archetype_index >= len(archetype_options):
        raise HTTPException(400, "아키타입을 선택하세요")

    selected_archetype = archetype_options[archetype_index]

    logger.info(f"[CharacterAPI] Stage 3: 컨셉 생성 시작 — char={character_id}")

    generator = ConceptGenerator()
    result = await generator.generate(
        series_name=series.name,
        series_category=series.category or "custom",
        market=series.market or "kr",
        language=series.language or "ko",
        selected_archetype=selected_archetype,
        audience_research=audience_research,
    )

    if not result:
        raise HTTPException(500, "컨셉 생성 실패")

    concepts_dict = concept_options_to_dict(result)

    session["stage"] = "concept_select"
    session["concepts"] = concepts_dict
    char.design_session = session
    flag_modified(char, "design_session")

    db.add(char)
    await db.commit()
    await db.refresh(char)

    return {"stage": "concept_select", "concepts": concepts_dict}


# ── Stage 3 선택: Concept Select ──────────────────────────────────────────

class SelectConceptRequest(BaseModel):
    index: int


@router.post("/{character_id}/design/concepts/select")
async def select_concept(
    series_id: int,
    character_id: int,
    body: SelectConceptRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    char = await _get_character(series_id, character_id, user, db)
    session = char.design_session or {}

    concepts = session.get("concepts", {})
    concept_list = concepts.get("concepts", [])
    if body.index >= len(concept_list):
        raise HTTPException(400, "잘못된 인덱스")

    selected = concept_list[body.index]
    session["selected_concept_index"] = body.index
    session["stage"] = "visual"

    # 이름 미리 업데이트
    char.name = selected.get("name", char.name)
    char.visual_description = selected.get("visual_direction", "")
    char.base_image_prompt = selected.get("image_prompt", "")
    char.design_session = session
    flag_modified(char, "design_session")

    db.add(char)
    await db.commit()

    return {"stage": "visual", "selected_index": body.index, "character_name": char.name}


# ── Stage 4: Visual — Imagen 4.0 직접 생성 ─────────────────────────────────

@router.post("/{character_id}/design/visual/generate")
async def generate_character_images(
    series_id: int,
    character_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """캐릭터 이미지를 Imagen 4.0으로 4장 직접 생성 → URL 저장"""
    import os, re
    from pathlib import Path
    from google import genai
    from google.genai import types

    char = await _get_character(series_id, character_id, user, db)
    session = char.design_session or {}

    # 컨셉에서 이미지 프롬프트 추출
    concepts = session.get("concepts", {})
    concept_index = session.get("selected_concept_index", 0)
    concept_list = concepts.get("concepts", [])

    base_prompt = char.base_image_prompt or ""
    if not base_prompt and concept_list and concept_index < len(concept_list):
        base_prompt = concept_list[concept_index].get("image_prompt", "")
    if not base_prompt:
        raise HTTPException(400, "이미지 프롬프트가 없습니다. 컨셉을 먼저 선택하세요.")

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(500, "GEMINI_API_KEY 미설정")

    # 출력 디렉토리
    char_img_dir = Path(__file__).parents[2] / "output" / "characters"
    char_img_dir.mkdir(parents=True, exist_ok=True)

    slug = re.sub(r"[^\w]", "_", char.name or f"char_{character_id}")[:20]
    style_suffix = (
        "Photorealistic concept art, high quality, 8K resolution, "
        "professional character design, dramatic lighting, no text, no watermarks"
    )
    final_prompt = f"{base_prompt}. {style_suffix}"

    logger.info(f"[CharacterAPI] Imagen 생성 시작 — char={character_id}, prompt={final_prompt[:80]}...")

    client = genai.Client(api_key=api_key)
    image_urls = []
    errors = []

    for i in range(4):
        try:
            response = client.models.generate_images(
                model="imagen-4.0-generate-001",
                prompt=final_prompt,
                config=types.GenerateImagesConfig(
                    aspect_ratio="1:1",
                    number_of_images=1,
                    person_generation="allow_adult",
                    output_mime_type="image/jpeg",
                    output_compression_quality=90,
                ),
            )
            if response.generated_images:
                img_bytes = response.generated_images[0].image.image_bytes
                if img_bytes:
                    filename = f"{slug}_c{character_id}_{i}.jpg"
                    (char_img_dir / filename).write_bytes(img_bytes)
                    image_urls.append(f"/api/characters/{filename}")
                    logger.info(f"  이미지 {i+1}/4 생성 완료")
        except Exception as e:
            errors.append(str(e))
            logger.warning(f"  이미지 {i+1}/4 실패: {e}")

    if not image_urls:
        raise HTTPException(500, f"이미지 생성 실패: {'; '.join(errors[:2])}")

    # 세션에 저장
    session["image_urls"] = image_urls
    session["stage"] = "image_select"
    char.design_session = session
    flag_modified(char, "design_session")
    db.add(char)
    await db.commit()

    return {"stage": "image_select", "image_urls": image_urls}


# ── Stage 4: Visual (image_urls 수동 입력 또는 외부 생성 후 저장) ──────────

class SaveImageUrlsRequest(BaseModel):
    image_urls: list[str]


@router.post("/{character_id}/design/visual")
async def save_image_urls(
    series_id: int,
    character_id: int,
    body: SaveImageUrlsRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """생성된 이미지 URL 저장 (Imagen 3 또는 Midjourney 결과)"""
    char = await _get_character(series_id, character_id, user, db)
    session = char.design_session or {}

    session["image_urls"] = body.image_urls
    # 이미지가 없으면 바로 bible 단계로
    session["stage"] = "image_select" if body.image_urls else "bible"
    char.design_session = session
    flag_modified(char, "design_session")

    db.add(char)
    await db.commit()

    return {"stage": session["stage"], "image_urls": body.image_urls}


class SelectImageRequest(BaseModel):
    index: int


@router.post("/{character_id}/design/visual/select")
async def select_image(
    series_id: int,
    character_id: int,
    body: SelectImageRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    char = await _get_character(series_id, character_id, user, db)
    session = char.design_session or {}

    image_urls = session.get("image_urls", [])
    if body.index >= len(image_urls):
        raise HTTPException(400, "잘못된 이미지 인덱스")

    char.reference_image_url = image_urls[body.index]
    session["selected_image_index"] = body.index
    session["stage"] = "bible"
    char.design_session = session
    flag_modified(char, "design_session")

    db.add(char)
    await db.commit()

    return {"stage": "bible", "selected_image_url": char.reference_image_url}


# ── Stage 5: Bible ─────────────────────────────────────────────────────────

@router.post("/{character_id}/design/bible")
async def run_bible(
    series_id: int,
    character_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    char = await _get_character(series_id, character_id, user, db)
    series = await _get_series(series_id, user, db)
    session = char.design_session or {}

    audience_research = session.get("audience_research")
    archetypes = session.get("archetypes", {})
    archetype_index = session.get("selected_archetype_index", 0)
    concepts = session.get("concepts", {})
    concept_index = session.get("selected_concept_index", 0)

    if not audience_research:
        raise HTTPException(400, "오디언스 리서치가 없습니다")

    archetype_options = archetypes.get("options", [])
    concept_list = concepts.get("concepts", [])

    if not archetype_options or archetype_index >= len(archetype_options):
        raise HTTPException(400, "아키타입 선택이 필요합니다")
    if not concept_list or concept_index >= len(concept_list):
        raise HTTPException(400, "컨셉 선택이 필요합니다")

    selected_archetype = archetype_options[archetype_index]
    selected_concept = concept_list[concept_index]

    logger.info(f"[CharacterAPI] Stage 5: 바이블 작성 시작 — char={character_id}")

    writer = BibleWriter()
    result = await writer.write(
        series_name=series.name,
        series_category=series.category or "custom",
        market=series.market or "kr",
        language=series.language or "ko",
        selected_concept=selected_concept,
        selected_archetype=selected_archetype,
        audience_research=audience_research,
        selected_image_url=char.reference_image_url or "",
    )

    if not result:
        raise HTTPException(500, "바이블 작성 실패")

    bible_dict = bible_to_dict(result)

    # 캐릭터 완성 처리
    char.bible = bible_dict
    char.name = result.name
    char.concept = result.tagline
    char.personality = ", ".join(result.core_personality[:3]) if result.core_personality else result.voice_description[:200]
    char.visual_description = result.visual_description
    char.base_image_prompt = result.base_image_prompt
    char.status = "active"

    session["stage"] = "done"
    char.design_session = session
    flag_modified(char, "design_session")

    db.add(char)
    await db.commit()
    await db.refresh(char)

    return {
        "stage": "done",
        "character": {
            "id": char.id,
            "name": char.name,
            "status": char.status,
            "bible": char.bible,
        }
    }
