"""
Pipeline Controller — 전체 파이프라인 오케스트레이션 (코드 기반)
실행 흐름:
  1. Researcher → 리서치
  2. Hooksmith → 훅 생성
  3. Copywriter → 글쓰기
  4. Quality Gate → 검수
  5. Creative Director → 디자인 전략
  6. Art Director → 이미지 렌더링
"""
import re
from pathlib import Path
from dataclasses import dataclass, field
from loguru import logger

from jinja2 import Environment, FileSystemLoader
from playwright.async_api import async_playwright

from app.config.market_profile import load_market_profile, MarketCode
from app.agents.research.agent import ResearcherAgent, ResearchResult
from app.agents.research.hooksmith import HooksmithAgent, HookResult
from app.agents.writer.copywriter import CopywriterAgent, ContentPlan
from app.agents.writer.quality_gate import QualityGate, QualityResult
from app.agents.media.creative_director import CreativeDirectorAgent, DesignPlan

TEMPLATE_DIR = Path(__file__).parent / "media" / "image_renderer" / "templates"
OUTPUT_DIR = Path(__file__).parents[2] / "output" / "carousel"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

_jinja_env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))


@dataclass
class PipelineState:
    stage: str = "idle"
    research: ResearchResult | None = None
    hooks: HookResult | None = None
    content: ContentPlan | None = None
    quality: QualityResult | None = None
    design_plan: DesignPlan | None = None
    image_paths: list[str] = field(default_factory=list)
    error: str | None = None


class PipelineController:
    def __init__(self, market: MarketCode):
        self.profile = load_market_profile(market)
        self.researcher = ResearcherAgent(self.profile)
        self.hooksmith = HooksmithAgent(self.profile)
        self.copywriter = CopywriterAgent(self.profile)
        self.quality_gate = QualityGate(self.profile)
        self.state = PipelineState()

    async def _render_images(self, design_plan: DesignPlan, project_slug: str) -> list[str]:
        """디자인 플랜 → 실제 PNG 이미지 렌더링"""
        image_paths = []
        slug = re.sub(r"[^\w]", "_", project_slug)[:30]

        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page(viewport=design_plan.canvas_size)

            for slide in design_plan.slides:
                template_file = f"{slide.template_name}.html"
                try:
                    template = _jinja_env.get_template(template_file)
                except Exception:
                    template = _jinja_env.get_template("editorial.html")

                html = template.render(**slide.template_data)
                await page.set_content(html, wait_until="networkidle")
                await page.wait_for_timeout(1000)

                filename = OUTPUT_DIR / f"{slug}_slide_{slide.slide_index:02d}.png"
                await page.screenshot(
                    path=str(filename),
                    clip={"x": 0, "y": 0, **design_plan.canvas_size},
                )
                image_paths.append(str(filename))
                logger.info(f"  슬라이드 {slide.slide_index}/{len(design_plan.slides)} 렌더링 완료")

            await browser.close()

        return image_paths

    async def run(
        self,
        topic: str,
        target_platforms: list[str] | None = None,
        series_context: str | None = None,
    ) -> PipelineState:
        platforms = target_platforms or self.profile.active_platforms
        logger.info(f"=== Pipeline: '{topic}' → {self.profile.display_name} ({', '.join(platforms)}) ===")

        # Stage 1: Research
        self.state.stage = "researching"
        try:
            self.state.research = await self.researcher.research(topic)
        except Exception as e:
            self.state.stage = "failed"
            self.state.error = f"리서치 실패: {e}"
            logger.error(self.state.error)
            return self.state

        # Stage 2: Hooksmith
        self.state.stage = "hooking"
        try:
            self.state.hooks = await self.hooksmith.generate_hooks(self.state.research)
        except Exception as e:
            self.state.stage = "failed"
            self.state.error = f"훅 생성 실패: {e}"
            logger.error(self.state.error)
            return self.state

        # Stage 3: Copywriter
        self.state.stage = "writing"
        try:
            self.state.content = await self.copywriter.write(
                research=self.state.research,
                hook_result=self.state.hooks,
                target_platforms=platforms,
                series_context=series_context,
            )
        except Exception as e:
            self.state.stage = "failed"
            self.state.error = f"콘텐츠 생성 실패: {e}"
            logger.error(self.state.error)
            return self.state

        # Stage 4: Quality Gate
        self.state.stage = "quality_check"
        self.state.quality = self.quality_gate.evaluate(self.state.content)

        if not self.state.quality.passed:
            logger.info("Quality Gate 실패, 1회 재생성 시도...")
            self.state.content = await self.copywriter.write(
                research=self.state.research,
                hook_result=self.state.hooks,
                target_platforms=platforms,
                series_context=series_context,
            )
            self.state.quality = self.quality_gate.evaluate(self.state.content)

        if not self.state.quality.passed:
            self.state.stage = "failed"
            self.state.error = f"Quality Gate 2회 실패 (점수: {self.state.quality.score}/100)"
            logger.warning(f"=== Pipeline: {self.state.error} ===")
            return self.state

        # Stage 5: Creative Director → 디자인 전략
        self.state.stage = "designing"
        try:
            cd = CreativeDirectorAgent(self.profile, brand={"handle": ""})
            # 캐러셀 형태 플랫폼의 첫 번째 콘텐츠로 디자인
            carousel_content = None
            for c in self.state.content.platform_contents:
                if c.platform in ("instagram", "threads", "linkedin"):
                    carousel_content = c
                    break
            if not carousel_content:
                carousel_content = self.state.content.platform_contents[0]

            self.state.design_plan = await cd.plan_design(carousel_content, self.state.content)
        except Exception as e:
            logger.warning(f"디자인 전략 실패 (텍스트만 사용): {e}")

        # Stage 6: Art Director → 이미지 렌더링
        self.state.stage = "rendering"
        if self.state.design_plan:
            try:
                slug = re.sub(r"[^\w]", "_", topic)[:30]
                self.state.image_paths = await self._render_images(self.state.design_plan, slug)
                logger.info(f"캐러셀 이미지 {len(self.state.image_paths)}장 렌더링 완료")
            except Exception as e:
                logger.warning(f"이미지 렌더링 실패: {e}")

        self.state.stage = "passed"
        logger.info(f"=== Pipeline 완료: PASS (점수: {self.state.quality.score}/100, "
                     f"이미지: {len(self.state.image_paths)}장) ===")
        return self.state
