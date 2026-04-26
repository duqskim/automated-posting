"""프로젝트 + 시리즈 + 에피소드 + 캐릭터 모델"""
from sqlalchemy import String, ForeignKey, Text, JSON, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Project(Base, TimestampMixin):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    topic: Mapped[str] = mapped_column(String(500))
    market: Mapped[str] = mapped_column(String(10))  # kr, us, jp, global
    language: Mapped[str] = mapped_column(String(5))  # ko, en, ja

    status: Mapped[str] = mapped_column(
        String(20), default="created"
    )  # created, researching, writing, producing, reviewing, publishing, published, failed

    # 시리즈 연결
    series_id: Mapped[int | None] = mapped_column(ForeignKey("content_series.id"), nullable=True)
    series_episode: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 에피소드 번호

    # 사용자 설정
    target_platforms: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    preferences: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    brand_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("brand_profiles.id"), nullable=True
    )

    # 모드
    is_urgent: Mapped[bool] = mapped_column(default=False)

    # 단계별 파이프라인 결과
    stage_results: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Relationships
    user = relationship("User", back_populates="projects")
    series = relationship("ContentSeries", back_populates="projects")
    brand_profile = relationship("BrandProfile")
    episode = relationship("SeriesEpisode", back_populates="project", uselist=False)


class ContentSeries(Base, TimestampMixin):
    __tablename__ = "content_series"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 시장 & 언어
    market: Mapped[str] = mapped_column(String(10), default="kr")   # kr, us, jp, global
    language: Mapped[str] = mapped_column(String(5), default="ko")  # ko, en, ja

    # 시리즈 성격
    category: Mapped[str] = mapped_column(String(50), default="custom")
    # history | finance | kids | drama | science | custom
    visual_style: Mapped[str] = mapped_column(String(50), default="modern")
    # cinematic | modern | cartoon | documentary | minimal
    fact_mode: Mapped[str] = mapped_column(String(20), default="standard")
    # standard | strict | none

    # 기본 발행 플랫폼 (에피소드 기본값)
    target_platforms: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    current_episode: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships
    user = relationship("User", back_populates="series")
    projects = relationship("Project", back_populates="series")
    episodes = relationship(
        "SeriesEpisode", back_populates="series",
        order_by="SeriesEpisode.episode_number",
        cascade="all, delete-orphan",
    )
    characters = relationship(
        "SeriesCharacter", back_populates="series",
        cascade="all, delete-orphan",
    )


class SeriesEpisode(Base, TimestampMixin):
    """시리즈의 단일 에피소드 — 프로젝트 생성 전 기획 단계도 저장"""
    __tablename__ = "series_episodes"

    id: Mapped[int] = mapped_column(primary_key=True)
    series_id: Mapped[int] = mapped_column(ForeignKey("content_series.id", ondelete="CASCADE"))
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )

    episode_number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(500))          # "단군신화 — Korea's Origin Story"
    part_name: Mapped[str | None] = mapped_column(String(100), nullable=True)  # "Part 1: Origins"
    era_tag: Mapped[str | None] = mapped_column(String(100), nullable=True)    # "삼국시대", "고려"
    drama_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)  # "대장금", "주몽"
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)             # 기획 메모
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)           # 생성 후 3줄 요약 (다음 회차 context)

    status: Mapped[str] = mapped_column(String(20), default="draft")
    # draft | generating | ready | published

    # Relationships
    series = relationship("ContentSeries", back_populates="episodes")
    project = relationship("Project", back_populates="episode", foreign_keys=[project_id])


class SeriesCharacter(Base, TimestampMixin):
    """시리즈 전용 캐릭터 — 5단계 Character Design Studio 결과물"""
    __tablename__ = "series_characters"

    id: Mapped[int] = mapped_column(primary_key=True)
    series_id: Mapped[int] = mapped_column(ForeignKey("content_series.id", ondelete="CASCADE"))

    # 상태: draft (설계 중) | active (완성)
    status: Mapped[str] = mapped_column(String(20), default="draft")

    # ── 완성된 캐릭터 정보 ──────────────────────────────────
    name: Mapped[str] = mapped_column(String(100), default="")
    concept: Mapped[str | None] = mapped_column(Text, nullable=True)
    personality: Mapped[str | None] = mapped_column(Text, nullable=True)
    visual_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    base_image_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    voice_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reference_image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # ── Character Bible (완성 문서) ─────────────────────────
    bible: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # ── Design Session (파이프라인 진행 상태) ──────────────
    # {
    #   stage: "audience"|"archetype"|"concepts"|"visual"|"bible"|"done"
    #   audience_research: {...}
    #   selected_archetype_index: 0
    #   archetypes: [...]
    #   selected_concept_index: 0
    #   concepts: [...]
    #   image_urls: [...]
    #   selected_image_index: 0
    # }
    design_session: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Relationships
    series = relationship("ContentSeries", back_populates="characters")


class BrandProfile(Base, TimestampMixin):
    __tablename__ = "brand_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    market: Mapped[str] = mapped_column(String(10))
    name: Mapped[str] = mapped_column(String(100))

    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    colors: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    fonts: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    default_voice_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Relationships
    user = relationship("User", back_populates="brand_profiles")
