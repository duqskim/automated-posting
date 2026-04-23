"""
Creative Director Agent — 디자인 전략 + 템플릿 매핑
역할: 콘텐츠 분석 → 슬라이드별 디자인 전략 결정 → 템플릿+테마 매핑

실제 현장의 CD 역할:
  1. 주제/톤에 맞는 전체 비주얼 방향 결정
  2. 슬라이드별 콘텐츠 타입 분류 (훅/데이터/비교/리스트/CTA)
  3. 슬라이드별 템플릿 배정 (연속 중복 방지, 시각적 다양성)
  4. 다크/라이트 테마 결정
  5. 브랜드 색상 팔레트 선택
"""
from dataclasses import dataclass
from loguru import logger

from app.llm.factory import get_llm_client
from app.config.market_profile import MarketProfile
from app.agents.writer.copywriter import ContentPlan, PlatformContent


# 콘텐츠 타입 → 사용 가능한 템플릿
TEMPLATE_MAP = {
    "hook": ["hook_bold"],
    "data": ["data_hero", "editorial"],
    "comparison": ["comparison"],
    "steps": ["list_icons"],
    "list": ["list_icons"],
    "explanation": ["editorial"],
    "tip": ["editorial", "list_icons"],
    "quote": ["hook_bold"],
    "summary": ["summary"],
    "cta": ["summary"],
}

# 테마 팔레트
THEMES = {
    "dark_premium": {
        "bg_primary": "#0F172A",
        "bg_secondary": "#1E293B",
        "text_primary": "#F1F5F9",
        "text_secondary": "#94A3B8",
        "accent": "#3B82F6",
        "accent_secondary": "#8B5CF6",
    },
    "dark_coral": {
        "bg_primary": "#1A1A2E",
        "bg_secondary": "#16213E",
        "text_primary": "#F1F5F9",
        "text_secondary": "#94A3B8",
        "accent": "#E94560",
        "accent_secondary": "#FF6B6B",
    },
    "dark_mint": {
        "bg_primary": "#0F172A",
        "bg_secondary": "#1E293B",
        "text_primary": "#F1F5F9",
        "text_secondary": "#94A3B8",
        "accent": "#10B981",
        "accent_secondary": "#34D399",
    },
    "light_clean": {
        "bg_primary": "#FFFFFF",
        "bg_secondary": "#F8FAFC",
        "text_primary": "#0F172A",
        "text_secondary": "#64748B",
        "accent": "#2563EB",
        "accent_secondary": "#7C3AED",
    },
    "light_warm": {
        "bg_primary": "#FAFAF9",
        "bg_secondary": "#F5F5F4",
        "text_primary": "#292524",
        "text_secondary": "#78716C",
        "accent": "#F59E0B",
        "accent_secondary": "#EF4444",
    },
}

# 주제 카테고리 → 추천 테마
CATEGORY_THEME_MAP = {
    "재테크": "dark_premium",
    "투자": "dark_premium",
    "AI": "dark_coral",
    "테크": "dark_coral",
    "절세": "dark_mint",
    "finance": "dark_premium",
    "investing": "dark_premium",
    "tech": "dark_coral",
    "AI": "dark_coral",
    "productivity": "dark_mint",
}


@dataclass
class SlideDesign:
    slide_index: int
    content_type: str  # hook, data, comparison, steps, explanation, summary, cta
    template_name: str  # hook_bold, editorial, data_hero, etc.
    theme: dict  # 색상 팔레트
    template_data: dict  # Jinja2에 전달할 데이터


@dataclass
class DesignPlan:
    theme_name: str
    theme: dict
    slides: list[SlideDesign]
    canvas_size: dict  # {"width": 1080, "height": 1350}
    font_primary: str
    font_accent: str


class CreativeDirectorAgent:
    """디자인 전략 + 템플릿 매핑 에이전트"""

    def __init__(self, market_profile: MarketProfile, brand: dict | None = None):
        self.profile = market_profile
        self.brand = brand or {}
        self.llm = get_llm_client("research")

    async def classify_slides(self, content: PlatformContent) -> list[dict]:
        """LLM으로 슬라이드별 콘텐츠 타입 분류"""
        slides_text = "\n".join([
            f"슬라이드 {i+1}: {text[:100]}"
            for i, text in enumerate(content.body)
        ])

        prompt = f"""아래 캐러셀 슬라이드의 각 콘텐츠 타입을 분류해주세요.

슬라이드 목록:
{slides_text}

가능한 타입: hook, data, comparison, steps, list, explanation, tip, quote, summary, cta

각 슬라이드에 대해 JSON 배열로 응답:
[
  {{"index": 1, "type": "hook", "has_number": true, "key_element": "통계 데이터"}},
  {{"index": 2, "type": "explanation", "has_number": false, "key_element": "개념 설명"}},
  ...
]"""

        result = await self.llm.generate_json(prompt)
        if result and isinstance(result, list):
            return result

        # 폴백: 규칙 기반 분류
        classifications = []
        for i, text in enumerate(content.body):
            if i == 0:
                ctype = "hook"
            elif i == len(content.body) - 1:
                ctype = "cta"
            elif any(c.isdigit() for c in text) and "%" in text:
                ctype = "data"
            elif "vs" in text.lower() or "비교" in text:
                ctype = "comparison"
            elif any(marker in text for marker in ["1.", "2.", "3.", "첫째", "둘째"]):
                ctype = "steps"
            else:
                ctype = "explanation"
            classifications.append({"index": i + 1, "type": ctype})

        return classifications

    def _select_theme(self, topic: str) -> tuple[str, dict]:
        """주제에 맞는 테마 선택"""
        # 브랜드 커스텀 색상이 있으면 우선
        if self.brand.get("colors"):
            custom_theme = {
                "bg_primary": self.brand["colors"].get("bg", "#0F172A"),
                "bg_secondary": self.brand["colors"].get("bg_secondary", "#1E293B"),
                "text_primary": self.brand["colors"].get("text", "#F1F5F9"),
                "text_secondary": self.brand["colors"].get("text_secondary", "#94A3B8"),
                "accent": self.brand["colors"].get("primary", "#3B82F6"),
                "accent_secondary": self.brand["colors"].get("secondary", "#8B5CF6"),
            }
            return "custom_brand", custom_theme

        # 주제 키워드 매칭
        topic_lower = topic.lower()
        for keyword, theme_name in CATEGORY_THEME_MAP.items():
            if keyword.lower() in topic_lower:
                return theme_name, THEMES[theme_name]

        # 기본: dark_premium (저장율 가장 높음)
        return "dark_premium", THEMES["dark_premium"]

    def _select_template(self, content_type: str, prev_template: str | None) -> str:
        """콘텐츠 타입에 맞는 템플릿 선택 (연속 중복 방지)"""
        candidates = TEMPLATE_MAP.get(content_type, ["editorial"])
        if len(candidates) == 1:
            return candidates[0]

        # 이전 템플릿과 다른 걸 우선 선택
        for template in candidates:
            if template != prev_template:
                return template
        return candidates[0]

    def _build_template_data(
        self, slide_text: str, content_type: str, slide_index: int,
        total_slides: int, content: PlatformContent, theme: dict
    ) -> dict:
        """슬라이드 텍스트 → 템플릿용 데이터 변환"""
        lines = [ln.strip() for ln in slide_text.strip().split("\n") if ln.strip()]
        title = lines[0] if lines else slide_text[:40]
        body = "\n".join(lines[1:]) if len(lines) > 1 else ""

        base_data = {
            **theme,
            "brand_handle": self.brand.get("handle", ""),
            "slide_num": str(slide_index),
            "total_slides": str(total_slides),
        }

        if content_type == "hook":
            # 텍스트 길이에 따라 폰트 사이즈 조정
            title_size = 56 if len(title) <= 15 else 48 if len(title) <= 25 else 40
            base_data.update({
                "main_text": content.hook if slide_index == 1 else title,
                "sub_text": body,
                "title_size": title_size,
                "category": content.platform.upper(),
            })
        elif content_type == "data":
            # 숫자 추출
            import re
            numbers = re.findall(r'[\d,.]+[%원만억$]?', slide_text)
            hero_num = numbers[0] if numbers else ""
            base_data.update({
                "number": hero_num,
                "context": title if not hero_num else body or title,
                "label": "",
                "number_size": 96 if len(hero_num) <= 5 else 72,
            })
        elif content_type == "comparison":
            base_data.update({
                "title": title,
                "left_title": "A",
                "right_title": "B",
                "left_items": [body] if body else ["항목 1"],
                "right_items": ["항목 1"],
            })
        elif content_type in ("steps", "list"):
            items = []
            for line in lines[1:]:
                items.append({"title": line[:40], "desc": line[40:] if len(line) > 40 else ""})
            if not items:
                items = [{"title": title, "desc": body}]
            base_data.update({
                "title": title,
                "items": items[:5],
            })
        elif content_type in ("summary", "cta"):
            items = [line for line in lines[1:]] if len(lines) > 1 else [title]
            base_data.update({
                "title": title,
                "items": items[:5],
                "cta_text": content.cta,
                "disclaimer": self.profile.content_rules.disclaimer_finance,
                "emoji": "📌" if content_type == "summary" else "🚀",
            })
        else:  # explanation, tip, quote
            title_size = 44 if len(title) <= 20 else 36
            body_size = 24 if len(body) <= 100 else 20
            base_data.update({
                "title": title,
                "body": body.replace("\n", "<br>"),
                "title_size": title_size,
                "body_size": body_size,
                "point_num": slide_index - 1 if slide_index > 1 else None,
            })

        return base_data

    async def plan_design(self, content: PlatformContent, content_plan: ContentPlan) -> DesignPlan:
        """전체 디자인 계획 수립"""
        logger.info(f"=== Creative Director: [{content.platform}] 디자인 기획 ===")

        # 1. 테마 선택
        theme_name, theme = self._select_theme(content_plan.topic)
        logger.info(f"  테마: {theme_name}")

        # 2. 슬라이드별 콘텐츠 타입 분류
        classifications = await self.classify_slides(content)
        logger.info(f"  슬라이드 분류: {[c.get('type', '?') for c in classifications]}")

        # 3. 템플릿 매핑
        slides = []
        prev_template = None
        total = len(content.body)

        for i, slide_text in enumerate(content.body):
            # 분류 결과 가져오기
            ctype = "explanation"
            if i < len(classifications):
                ctype = classifications[i].get("type", "explanation")

            # 첫 번째는 항상 hook, 마지막은 항상 cta/summary
            if i == 0:
                ctype = "hook"
            elif i == total - 1:
                ctype = "cta"

            template_name = self._select_template(ctype, prev_template)
            template_data = self._build_template_data(
                slide_text, ctype, i + 1, total, content, theme
            )

            slides.append(SlideDesign(
                slide_index=i + 1,
                content_type=ctype,
                template_name=template_name,
                theme=theme,
                template_data=template_data,
            ))
            prev_template = template_name

        plan = DesignPlan(
            theme_name=theme_name,
            theme=theme,
            slides=slides,
            canvas_size={"width": 1080, "height": 1350},  # 4:5 비율 (IG 최적)
            font_primary="Pretendard",
            font_accent="Pretendard",
        )

        logger.info(f"  디자인 플랜 완성: {len(slides)}장 "
                     f"[{', '.join(s.template_name for s in slides)}]")
        return plan
