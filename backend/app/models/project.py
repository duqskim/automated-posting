"""프로젝트 모델 — 주제 하나 = 프로젝트 하나"""
from sqlalchemy import String, Integer, ForeignKey, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Project(Base, TimestampMixin):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    topic: Mapped[str] = mapped_column(String(500))
    market: Mapped[str] = mapped_column(String(5))  # kr, us, jp
    language: Mapped[str] = mapped_column(String(5))  # ko, en, ja

    status: Mapped[str] = mapped_column(
        String(20), default="created"
    )  # created, researching, writing, producing, reviewing, publishing, published, failed

    # 시리즈 관리
    series_id: Mapped[int | None] = mapped_column(ForeignKey("content_series.id"), nullable=True)
    series_episode: Mapped[int | None] = mapped_column(nullable=True)

    # 사용자 설정
    target_platforms: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # 발행 대상 플랫폼
    preferences: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # 톤, 스타일 오버라이드
    brand_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("brand_profiles.id"), nullable=True
    )

    # 모드
    is_urgent: Mapped[bool] = mapped_column(default=False)  # 긴급 모드 (리뷰 스킵)

    # Relationships
    user = relationship("User", back_populates="projects")
    series = relationship("ContentSeries", back_populates="projects")
    brand_profile = relationship("BrandProfile")


class ContentSeries(Base, TimestampMixin):
    __tablename__ = "content_series"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255))
    market: Mapped[str] = mapped_column(String(5))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_episode: Mapped[int] = mapped_column(default=0)

    # Relationships
    projects = relationship("Project", back_populates="series")


class BrandProfile(Base, TimestampMixin):
    __tablename__ = "brand_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    market: Mapped[str] = mapped_column(String(5))
    name: Mapped[str] = mapped_column(String(100))

    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    colors: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # primary, secondary, accent
    fonts: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    default_voice_id: Mapped[str | None] = mapped_column(String(100), nullable=True)  # ElevenLabs

    # Relationships
    user = relationship("User", back_populates="brand_profiles")
