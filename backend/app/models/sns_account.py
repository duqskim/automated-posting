"""SNS 계정 모델 — 사용자별, 시장별 SNS 계정 관리"""
from sqlalchemy import String, Integer, ForeignKey, DateTime, Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class SNSAccount(Base, TimestampMixin):
    __tablename__ = "sns_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    market: Mapped[str] = mapped_column(String(5))  # kr, us, jp
    platform: Mapped[str] = mapped_column(String(50))  # instagram, youtube, linkedin, x, ...
    account_name: Mapped[str] = mapped_column(String(255))
    account_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # 인증 정보 (암호화 저장 필요)
    access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)

    is_active: Mapped[bool] = mapped_column(default=True)

    # Relationships
    user = relationship("User", back_populates="sns_accounts")
