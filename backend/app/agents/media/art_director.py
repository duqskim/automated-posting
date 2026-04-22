"""
Art Director Agent — 이미지 + 썸네일 제작
역할: 캐러셀 이미지, 플랫폼별 썸네일, 브랜드 키트 적용
기반: shadow-meteorite slide_renderer.py (Playwright + Jinja2)
"""
import re
from pathlib import Path
from dataclasses import dataclass, field
from loguru import logger

from jinja2 import Environment, FileSystemLoader
from playwright.async_api import async_playwright

from app.config.market_profile import MarketProfile
from app.agents.writer.copywriter import ContentPlan, PlatformContent

TEMPLATE_DIR = Path(__file__).parent / "image_renderer" / "templates"
OUTPUT_DIR = Path(__file__).parents[3] / "output" / "images"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

_jinja_env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))

# 플랫폼별 이미지 사이즈
PLATFORM_SIZES = {
    "instagram": {"width": 1080, "height": 1080},
    "instagram_story": {"width": 1080, "height": 1920},
    "youtube": {"width": 1280, "height": 720},
    "youtube_shorts": {"width": 1080, "height": 1920},
    "tiktok": {"width": 1080, "height": 1920},
    "x": {"width": 1200, "height": 675},
    "linkedin": {"width": 1200, "height": 627},
    "facebook": {"width": 1200, "height": 630},
    "pinterest": {"width": 1000, "height": 1500},
    "threads": {"width": 1080, "height": 1080},
    "naver_blog": {"width": 960, "height": 540},
    "newsletter": {"width": 600, "height": 338},
}


@dataclass
class ImageAsset:
    platform: str
    asset_type: str  # "slide", "thumbnail", "og_image"
    file_path: Path
    width: int
    height: int
    slide_index: int | None = None


@dataclass
class ArtDirectorResult:
    slides: list[ImageAsset] = field(default_factory=list)
    thumbnails: list[ImageAsset] = field(default_factory=list)
    total_images: int = 0


class ArtDirectorAgent:
    """이미지 + 썸네일 제작 에이전트"""

    def __init__(self, market_profile: MarketProfile, brand: dict | None = None):
        self.profile = market_profile
        self.brand = brand or {}

    def _split_text(self, text: str) -> tuple[str, str]:
        """텍스트를 제목과 본문으로 분리"""
        lines = [ln.strip() for ln in text.strip().split("\n") if ln.strip()]
        if not lines:
            return "", ""
        if len(lines) == 1:
            pivot = min(40, len(lines[0]))
            return lines[0][:pivot], lines[0][pivot:].strip()
        if len(lines[0]) <= 30:
            return lines[0], " ".join(lines[1:])
        return lines[0][:30], " ".join([lines[0][30:]] + lines[1:])

    def _build_slide_contexts(self, content: PlatformContent) -> list[dict]:
        """플랫폼 콘텐츠 → 슬라이드별 렌더링 컨텍스트"""
        slides = content.body
        total = len(slides)
        contexts = []

        brand_colors = self.brand.get("colors", {})
        brand_handle = self.brand.get("handle", "")

        for i, slide_text in enumerate(slides):
            slide_num = i + 1
            title, detail = self._split_text(slide_text)

            if slide_num == 1:
                ctx = {
                    "slide_type": "hook",
                    "category": content.platform,
                    "main_text": content.hook if content.hook else title,
                    "sub_text": detail,
                }
            elif slide_num == total:
                ctx = {
                    "slide_type": "cta",
                    "category": content.platform,
                    "main_text": title or slide_text[:60],
                    "cta_text": content.cta or detail,
                }
            else:
                ctx = {
                    "slide_type": "content",
                    "category": content.platform,
                    "slide_index": slide_num,
                    "total_slides": total,
                    "point_num": slide_num - 1,
                    "content_title": title or slide_text[:40],
                    "detail_text": detail or "",
                }

            # 브랜드 정보 주입
            ctx["brand_handle"] = brand_handle
            ctx["brand_primary"] = brand_colors.get("primary", "#1a1a2e")
            ctx["brand_accent"] = brand_colors.get("accent", "#e94560")
            ctx["ai_disclosure"] = self.profile.content_rules.ai_disclosure

            contexts.append(ctx)

        return contexts

    async def render_carousel(
        self, content: PlatformContent, project_slug: str
    ) -> list[ImageAsset]:
        """캐러셀 슬라이드 이미지 렌더링"""
        if not content.body:
            return []

        size = PLATFORM_SIZES.get(content.platform, PLATFORM_SIZES["instagram"])
        contexts = self._build_slide_contexts(content)
        template = _jinja_env.get_template("slide.html")
        assets = []

        slug = re.sub(r"[^\w]", "_", project_slug)[:30]

        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page(viewport=size)

            for i, ctx in enumerate(contexts):
                html = template.render(**ctx)
                await page.set_content(html, wait_until="networkidle")

                filename = OUTPUT_DIR / f"{slug}_{content.platform}_slide{i+1:02d}.png"
                await page.screenshot(
                    path=str(filename),
                    clip={"x": 0, "y": 0, "width": size["width"], "height": size["height"]},
                )

                assets.append(ImageAsset(
                    platform=content.platform,
                    asset_type="slide",
                    file_path=filename,
                    width=size["width"],
                    height=size["height"],
                    slide_index=i + 1,
                ))

            await browser.close()

        logger.info(f"[{content.platform}] 캐러셀 {len(assets)}장 렌더링 완료")
        return assets

    async def render_thumbnail(
        self, content: PlatformContent, thumbnail_text: str, project_slug: str
    ) -> ImageAsset | None:
        """플랫폼별 썸네일 렌더링"""
        size = PLATFORM_SIZES.get(content.platform, PLATFORM_SIZES["youtube"])
        slug = re.sub(r"[^\w]", "_", project_slug)[:30]

        ctx = {
            "slide_type": "hook",
            "category": content.platform,
            "main_text": thumbnail_text,
            "sub_text": "",
            "brand_handle": self.brand.get("handle", ""),
            "brand_primary": self.brand.get("colors", {}).get("primary", "#1a1a2e"),
            "brand_accent": self.brand.get("colors", {}).get("accent", "#e94560"),
            "ai_disclosure": "",
        }

        template = _jinja_env.get_template("slide.html")

        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page(viewport=size)

            html = template.render(**ctx)
            await page.set_content(html, wait_until="networkidle")

            filename = OUTPUT_DIR / f"{slug}_{content.platform}_thumbnail.png"
            await page.screenshot(
                path=str(filename),
                clip={"x": 0, "y": 0, "width": size["width"], "height": size["height"]},
            )

            await browser.close()

        logger.info(f"[{content.platform}] 썸네일 렌더링 완료: {size['width']}x{size['height']}")
        return ImageAsset(
            platform=content.platform,
            asset_type="thumbnail",
            file_path=filename,
            width=size["width"],
            height=size["height"],
        )

    async def produce(self, content_plan: ContentPlan, project_slug: str) -> ArtDirectorResult:
        """전체 이미지 제작"""
        logger.info(f"=== Art Director: '{content_plan.topic}' 이미지 제작 시작 ===")

        result = ArtDirectorResult()

        for content in content_plan.platform_contents:
            # 캐러셀 형태 플랫폼만 슬라이드 렌더링
            carousel_platforms = ["instagram", "threads", "linkedin"]
            if content.platform in carousel_platforms and content.body:
                slides = await self.render_carousel(content, project_slug)
                result.slides.extend(slides)

            # 모든 플랫폼에 대해 썸네일 생성
            thumbnail = await self.render_thumbnail(
                content, content_plan.thumbnail_text, project_slug
            )
            if thumbnail:
                result.thumbnails.append(thumbnail)

        result.total_images = len(result.slides) + len(result.thumbnails)
        logger.info(f"Art Director 완료: 슬라이드 {len(result.slides)}장, "
                     f"썸네일 {len(result.thumbnails)}개, 총 {result.total_images}개")
        return result
