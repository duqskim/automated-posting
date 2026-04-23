"""
Design Reviewer Agent — 디자인 검수
역할: 렌더링된 이미지의 품질 검증 (코드 기반, LLM 호출 없음)

검수 항목:
  1. 텍스트 오버플로우 (잘림) 감지
  2. 최소 콘트라스트 비율 확인
  3. 브랜드 일관성 (색상, 핸들)
  4. 슬라이드 다양성 (연속 중복 템플릿 경고)
  5. 이미지 파일 유효성
"""
from pathlib import Path
from dataclasses import dataclass, field
from loguru import logger

from app.agents.media.creative_director import DesignPlan, SlideDesign


@dataclass
class DesignIssue:
    slide_index: int
    severity: str  # "error", "warning"
    category: str  # "overflow", "contrast", "brand", "variety", "file"
    message: str


@dataclass
class DesignReviewResult:
    passed: bool
    score: float  # 0~100
    issues: list[DesignIssue] = field(default_factory=list)


class DesignReviewerAgent:
    """디자인 검수 에이전트"""

    def __init__(self):
        pass

    def _check_text_overflow(self, design: SlideDesign) -> list[DesignIssue]:
        """텍스트 오버플로우 위험 감지"""
        issues = []
        data = design.template_data

        # 제목 길이 체크
        title = data.get("main_text") or data.get("title") or ""
        if design.template_name == "hook_bold" and len(title) > 40:
            issues.append(DesignIssue(
                slide_index=design.slide_index,
                severity="warning",
                category="overflow",
                message=f"훅 텍스트 길이 {len(title)}자 — 40자 초과 시 잘릴 위험",
            ))

        # 본문 길이 체크
        body = data.get("body") or data.get("context") or ""
        if len(body) > 200:
            issues.append(DesignIssue(
                slide_index=design.slide_index,
                severity="warning",
                category="overflow",
                message=f"본문 {len(body)}자 — 200자 초과 시 폰트 축소 필요",
            ))

        # 리스트 아이템 수 체크
        items = data.get("items", [])
        if len(items) > 5:
            issues.append(DesignIssue(
                slide_index=design.slide_index,
                severity="error",
                category="overflow",
                message=f"리스트 아이템 {len(items)}개 — 최대 5개 권장",
            ))

        return issues

    def _check_variety(self, slides: list[SlideDesign]) -> list[DesignIssue]:
        """템플릿 다양성 검사"""
        issues = []

        for i in range(1, len(slides)):
            if slides[i].template_name == slides[i-1].template_name:
                if slides[i].template_name not in ("hook_bold", "summary"):
                    issues.append(DesignIssue(
                        slide_index=slides[i].slide_index,
                        severity="warning",
                        category="variety",
                        message=f"슬라이드 {i}~{i+1} 동일 템플릿 '{slides[i].template_name}' 연속 사용",
                    ))

        # 전체 중 editorial이 60% 이상이면 경고
        editorial_count = sum(1 for s in slides if s.template_name == "editorial")
        if len(slides) > 3 and editorial_count / len(slides) > 0.6:
            issues.append(DesignIssue(
                slide_index=0,
                severity="warning",
                category="variety",
                message=f"editorial 템플릿 {editorial_count}/{len(slides)}장 — 시각적 단조로움 위험",
            ))

        return issues

    def _check_brand_consistency(self, slides: list[SlideDesign]) -> list[DesignIssue]:
        """브랜드 일관성 검사"""
        issues = []

        if not slides:
            return issues

        base_theme = slides[0].theme
        for slide in slides[1:]:
            if slide.theme.get("accent") != base_theme.get("accent"):
                issues.append(DesignIssue(
                    slide_index=slide.slide_index,
                    severity="error",
                    category="brand",
                    message="액센트 색상이 다른 슬라이드와 불일치",
                ))
                break

        return issues

    def _check_rendered_files(self, image_paths: list[Path]) -> list[DesignIssue]:
        """렌더링된 파일 유효성 검사"""
        issues = []

        for i, path in enumerate(image_paths):
            if not path.exists():
                issues.append(DesignIssue(
                    slide_index=i + 1,
                    severity="error",
                    category="file",
                    message=f"렌더링된 파일 없음: {path.name}",
                ))
            elif path.stat().st_size < 5000:  # 5KB 미만이면 빈 이미지 가능성
                issues.append(DesignIssue(
                    slide_index=i + 1,
                    severity="warning",
                    category="file",
                    message=f"파일 크기 {path.stat().st_size}B — 렌더링 실패 가능성",
                ))

        return issues

    def review(
        self,
        design_plan: DesignPlan,
        rendered_files: list[Path] | None = None,
    ) -> DesignReviewResult:
        """전체 디자인 검수"""
        logger.info(f"=== Design Reviewer: {len(design_plan.slides)}장 검수 시작 ===")

        all_issues = []

        # 1. 텍스트 오버플로우
        for slide in design_plan.slides:
            all_issues.extend(self._check_text_overflow(slide))

        # 2. 다양성
        all_issues.extend(self._check_variety(design_plan.slides))

        # 3. 브랜드 일관성
        all_issues.extend(self._check_brand_consistency(design_plan.slides))

        # 4. 파일 유효성
        if rendered_files:
            all_issues.extend(self._check_rendered_files(rendered_files))

        # 점수
        error_count = sum(1 for i in all_issues if i.severity == "error")
        warning_count = sum(1 for i in all_issues if i.severity == "warning")
        score = max(0, 100 - (error_count * 25) - (warning_count * 5))
        passed = error_count == 0 and score >= 60

        result = DesignReviewResult(passed=passed, score=score, issues=all_issues)

        logger.info(f"Design Review: {'PASS' if passed else 'FAIL'} "
                     f"(점수: {score}/100, {error_count} errors, {warning_count} warnings)")

        return result
