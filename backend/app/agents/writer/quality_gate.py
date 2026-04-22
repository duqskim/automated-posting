"""
Quality Gate — 코드 기반 콘텐츠 품질 검증 (LLM 호출 없음)
역할: AI 티 검출, 훅 강도 점수, 팩트 체크, 플랫폼 규격 검증
"""
import re
from dataclasses import dataclass, field
from loguru import logger

from app.config.market_profile import MarketProfile
from app.agents.writer.copywriter import ContentPlan, PlatformContent


@dataclass
class QualityIssue:
    platform: str
    severity: str  # "error", "warning"
    category: str  # "ai_detection", "hook_strength", "fact_check", "format", "sensitive"
    message: str
    auto_fixed: bool = False


@dataclass
class QualityResult:
    passed: bool
    score: float  # 0~100
    issues: list[QualityIssue] = field(default_factory=list)
    fixed_content: ContentPlan | None = None


class QualityGate:
    """콘텐츠 품질 검증 게이트 (코드 기반, LLM 호출 없음)"""

    def __init__(self, market_profile: MarketProfile):
        self.profile = market_profile

    def _check_ai_detection(self, content: PlatformContent) -> list[QualityIssue]:
        """AI 티 나는 표현 검출 + 자동 수정"""
        issues = []
        ai_config = self.profile.ai_detection
        banned = ai_config.get("banned_patterns", [])

        all_text = " ".join([content.hook] + content.body + [content.caption])

        for pattern in banned:
            if pattern.lower() in all_text.lower():
                issues.append(QualityIssue(
                    platform=content.platform,
                    severity="warning",
                    category="ai_detection",
                    message=f"AI 티 표현 감지: '{pattern}'",
                ))

        return issues

    def _check_hook_strength(self, content: PlatformContent) -> list[QualityIssue]:
        """훅 강도 점수"""
        issues = []
        hook = content.hook

        # 길이 검사
        if self.profile.language == "ko":
            if len(hook) > 60:
                issues.append(QualityIssue(
                    platform=content.platform,
                    severity="warning",
                    category="hook_strength",
                    message=f"훅이 너무 긺: {len(hook)}자 (60자 이내 권장)",
                ))
        elif self.profile.language == "en":
            word_count = len(hook.split())
            if word_count > 15:
                issues.append(QualityIssue(
                    platform=content.platform,
                    severity="warning",
                    category="hook_strength",
                    message=f"훅이 너무 긺: {word_count}단어 (15단어 이내 권장)",
                ))

        # 숫자 포함 여부 (숫자 있는 훅이 성과 높음)
        has_number = bool(re.search(r'\d', hook))
        if not has_number:
            issues.append(QualityIssue(
                platform=content.platform,
                severity="warning",
                category="hook_strength",
                message="훅에 구체적 숫자 없음 (숫자 포함 시 성과 높음)",
            ))

        return issues

    def _check_fact_claims(self, content: PlatformContent) -> list[QualityIssue]:
        """출처 없는 통계/수치 검출"""
        issues = []
        all_text = " ".join(content.body)

        # "N%가", "N%의", "N% of" 패턴 검출
        stat_patterns = [
            r'\d+\.?\d*%',  # 47.3%, 50%
            r'\d+만\s*명',  # 100만 명
            r'\d+억',       # 100억
            r'\$[\d,]+',    # $1,000
            r'\d+ million', # 5 million
            r'\d+ billion', # 2 billion
        ]

        for pattern in stat_patterns:
            matches = re.findall(pattern, all_text)
            for match in matches:
                # 반올림된 숫자 경고 (50%, 100%, 약 N%)
                if self.profile.ai_detection.get("require_specific_numbers"):
                    clean_num = re.sub(r'[%$,만억명 millionbillion]', '', match).strip()
                    try:
                        num = float(clean_num)
                        if num > 0 and num % 10 == 0 and num != 100:
                            issues.append(QualityIssue(
                                platform=content.platform,
                                severity="warning",
                                category="fact_check",
                                message=f"반올림 숫자 의심: {match} (구체적 수치 사용 권장: 47.3% > 50%)",
                            ))
                    except ValueError:
                        pass

        return issues

    def _check_format(self, content: PlatformContent) -> list[QualityIssue]:
        """플랫폼 규격 검증"""
        issues = []

        if content.platform == "instagram":
            if len(content.body) < 5:
                issues.append(QualityIssue(
                    platform=content.platform,
                    severity="error",
                    category="format",
                    message=f"캐러셀 슬라이드 부족: {len(content.body)}개 (최소 5개)",
                ))
            if len(content.hashtags) > self.profile.hashtag.count:
                issues.append(QualityIssue(
                    platform=content.platform,
                    severity="warning",
                    category="format",
                    message=f"해시태그 초과: {len(content.hashtags)}개 (최대 {self.profile.hashtag.count}개)",
                ))

        elif content.platform == "x":
            for i, tweet in enumerate(content.body):
                if len(tweet) > 280:
                    issues.append(QualityIssue(
                        platform=content.platform,
                        severity="error",
                        category="format",
                        message=f"트윗 {i+1} 글자 초과: {len(tweet)}자 (280자 제한)",
                    ))

        elif content.platform == "linkedin":
            total_len = len(content.hook) + sum(len(p) for p in content.body) + len(content.cta)
            if total_len > 3000:
                issues.append(QualityIssue(
                    platform=content.platform,
                    severity="warning",
                    category="format",
                    message=f"LinkedIn 포스트 길이 초과: {total_len}자 (1300자 권장)",
                ))

        return issues

    def _check_sensitive_content(self, content: PlatformContent) -> list[QualityIssue]:
        """민감 키워드 필터"""
        issues = []
        all_text = " ".join([content.hook] + content.body + [content.caption])

        # 투자 권유 표현 검출
        investment_triggers = {
            "ko": ["지금 사세요", "반드시 투자", "무조건 매수", "100% 수익", "원금 보장", "확실한 수익"],
            "en": ["guaranteed returns", "buy now", "risk-free", "100% profit", "you must invest"],
            "ja": ["絶対儲かる", "必ず利益", "元本保証", "リスクなし"],
        }

        triggers = investment_triggers.get(self.profile.language, [])
        for trigger in triggers:
            if trigger.lower() in all_text.lower():
                issues.append(QualityIssue(
                    platform=content.platform,
                    severity="error",
                    category="sensitive",
                    message=f"투자 권유 표현 검출: '{trigger}' — 삭제 필요",
                ))

        return issues

    def evaluate(self, content_plan: ContentPlan) -> QualityResult:
        """전체 콘텐츠 플랜 품질 평가"""
        logger.info(f"=== Quality Gate: '{content_plan.topic}' 검증 시작 ===")

        all_issues = []
        for content in content_plan.platform_contents:
            all_issues.extend(self._check_ai_detection(content))
            all_issues.extend(self._check_hook_strength(content))
            all_issues.extend(self._check_fact_claims(content))
            all_issues.extend(self._check_format(content))
            all_issues.extend(self._check_sensitive_content(content))

        # 점수 산정
        error_count = sum(1 for i in all_issues if i.severity == "error")
        warning_count = sum(1 for i in all_issues if i.severity == "warning")
        platform_count = len(content_plan.platform_contents)

        if platform_count == 0:
            score = 0
        else:
            score = max(0, 100 - (error_count * 20) - (warning_count * 5))

        passed = error_count == 0 and score >= 60

        result = QualityResult(
            passed=passed,
            score=score,
            issues=all_issues,
            fixed_content=content_plan if passed else None,
        )

        logger.info(f"Quality Gate 결과: {'PASS' if passed else 'FAIL'} "
                     f"(점수: {score}/100, {error_count} errors, {warning_count} warnings)")

        if not passed:
            for issue in all_issues:
                if issue.severity == "error":
                    logger.warning(f"  [{issue.platform}] {issue.category}: {issue.message}")

        return result
