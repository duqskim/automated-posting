"""인증 서비스 — 회원가입, 로그인"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.auth.jwt import hash_password, verify_password, create_access_token


async def register_user(db: AsyncSession, email: str, password: str, name: str) -> User:
    """회원가입"""
    # 이메일 중복 확인
    result = await db.execute(select(User).where(User.email == email))
    if result.scalar_one_or_none():
        raise ValueError("이미 등록된 이메일입니다")

    user = User(
        email=email,
        password_hash=hash_password(password),
        name=name,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def authenticate_user(db: AsyncSession, email: str, password: str) -> dict | None:
    """로그인 — 성공 시 토큰 반환"""
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(password, user.password_hash):
        return None

    token = create_access_token(user.id, user.email)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
        },
    }
