"""사용자 모델"""
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(default=True)

    # Relationships
    sns_accounts = relationship("SNSAccount", back_populates="user", lazy="selectin")
    projects = relationship("Project", back_populates="user", lazy="selectin")
    brand_profiles = relationship("BrandProfile", back_populates="user", lazy="selectin")
