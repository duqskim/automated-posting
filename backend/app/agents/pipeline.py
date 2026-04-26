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
                "image_prompts": pc.image_prompts,
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
                image_prompts=pc.get("image_prompts", []),
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
        slug = re.sub(r"[^\w]", "_", project_slug, flags=re.ASCII)[:30]

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
        fact_corrections: list[dict] | None = None,
    ) -> dict:
        """Stage 3+4: 글쓰기 + 품질 검수 → dict 반환"""
        logger.info(f"[Stage 3] 글쓰기 시작 (훅 #{selected_hook_index})")
        research = research_from_dict(research_dict)
        hooks = hooks_from_dict(hooks_dict)

        # 선택된 훅으로 HookResult 재구성
        safe_idx = min(selected_hook_index, len(hooks.hooks) - 1)
        hooks.recommended_hook_index = safe_idx

        if fact_corrections:
            logger.info(f"  [팩트 수정 재작성] 오류 {len(fact_corrections)}개 반영")

        content = await self.copywriter.write(
            research=research,
            hook_result=hooks,
            target_platforms=target_platforms,
            fact_corrections=fact_corrections,
        )
        quality = self.quality_gate.evaluate(content)

        if not quality.passed:
            logger.info("Quality Gate 실패, 1회 재생성 시도...")
            content = await self.copywriter.write(
                research=research,
                hook_result=hooks,
                target_platforms=target_platforms,
                fact_corrections=fact_corrections,
            )
            quality = self.quality_gate.evaluate(content)

        # 팩트 체크 (비동기, 실패해도 파이프라인 계속)
        fact_check_result = None
        try:
            from app.agents.writer.fact_checker import FactChecker
            checker = FactChecker()
            # 첫 번째 플랫폼 본문으로 검증 (대표 콘텐츠)
            primary = content.platform_contents[0] if content.platform_contents else None
            if primary:
                fc = await checker.check(
                    topic=content.topic,
                    body_texts=primary.body,
                    language=self.profile.language,
                )
                fact_check_result = {
                    "verified": fc.verified,
                    "disputed_count": fc.disputed_count,
                    "uncertain_count": fc.uncertain_count,
                    "summary": fc.summary,
                    "claims": [
                        {"claim": c.claim, "status": c.status, "note": c.note}
                        for c in fc.claims
                    ],
                }
        except Exception as e:
            logger.warning(f"팩트 체크 실패 (무시): {e}")

        return {
            "content": content_plan_to_dict(content),
            "quality_score": quality.score,
            "quality_passed": quality.passed,
            "fact_check": fact_check_result,
        }

    # ── 플랫폼 타입 분류 ──────────────────────────────────────
    # 캐러셀: HTML/CSS Playwright 렌더링 (슬라이드 카드)
    CAROUSEL_PLATFORMS = {"instagram", "linkedin"}
    # 숏폼 영상: 9:16 세로, 최대 60초, 빠른 페이싱
    SHORT_VIDEO_PLATFORMS = {"youtube_shorts", "instagram_reels", "tiktok"}
    # 텍스트 + 단일 이미지: 영상 없음
    TEXT_IMAGE_PLATFORMS = {"x", "threads"}
    # 롱폼 영상: 16:9, 5분+, 챕터·메타데이터·썸네일 포함 → youtube

    async def run_render(
        self,
        content_dict: dict,
        topic: str,
        platform: str = "youtube",
    ) -> dict:
        """Stage 4: 플랫폼 타입별 이미지/씬 생성
        - carousel (instagram/linkedin): CreativeDirector → ArtDirector → DesignReviewer
        - short_video (youtube_shorts/instagram_reels/tiktok): 9:16 씬 이미지 (빠른 페이싱)
        - text_image (x/threads): 단일 헤더 이미지
        - long_form_video (youtube): 풀 씬 파이프라인 + 썸네일 + 메타데이터
        반환: {"image_paths", "render_type", "thumbnail_path", "metadata", "video_plan", "thumbnail_spec"}
        """
        if platform in self.CAROUSEL_PLATFORMS:
            return await self._run_render_carousel(content_dict, topic, platform)
        if platform in self.SHORT_VIDEO_PLATFORMS:
            return await self._run_render_short_video(content_dict, topic, platform)
        if platform in self.TEXT_IMAGE_PLATFORMS:
            return await self._run_render_text_image(content_dict, topic, platform)
        # 기본: youtube 롱폼
        return await self._run_render_scene(content_dict, topic, platform)

    async def _run_render_carousel(self, content_dict: dict, topic: str, platform: str) -> dict:
        """캐러셀 플랫폼: ArtDirector (Playwright) → 슬라이드 PNG"""
        from app.agents.media.art_director import ArtDirectorAgent
        from app.agents.media.design_reviewer import DesignReviewerAgent
        from app.agents.media.creative_director import CreativeDirectorAgent

        logger.info(f"[Stage 4-Carousel] Playwright 렌더링 [{platform}]")
        content_plan = content_plan_from_dict(content_dict)

        target = next(
            (pc for pc in content_plan.platform_contents if pc.platform == platform),
            content_plan.platform_contents[0],
        )

        slug = re.sub(r"[^\w]", "_", topic, flags=re.ASCII)[:25]
        art = ArtDirectorAgent(self.profile)

        # Step 1: Creative Director → 디자인 전략
        design_plan = None
        try:
            cd = CreativeDirectorAgent(self.profile, brand={})
            design_plan = await cd.plan_design(target, content_plan)
            logger.info(f"  [CD] 테마: {design_plan.theme_name}, {len(design_plan.slides)}슬라이드")
        except Exception as e:
            logger.warning(f"  [CD] 실패 (ArtDirector 기본값 사용): {e}")

        # Step 2: ArtDirector → 캐러셀 렌더링
        slides = await art.render_carousel(target, slug)
        image_paths = [str(asset.file_path) for asset in slides]
        logger.info(f"  [ArtDirector] {len(image_paths)}장 렌더링 완료")

        # Step 3: Design Reviewer → 품질 검수
        if design_plan and image_paths:
            try:
                reviewer = DesignReviewerAgent()
                review = reviewer.review(
                    design_plan=design_plan,
                    rendered_files=[Path(p) for p in image_paths],
                )
                logger.info(f"  [DesignReview] {'PASS' if review.passed else 'FAIL'} ({review.score}/100)")
                if not review.passed:
                    for issue in review.issues:
                        if issue.severity == "error":
                            logger.warning(f"    ERROR 슬라이드{issue.slide_index}: {issue.message}")
            except Exception as e:
                logger.warning(f"  [DesignReview] 검수 실패 (무시): {e}")

        # 썸네일
        thumbnail_path = None
        try:
            thumb_text = content_plan.thumbnail_text or target.hook
            thumb = await art.render_thumbnail(target, thumb_text, slug)
            if thumb:
                thumbnail_path = str(thumb.file_path)
                logger.info(f"  [Thumbnail] 생성 완료: {thumb.width}x{thumb.height}")
        except Exception as e:
            logger.warning(f"  [Thumbnail] 실패 (무시): {e}")

        return {
            "image_paths": image_paths,
            "render_type": "carousel",
            "thumbnail_path": thumbnail_path,
        }

    async def _run_render_scene(self, content_dict: dict, topic: str, platform: str) -> dict:
        """영상 플랫폼: VideoPlannerAgent → VideoDirectorAgent → ImagePrompter → Imagen 4"""
        from app.agents.media.image_generation import generate_all_scenes, SCENES_DIR
        from app.agents.media.image_prompter import generate_image_prompts
        from app.agents.media.video_planner import VideoPlannerAgent
        from app.agents.media.video_director import enhance_prompts_with_direction
        from app.agents.media.thumbnail_agent import generate_thumbnail_spec, render_thumbnail, thumbnail_spec_to_dict
        from app.agents.media.metadata_agent import MetadataAgent, metadata_to_dict

        logger.info(f"[Stage 4-Scene] YouTube 씬 이미지 생성 파이프라인 [{platform}]")
        content_plan = content_plan_from_dict(content_dict)

        target = next(
            (pc for pc in content_plan.platform_contents if pc.platform == platform),
            content_plan.platform_contents[0],
        )

        slug = re.sub(r"[^\w]", "_", topic, flags=re.ASCII)[:25]

        # research에서 thumbnail_style 추출 (없으면 빈 문자열)
        thumbnail_style = content_plan.platform_contents[0].metadata.get(
            "thumbnail_style", ""
        ) if content_plan.platform_contents else ""

        # Step 1: Video Planner — 씬별 샷 리스트 + 페이싱
        logger.info("  [VideoPlannerAgent] 씬 플래닝 중...")
        video_plan = None
        try:
            planner = VideoPlannerAgent(self.profile)
            video_plan = await planner.plan(
                topic=topic,
                hook=target.hook,
                body_slides=target.body,
                platform=platform,
            )
        except Exception as e:
            logger.warning(f"  [VideoPlannerAgent] 실패 (계속): {e}")

        # Step 2: ImagePrompter — Imagen 기본 프롬프트
        logger.info("  [ImagePrompter] Imagen 전용 프롬프트 생성 중...")
        base_prompts = await generate_image_prompts(
            topic=topic,
            hook=target.hook,
            body_slides=target.body,
            rough_prompts=target.image_prompts or [],
            language=self.profile.language,
            platform=platform,
        )

        # Step 3: Video Director — 영화적 연출 강화
        optimized_prompts = base_prompts
        if video_plan:
            logger.info("  [VideoDirectorAgent] 연출 강화 중...")
            try:
                optimized_prompts = await enhance_prompts_with_direction(
                    base_prompts=base_prompts,
                    video_plan=video_plan,
                    topic=topic,
                )
            except Exception as e:
                logger.warning(f"  [VideoDirectorAgent] 실패 (기본 프롬프트 사용): {e}")

        # Step 4: Imagen 4 씬 이미지 생성
        image_paths = await generate_all_scenes(
            slide_texts=target.body,
            image_prompts=optimized_prompts,
            topic=topic,
            platform=platform,
            language=self.profile.language,
            slug=slug,
        )
        image_paths = [p for p in image_paths if p]
        logger.info(f"  씬 이미지 완료: {len(image_paths)}장")

        # Step 5: Thumbnail Agent — CTR 최적화 썸네일
        thumbnail_path = None
        thumbnail_spec_dict = None
        try:
            logger.info("  [ThumbnailAgent] 썸네일 생성 중...")
            thumb_spec = await generate_thumbnail_spec(
                topic=topic,
                hook=target.hook,
                winning_formula_thumbnail_style=thumbnail_style,
                language=self.profile.language,
            )
            thumbnail_spec_dict = thumbnail_spec_to_dict(thumb_spec)

            thumb_output = SCENES_DIR / f"{slug}_thumbnail.jpg"
            result = await render_thumbnail(
                spec=thumb_spec,
                output_path=thumb_output,
                topic=topic,
                language=self.profile.language,
            )
            if result:
                thumbnail_path = str(result)
        except Exception as e:
            logger.warning(f"  [ThumbnailAgent] 실패 (무시): {e}")

        # Step 6: Metadata Agent — YouTube SEO 메타데이터
        metadata_dict = None
        try:
            logger.info("  [MetadataAgent] SEO 메타데이터 생성 중...")
            meta_agent = MetadataAgent(self.profile)
            metadata = await meta_agent.generate(
                topic=topic,
                hook=target.hook,
                body_slides=target.body,
                keywords=target.hashtags or [],
                platform=platform,
            )
            metadata_dict = metadata_to_dict(metadata)
        except Exception as e:
            logger.warning(f"  [MetadataAgent] 실패 (무시): {e}")

        # video_plan 직렬화
        video_plan_dict = None
        if video_plan:
            video_plan_dict = {
                "pacing": video_plan.pacing,
                "visual_style": video_plan.visual_style,
                "color_theme": video_plan.color_theme,
                "total_duration_seconds": video_plan.total_duration_seconds,
                "shots": [
                    {
                        "slide_index": s.slide_index,
                        "camera_movement": s.camera_movement,
                        "mood": s.mood,
                        "duration_seconds": s.duration_seconds,
                        "transition": s.transition,
                        "ken_burns": s.ken_burns,
                    }
                    for s in video_plan.shots
                ],
            }

        return {
            "image_paths": image_paths,
            "render_type": "scene",
            "thumbnail_path": thumbnail_path,
            "thumbnail_spec": thumbnail_spec_dict,
            "metadata": metadata_dict,
            "video_plan": video_plan_dict,
        }

    async def _run_render_short_video(self, content_dict: dict, topic: str, platform: str) -> dict:
        """숏폼 영상 플랫폼 (youtube_shorts/instagram_reels/tiktok): 9:16 씬 이미지
        - 롱폼과 차이: 짧은 목표 시간(45초), 빠른 페이싱, 썸네일·챕터 없음
        """
        from app.agents.media.image_generation import generate_all_scenes
        from app.agents.media.image_prompter import generate_image_prompts
        from app.agents.media.video_planner import VideoPlannerAgent
        from app.agents.media.video_director import enhance_prompts_with_direction

        logger.info(f"[Stage 4-ShortVideo] 숏폼 씬 이미지 [{platform}]")
        content_plan = content_plan_from_dict(content_dict)

        target = next(
            (pc for pc in content_plan.platform_contents if pc.platform == platform),
            content_plan.platform_contents[0],
        )

        slug = re.sub(r"[^\w]", "_", topic, flags=re.ASCII)[:25]

        # Step 1: Video Planner — 숏폼 전용 (목표 45초, 빠른 페이싱)
        video_plan = None
        try:
            planner = VideoPlannerAgent(self.profile)
            video_plan = await planner.plan(
                topic=topic,
                hook=target.hook,
                body_slides=target.body,
                platform=platform,
                target_duration_seconds=45,
            )
        except Exception as e:
            logger.warning(f"  [VideoPlannerAgent] 실패 (계속): {e}")

        # Step 2: ImagePrompter — 9:16 프롬프트
        base_prompts = await generate_image_prompts(
            topic=topic,
            hook=target.hook,
            body_slides=target.body,
            rough_prompts=target.image_prompts or [],
            language=self.profile.language,
            platform=platform,  # 9:16 aspect 자동 적용
        )

        # Step 3: Video Director — 에너제틱 스타일
        optimized_prompts = base_prompts
        if video_plan:
            try:
                optimized_prompts = await enhance_prompts_with_direction(
                    base_prompts=base_prompts,
                    video_plan=video_plan,
                    topic=topic,
                )
            except Exception as e:
                logger.warning(f"  [VideoDirectorAgent] 실패 (기본 프롬프트 사용): {e}")

        # Step 4: Imagen 4 씬 이미지 (9:16)
        image_paths = await generate_all_scenes(
            slide_texts=target.body,
            image_prompts=optimized_prompts,
            topic=topic,
            platform=platform,
            language=self.profile.language,
            slug=slug,
        )
        image_paths = [p for p in image_paths if p]
        logger.info(f"  숏폼 씬 이미지 완료: {len(image_paths)}장")

        # video_plan 직렬화
        video_plan_dict = None
        if video_plan:
            video_plan_dict = {
                "pacing": video_plan.pacing,
                "visual_style": video_plan.visual_style,
                "color_theme": video_plan.color_theme,
                "total_duration_seconds": video_plan.total_duration_seconds,
                "shots": [
                    {
                        "slide_index": s.slide_index,
                        "camera_movement": s.camera_movement,
                        "mood": s.mood,
                        "duration_seconds": s.duration_seconds,
                        "transition": s.transition,
                        "ken_burns": s.ken_burns,
                    }
                    for s in video_plan.shots
                ],
            }

        return {
            "image_paths": image_paths,
            "render_type": "scene",
            "thumbnail_path": None,  # 숏폼은 첫 프레임이 썸네일
            "thumbnail_spec": None,
            "metadata": None,
            "video_plan": video_plan_dict,
        }

    async def _run_render_text_image(self, content_dict: dict, topic: str, platform: str) -> dict:
        """텍스트+이미지 플랫폼 (x/threads): 단일 헤더 이미지 1장 생성"""
        from app.agents.media.image_generation import generate_scene_image, SCENES_DIR
        from app.agents.media.image_prompter import generate_image_prompts

        logger.info(f"[Stage 4-TextImage] 헤더 이미지 생성 [{platform}]")
        content_plan = content_plan_from_dict(content_dict)

        target = next(
            (pc for pc in content_plan.platform_contents if pc.platform == platform),
            content_plan.platform_contents[0],
        )

        slug = re.sub(r"[^\w]", "_", topic, flags=re.ASCII)[:25]

        # 훅 텍스트 기반으로 단일 이미지 프롬프트 생성
        try:
            prompts = await generate_image_prompts(
                topic=topic,
                hook=target.hook,
                body_slides=[target.hook],  # 훅 1장만
                rough_prompts=[],
                language=self.profile.language,
                platform="x",  # 16:9 기본
            )
            img_prompt = prompts[0] if prompts else f"Cinematic scene about {topic}. Photorealistic, 8K"
        except Exception:
            img_prompt = f"Cinematic scene about {topic}. Professional photography, 16:9"

        # 단일 이미지 생성
        output_path = SCENES_DIR / f"{slug}_{platform}_header.jpg"
        result = await generate_scene_image(
            slide_text=target.hook,
            image_prompt=img_prompt,
            output_path=output_path,
            topic=topic,
            language=self.profile.language,
            aspect_ratio="1:1" if platform == "threads" else "16:9",
        )

        image_paths = [str(result)] if result else []
        logger.info(f"  [{platform}] 헤더 이미지 {'완료' if result else '실패'}")

        return {
            "image_paths": image_paths,
            "render_type": "text_image",
            "thumbnail_path": None,
            "thumbnail_spec": None,
            "metadata": None,
            "video_plan": None,
        }

    async def run_video(
        self,
        content_dict: dict,
        topic: str,
        platform: str = "youtube",
        scene_image_paths: list[str] | None = None,
        with_tts: bool = False,
        tts_provider: str = "none",
        video_plan_dict: dict | None = None,
    ) -> dict:
        """Stage 5: 씬 이미지 → Veo 클립 → moviepy 조립 → VideoReviewer → ShortsExtractor"""
        from app.agents.media.video_production import produce_video
        from app.agents.media.video_reviewer import VideoReviewerAgent, video_review_to_dict
        from app.agents.media.shorts_extractor import extract_shorts, select_shorts_scenes
        from pathlib import Path as _Path

        logger.info(f"[Stage 5] 영상 제작 시작: [{platform}]")
        content_plan = content_plan_from_dict(content_dict)

        target = next(
            (pc for pc in content_plan.platform_contents if pc.platform == platform),
            content_plan.platform_contents[0],
        )

        # 텍스트 포맷 플랫폼은 영상 없음
        if platform in self.TEXT_IMAGE_PLATFORMS:
            logger.info(f"[Stage 5] {platform}은 텍스트+이미지 포맷 — 영상 제작 없음")
            return {"error": f"{platform}은 영상 포맷이 아닙니다", "platform": platform}

        is_short = platform in self.SHORT_VIDEO_PLATFORMS
        aspect_ratio = "9:16" if is_short or platform in ("instagram_reels",) else "16:9"

        # video_plan에서 씬별 재생 시간 추출
        scene_durations: list[float] = []
        if video_plan_dict and video_plan_dict.get("shots"):
            scene_durations = [float(s.get("duration_seconds", 6)) for s in video_plan_dict["shots"]]

        # Step 1: Veo + TTS + moviepy 영상 제작
        result = await produce_video(
            topic=topic,
            platform=platform,
            slide_texts=target.body,
            image_prompts=target.image_prompts or [f"{topic} scene {i+1}" for i in range(len(target.body))],
            scene_image_paths=scene_image_paths or [],
            aspect_ratio=aspect_ratio,
            with_tts=with_tts,
            tts_provider=tts_provider,
        )

        # Step 2: Video Reviewer — 품질 검수
        full_video = result.get("full_video")
        review_result = None
        if full_video:
            try:
                reviewer = VideoReviewerAgent()
                review = reviewer.review(
                    video_path=_Path(full_video),
                    platform=platform,
                    expected_slide_count=len(target.body),
                    tts_enabled=(tts_provider != "none"),
                )
                review_result = video_review_to_dict(review)
                if not review.passed:
                    logger.warning(
                        f"  [VideoReviewer] FAIL ({review.score:.0f}/100) "
                        f"— {[i.message for i in review.issues if i.severity == 'error']}"
                    )
            except Exception as e:
                logger.warning(f"  [VideoReviewer] 검수 실패 (무시): {e}")

        # Step 3: Shorts Extractor — 롱폼(youtube)에서만 자동 Shorts 추출
        # 숏폼 플랫폼(youtube_shorts, tiktok 등)은 이미 짧은 영상이므로 불필요
        shorts_result = None
        if platform == "youtube" and full_video and len(target.body) > 2:
            try:
                logger.info("  [ShortsExtractor] YouTube Shorts 자동 추출 중...")
                from app.agents.media.video_production import OUTPUT_DIR as VIDEO_OUTPUT_DIR
                slug = re.sub(r"[^\w]", "_", topic, flags=re.ASCII)[:25]
                shorts_path = VIDEO_OUTPUT_DIR / f"{slug}_auto_shorts.mp4"

                clip_paths_raw = result.get("clip_paths", [])
                clip_paths = [_Path(p) if p else None for p in clip_paths_raw]

                extracted = extract_shorts(
                    full_video_path=_Path(full_video),
                    output_path=shorts_path,
                    clip_paths=clip_paths,
                    slide_texts=target.body,
                    scene_durations=scene_durations or None,
                    crop_to_vertical=True,
                )
                if extracted:
                    shorts_result = str(extracted)
                    logger.info(f"  [ShortsExtractor] Shorts 생성 완료: {extracted.name}")
            except Exception as e:
                logger.warning(f"  [ShortsExtractor] 실패 (무시): {e}")

        result["video_review"] = review_result
        if shorts_result:
            result["auto_shorts"] = shorts_result

        return result

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
