"""
automated-posting FastAPI 앱
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.models.base import engine, Base
from app.auth.router import router as auth_router
from app.api.accounts import router as accounts_router
from app.api.projects import router as projects_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 시작/종료 이벤트"""
    logger.info("automated-posting 서버 시작")
    # 개발 환경: 테이블 자동 생성 (프로덕션에서는 Alembic 사용)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("DB 테이블 준비 완료")
    yield
    logger.info("automated-posting 서버 종료")


app = FastAPI(
    title="automated-posting",
    description="SNS 자동 콘텐츠 제작/발행 시스템 — 멀티마켓(KR/US/JP)",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS (개발 환경)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Next.js dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(auth_router)
app.include_router(accounts_router)
app.include_router(projects_router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "automated-posting"}
