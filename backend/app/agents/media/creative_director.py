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
        import re as _re

        lines = [ln.strip() for ln in slide_text.strip().split("\n") if ln.strip()]
        title = lines[0] if lines else slide_text[:40]
        body_lines = lines[1:] if len(lines) > 1 else []
        body = "\n".join(body_lines)

        # editorial/summary는 별도 테마 사용 (라이트 or 액센트)
        if content_type in ("explanation", "tip", "quote"):
            # editorial 라이트 테마 고정
            slide_theme = {
                **theme,
                # editorial.html은 내부에서 white bg 하드코딩하므로 accent만 주입
                "accent": theme.get("accent", "#2563EB"),
                "accent_secondary": theme.get("accent_secondary", "#7C3AED"),
            }
        elif content_type in ("summary", "cta"):
            # summary.html은 accent를 배경으로 씀 → 그대로 전달
            slide_theme = theme
        else:
            slide_theme = theme

        base_data = {
            **slide_theme,
            "brand_handle": self.brand.get("handle", ""),
            "slide_num": str(slide_index),
            "total_slides": str(total_slides),
        }

        if content_type == "hook":
            hook_text = content.hook if slide_index == 1 and content.hook else title
            title_size = 68 if len(hook_text) <= 12 else 60 if len(hook_text) <= 20 else 52 if len(hook_text) <= 30 else 44
            # 배경 워드: 주제 키워드 첫 단어 (최대 4자)
            import re as _re2
            words = _re2.sub(r'[^\w가-힣A-Za-z]', ' ', slide_text or "").split()
            bg_word = next((w for w in words if len(w) >= 2), "")[:6].upper()
            base_data.update({
                "main_text": hook_text,
                "sub_text": body if body else (lines[1] if len(lines) > 1 else ""),
                "title_size": title_size,
                "category": content.platform.upper(),
                "bg_word": bg_word,
            })

        elif content_type == "data":
            # 숫자+단위 패턴 추출 (%, 원, 만, 억, $, 배, 개 등)
            numbers = _re.findall(r'[\d,]+\.?\d*\s*[%원만억$배개명조천]+', slide_text)
            if not numbers:
                numbers = _re.findall(r'[\d,]+\.?\d*', slide_text)
            hero_num = numbers[0].strip() if numbers else title[:8]
            # 숫자 제외 나머지를 context로
            context_text = _re.sub(_re.escape(hero_num), "", slide_text, count=1).strip()
            context_text = context_text or body or title
            # 숫자와 단위 분리
            num_only = _re.sub(r'[^0-9,.]', '', hero_num)
            unit_only = _re.sub(r'[\d,.]', '', hero_num).strip()
            number_size = 160 if len(num_only) <= 3 else 120 if len(num_only) <= 5 else 90
            base_data.update({
                "number": num_only,
                "unit": unit_only,
                "context": context_text[:80],
                "label": title if num_only and title != hero_num else "",
                "number_size": number_size,
            })

        elif content_type == "comparison":
            # bullet/번호 마커 제거 함수
            def _strip_marker(s: str) -> str:
                return _re.sub(r'^[\s\-•*\d\.]+\s*', '', s).strip()

            # VS 패턴 파싱: "기존 vs 새로운"
            vs_match = _re.search(r'(.+?)\s*[Vv][Ss]\.?\s*(.+)', title)
            # 제목에서 한국어 "비교" 패턴도 추출: "A와 B 비교", "A 대 B"
            ko_match = _re.search(r'(.+?)[와과]\s*(.+?)\s*비교', title)

            _SUFFIX_RE = _re.compile(r'\s*(차이점|비교|차이|대비|분석)$')
            if vs_match:
                left_title = _SUFFIX_RE.sub('', vs_match.group(1).strip()).strip()
                right_title = _SUFFIX_RE.sub('', vs_match.group(2).strip()).strip()
            elif ko_match:
                left_title = ko_match.group(1).strip()
                right_title = ko_match.group(2).strip()
            else:
                # "A 3가지 비교" 처럼 비교 대상이 명시 안 된 경우 — 첫 두 아이템 첫 단어로 헤더
                clean_items = [_strip_marker(l) for l in body_lines if l.strip()]
                if len(clean_items) >= 2:
                    # 콜론 있으면 콜론 앞이 타입명
                    def _extract_type(s: str) -> str:
                        c = s.split(':')[0].split('(')[0].split('–')[0].strip()
                        return c[:12] if c else s[:12]
                    left_title = _extract_type(clean_items[0])
                    right_title = _extract_type(clean_items[min(1, len(clean_items)-1)])
                else:
                    left_title = "장점"
                    right_title = "단점"

            # body_lines 클린 + 균등 분배 (ceil 기준으로 left에 더 줌)
            clean_lines = [_strip_marker(l) for l in body_lines if l.strip()]
            if not clean_lines:
                clean_lines = [body or "항목 1"]
            mid = (len(clean_lines) + 1) // 2  # ceil
            left_items = clean_lines[:mid]
            right_items = clean_lines[mid:] or clean_lines[-1:]

            base_data.update({
                "title": title,
                "left_title": left_title,
                "right_title": right_title,
                "left_items": left_items[:4],
                "right_items": right_items[:4],
            })

        elif content_type in ("steps", "list"):
            items = []
            # 번호 또는 불릿 마커가 있으면 분리
            bullet_lines = [ln for ln in body_lines if ln]
            if not bullet_lines:
                # 전체 텍스트를 40자씩 나눔
                words = slide_text.split()
                chunk, chunks = [], []
                for w in words:
                    chunk.append(w)
                    if len(" ".join(chunk)) >= 30:
                        chunks.append(" ".join(chunk))
                        chunk = []
                if chunk:
                    chunks.append(" ".join(chunk))
                bullet_lines = chunks or [title]

            for line in bullet_lines[:5]:
                # "1. 제목: 설명" 패턴 파싱
                colon_match = _re.match(r'^[\d\.\-\•\*\s]*(.+?):\s*(.+)$', line)
                num_match = _re.match(r'^[\d\.\-\•\*]+\s+(.+)$', line)
                if colon_match:
                    items.append({"title": colon_match.group(1).strip()[:35], "desc": colon_match.group(2).strip()[:60]})
                elif num_match:
                    items.append({"title": num_match.group(1).strip()[:50], "desc": ""})
                else:
                    item_text = line.strip()
                    if len(item_text) > 30:
                        items.append({"title": item_text[:30], "desc": item_text[30:].strip()[:60]})
                    else:
                        items.append({"title": item_text, "desc": ""})

            if not items:
                items = [{"title": title, "desc": body[:60]}]

            base_data.update({
                "title": title if body_lines else "핵심 정리",
                "items": items[:5],
            })

        elif content_type in ("summary", "cta"):
            summary_items = []
            for ln in body_lines:
                clean = _re.sub(r'^[\d\.\-\•\*✓]+\s*', '', ln).strip()
                if clean:
                    summary_items.append(clean[:60])
            if not summary_items:
                summary_items = [title[:60]]

            base_data.update({
                "title": title if body_lines else "오늘의 핵심",
                "items": summary_items[:5],
                "cta_text": content.cta or "저장해두고 나중에 써먹으세요 🔖",
                "disclaimer": self.profile.content_rules.disclaimer_finance,
                "emoji": "📌" if content_type == "summary" else "🚀",
            })

        else:  # explanation, tip, quote → editorial 템플릿
            title_size = 46 if len(title) <= 18 else 38 if len(title) <= 28 else 32
            body_size = 24 if len(body) <= 120 else 20
            # 본문에서 강조할 문장 추출 (마지막 줄 or 짧은 핵심 문장)
            highlight = ""
            if body_lines and len(body_lines) >= 2:
                # 가장 짧은 줄 = 핵심 요약일 가능성 높음
                short = min(body_lines, key=len)
                if len(short) <= 50:
                    highlight = short
            base_data.update({
                "title": title,
                "body": body.replace("\n", "<br>"),
                "title_size": title_size,
                "body_size": body_size,
                "highlight": highlight,
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
