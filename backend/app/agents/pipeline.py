"""
Pipeline Controller — 전체 파이프라인 오케스트레이션 (코드 기반)
실행 흐름:
  1. Researcher → 리서치
  2. Hooksmith → 훅 생성 (5개, 사용자 선택)
  3. Copywriter → 글쓰기
  4. Quality Gate → 검수
  5. Creative Director → 디자인 전략
  6. Art Director → 이미지 렌더링

단계별 실행 (step-by-step):
  run_research()  → stage_results["research"] 저장
  run_hooks()     → stage_results["hooks"] 저장
  run_write()     → stage_results["content"] 저장
  run_render()    → stage_results["images"] 저장
"""
import re
from pathlib import Path
from dataclasses import dataclass, field
from loguru import logger

from jinja2 import Environment, FileSystemLoader
from playwright.async_api import async_playwright

from app.config.market_profile import load_market_profile, MarketCode
from app.agents.research.agent import ResearcherAgent, ResearchResult, TopContent, WinningFormula
from app.agents.research.hooksmith import HooksmithAgent, HookResult, Hook, ThumbnailCopy
from app.agents.writer.copywriter import CopywriterAgent, ContentPlan, PlatformContent
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


# ─── 직렬화 헬퍼 ────────────────────────────────────────────

def research_to_dict(r: ResearchResult) -> dict:
    return {
        "topic": r.topic,
        "keywords": r.keywords,
        "top_content": [
            {
                "platform": c.platform,
                "title": c.title,
                "url": c.url,
                "engagement": c.engagement,
                "hook_used": c.hook_used,
                "format_notes": c.format_notes,
            }
            for c in r.top_content
        ],
        "winning_formula": {
            "hook_patterns": r.winning_formula.hook_patterns,
            "content_structure": r.winning_formula.content_structure,
            "avg_length": r.winning_formula.avg_length,
            "hashtag_strategy": r.winning_formula.hashtag_strategy,
            "thumbnail_style": r.winning_formula.thumbnail_style,
            "content_gaps": r.winning_formula.content_gaps,
        },
    }


def research_from_dict(d: dict) -> ResearchResult:
    return ResearchResult(
        topic=d["topic"],
        keywords=d.get("keywords", []),
        top_content=[
            TopContent(
                platform=c.get("platform", ""),
                title=c.get("title", ""),
                url=c.get("url"),
                engagement=c.get("engagement"),
                hook_used=c.get("hook_used"),
                format_notes=c.get("format_notes"),
            )
            for c in d.get("top_content", [])
        ],
        winning_formula=WinningFormula(
            hook_patterns=d.get("winning_formula", {}).get("hook_patterns", []),
            content_structure=d.get("winning_formula", {}).get("content_structure", ""),
            avg_length=d.get("winning_formula", {}).get("avg_length", ""),
            hashtag_strategy=d.get("winning_formula", {}).get("hashtag_strategy", ""),
            thumbnail_style=d.get("winning_formula", {}).get("thumbnail_style", ""),
            content_gaps=d.get("winning_formula", {}).get("content_gaps", []),
        ),
    )


def hooks_to_dict(r: HookResult) -> dict:
    return {
        "hooks": [
            {
                "text": h.text,
                "style": h.style,
                "score": h.score,
                "platform_fit": h.platform_fit,
            }
            for h in r.hooks
        ],
        "thumbnail_copies": [
            {
                "main_text": t.main_text,
                "sub_text": t.sub_text,
                "style_note": t.style_note,
            }
            for t in r.thumbnail_copies
        ],
        "recommended_hook_index": r.recommended_hook_index,
    }


def hooks_from_dict(d: dict) -> HookResult:
    return HookResult(
        hooks=[
            Hook(
                text=h["text"],
                style=h.get("style", "curiosity"),
                score=h.get("score", 0.0),
                platform_fit=h.get("platform_fit", []),
            )
            for h in d.get("hooks", [])
        ],
        thumbnail_copies=[
            ThumbnailCopy(
                main_text=t["main_text"],
                sub_text=t.get("sub_text"),
                style_note=t.get("style_note"),
            )
            for t in d.get("thumbnail_copies", [])
        ],
        recommended_hook_index=d.get("recommended_hook_index", 0),
    )


def content_plan_to_dict(c: ContentPlan) -> dict:
    return {
        "topic": c.topic,
        "market": c.market,
        "master_narrative": c.master_narrative,
        "thumbnail_text": c.thumbnail_text,
        "platform_contents": [
            {
                "platform": pc.platform,
                "hook": pc.hook,
                "body": pc.body,
                "caption": pc.caption,
                "hashtags": pc.hashtags,
                "cta": pc.cta,
                "metadata": pc.metadata,
            }
            for pc in c.platform_contents
        ],
    }


def content_plan_from_dict(d: dict) -> ContentPlan:
    return ContentPlan(
        topic=d["topic"],
        market=d.get("market", "kr"),
        master_narrative=d.get("master_narrative", ""),
        thumbnail_text=d.get("thumbnail_text", ""),
        platform_contents=[
            PlatformContent(
                platform=pc["platform"],
                hook=pc.get("hook", ""),
                body=pc.get("body", []),
                caption=pc.get("caption", ""),
                hashtags=pc.get("hashtags", []),
                cta=pc.get("cta", ""),
                metadata=pc.get("metadata", {}),
            )
            for pc in d.get("platform_contents", [])
        ],
    )


# ─── 파이프라인 컨트롤러 ────────────────────────────────────

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

    # ── 단계별 실행 메서드 ──

    async def run_research(self, topic: str) -> dict:
        """Stage 1: 리서치만 실행 → dict 반환"""
        logger.info(f"[Stage 1] 리서치 시작: '{topic}'")
        research = await self.researcher.research(topic)
        return research_to_dict(research)

    async def run_hooks(self, research_dict: dict) -> dict:
        """Stage 2: 훅 생성 → dict 반환"""
        logger.info("[Stage 2] 훅 생성 시작")
        research = research_from_dict(research_dict)
        hooks = await self.hooksmith.generate_hooks(research)
        return hooks_to_dict(hooks)

    async def run_write(
        self,
        research_dict: dict,
        hooks_dict: dict,
        selected_hook_index: int,
        target_platforms: list[str],
    ) -> dict:
        """Stage 3+4: 글쓰기 + 품질 검수 → dict 반환"""
        logger.info(f"[Stage 3] 글쓰기 시작 (훅 #{selected_hook_index})")
        research = research_from_dict(research_dict)
        hooks = hooks_from_dict(hooks_dict)

        # 선택된 훅으로 HookResult 재구성
        safe_idx = min(selected_hook_index, len(hooks.hooks) - 1)
        hooks.recommended_hook_index = safe_idx

        content = await self.copywriter.write(
            research=research,
            hook_result=hooks,
            target_platforms=target_platforms,
        )
        quality = self.quality_gate.evaluate(content)

        if not quality.passed:
            logger.info("Quality Gate 실패, 1회 재생성 시도...")
            content = await self.copywriter.write(
                research=research,
                hook_result=hooks,
                target_platforms=target_platforms,
            )
            quality = self.quality_gate.evaluate(content)

        return {
            "content": content_plan_to_dict(content),
            "quality_score": quality.score,
            "quality_passed": quality.passed,
        }

    async def run_render(
        self,
        content_dict: dict,
        topic: str,
        brand: dict | None = None,
        edited_slides: dict | None = None,  # {platform: [slide1, slide2, ...]}
    ) -> list[str]:
        """Stage 5+6: 디자인 + 렌더링 → 이미지 파일명 목록 반환"""
        logger.info("[Stage 5+6] 디자인 + 렌더링 시작")
        content_plan = content_plan_from_dict(content_dict)

        # 사용자 편집 슬라이드 적용
        if edited_slides:
            for pc in content_plan.platform_contents:
                if pc.platform in edited_slides:
                    pc.body = edited_slides[pc.platform]

        # 캐러셀 플랫폼 선택
        carousel_content = None
        for c in content_plan.platform_contents:
            if c.platform in ("instagram", "threads", "linkedin"):
                carousel_content = c
                break
        if not carousel_content:
            carousel_content = content_plan.platform_contents[0]

        cd = CreativeDirectorAgent(self.profile, brand=brand or {})
        design_plan = await cd.plan_design(carousel_content, content_plan)

        slug = re.sub(r"[^\w]", "_", topic)[:30]
        image_paths = await self._render_images(design_plan, slug)

        logger.info(f"  렌더링 완료: {len(image_paths)}장")
        return image_paths

    # ── 풀 파이프라인 (기존 호환) ──

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

        # Stage 5: Creative Director
        self.state.stage = "designing"
        try:
            cd = CreativeDirectorAgent(self.profile, brand={"handle": ""})
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

        # Stage 6: Art Director
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
