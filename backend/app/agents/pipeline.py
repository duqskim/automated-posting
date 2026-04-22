"""
Pipeline Controller — 전체 파이프라인 오케스트레이션 (코드 기반)
역할: Researcher → Hooksmith → Copywriter → Quality Gate 순서 실행
"""
from dataclasses import dataclass
from loguru import logger

from app.config.market_profile import load_market_profile, MarketCode
from app.agents.research.agent import ResearcherAgent, ResearchResult
from app.agents.research.hooksmith import HooksmithAgent, HookResult
from app.agents.writer.copywriter import CopywriterAgent, ContentPlan
from app.agents.writer.quality_gate import QualityGate, QualityResult


@dataclass
class PipelineState:
    """파이프라인 진행 상태"""
    stage: str = "idle"  # idle, researching, hooking, writing, quality_check, passed, failed
    research: ResearchResult | None = None
    hooks: HookResult | None = None
    content: ContentPlan | None = None
    quality: QualityResult | None = None
    error: str | None = None


class PipelineController:
    """
    콘텐츠 파이프라인 컨트롤러

    실행 흐름:
      1. Researcher → 주제 리서치
      2. Hooksmith → 훅 생성 (훅 먼저!)
      3. Copywriter → 플랫폼별 콘텐츠 (독립 생성)
      4. Quality Gate → 검증 (실패 시 1회 재생성)
    """

    def __init__(self, market: MarketCode):
        self.profile = load_market_profile(market)
        self.researcher = ResearcherAgent(self.profile)
        self.hooksmith = HooksmithAgent(self.profile)
        self.copywriter = CopywriterAgent(self.profile)
        self.quality_gate = QualityGate(self.profile)
        self.state = PipelineState()

    async def run(
        self,
        topic: str,
        target_platforms: list[str] | None = None,
        series_context: str | None = None,
    ) -> PipelineState:
        """전체 파이프라인 실행"""
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
            # 1회 재생성 시도
            logger.info("Quality Gate 실패, 1회 재생성 시도...")
            self.state.content = await self.copywriter.write(
                research=self.state.research,
                hook_result=self.state.hooks,
                target_platforms=platforms,
                series_context=series_context,
            )
            self.state.quality = self.quality_gate.evaluate(self.state.content)

        if self.state.quality.passed:
            self.state.stage = "passed"
            logger.info(f"=== Pipeline 완료: PASS (점수: {self.state.quality.score}/100) ===")
        else:
            self.state.stage = "failed"
            self.state.error = f"Quality Gate 2회 실패 (점수: {self.state.quality.score}/100)"
            logger.warning(f"=== Pipeline: {self.state.error} ===")

        return self.state
