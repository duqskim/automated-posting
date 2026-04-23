"""생성된 콘텐츠 저장 모델"""
from sqlalchemy import String, Integer, ForeignKey, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class GeneratedContent(Base, TimestampMixin):
    __tablename__ = "generated_contents"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    platform: Mapped[str] = mapped_column(String(50))
    hook: Mapped[str] = mapped_column(Text)
    body: Mapped[list] = mapped_column(JSON)  # 슬라이드/트윗 배열
    caption: Mapped[str] = mapped_column(Text, default="")
    hashtags: Mapped[list] = mapped_column(JSON, default=[])
    cta: Mapped[str] = mapped_column(Text, default="")
    quality_score: Mapped[int] = mapped_column(Integer, default=0)
