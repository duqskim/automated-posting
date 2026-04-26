"""
automated-posting FastAPI 앱
"""
from contextlib import asynccontextmanager
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parents[1] / ".env")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from loguru import logger
from sqlalchemy import text

from app.models.base import engine, Base
import app.models  # noqa: F401 — 모든 모델 로드 (relationship resolve)
from app.auth.router import router as auth_router
from app.api.accounts import router as accounts_router
from app.api.projects import router as projects_router
from app.api.pipeline import router as pipeline_router
from app.api.series import router as series_router
from app.api.character import router as character_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 시작/종료 이벤트"""
    logger.info("automated-posting 서버 시작")
    # 개발 환경: 테이블 자동 생성 (프로덕션에서는 Alembic 사용)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        # ── projects 컬럼 마이그레이션 ─────────────────────────
        result = await conn.execute(text("PRAGMA table_info(projects)"))
        proj_cols = [row[1] for row in result.fetchall()]
        if "stage_results" not in proj_cols:
            await conn.execute(text("ALTER TABLE projects ADD COLUMN stage_results JSON"))

        # ── series_characters 컬럼 마이그레이션 ───────────────
        result = await conn.execute(text("PRAGMA table_info(series_characters)"))
        char_cols = [row[1] for row in result.fetchall()]
        for col, definition in [
            ("status",         "TEXT DEFAULT 'draft'"),
            ("bible",          "JSON"),
            ("design_session", "JSON"),
        ]:
            if col not in char_cols:
                await conn.execute(text(
                    f"ALTER TABLE series_characters ADD COLUMN {col} {definition}"
                ))

        # ── content_series 컬럼 마이그레이션 ──────────────────
        result = await conn.execute(text("PRAGMA table_info(content_series)"))
        series_cols = [row[1] for row in result.fetchall()]
        for col, definition in [
            ("language",        "TEXT DEFAULT 'ko'"),
            ("category",        "TEXT DEFAULT 'custom'"),
            ("visual_style",    "TEXT DEFAULT 'modern'"),
            ("fact_mode",       "TEXT DEFAULT 'standard'"),
            ("target_platforms","JSON"),
        ]:
            if col not in series_cols:
                await conn.execute(text(
                    f"ALTER TABLE content_series ADD COLUMN {col} {definition}"
                ))

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
app.include_router(pipeline_router)
app.include_router(series_router)
app.include_router(character_router)


# 이미지 파일 서빙 (레거시 run() 경로)
_output_dir = Path(__file__).parents[1] / "output" / "carousel"
_output_dir.mkdir(parents=True, exist_ok=True)
app.mount("/api/images", StaticFiles(directory=str(_output_dir)), name="images")

# 캐러셀 이미지 서빙 (ArtDirector → output/images/)
_carousel_dir = Path(__file__).parents[1] / "output" / "images"
_carousel_dir.mkdir(parents=True, exist_ok=True)
app.mount("/api/carousel", StaticFiles(directory=str(_carousel_dir)), name="carousel")

# 씬 이미지 파일 서빙 (Imagen 3 생성)
_scenes_dir = Path(__file__).parents[1] / "output" / "scenes"
_scenes_dir.mkdir(parents=True, exist_ok=True)
app.mount("/api/scenes", StaticFiles(directory=str(_scenes_dir)), name="scenes")

# 영상 파일 서빙
_video_dir = Path(__file__).parents[1] / "output" / "video"
_video_dir.mkdir(parents=True, exist_ok=True)
app.mount("/api/videos", StaticFiles(directory=str(_video_dir)), name="videos")


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "automated-posting"}
