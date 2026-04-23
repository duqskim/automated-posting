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
    "주식": "dark_premium",
    "ETF": "dark_premium",
    "ISA": "dark_premium",
    "절세": "dark_mint",
    "세금": "dark_mint",
    "AI": "dark_coral",
    "테크": "dark_coral",
    "기술": "dark_coral",
    "건강": "dark_mint",
    "finance": "dark_premium",
    "investing": "dark_premium",
    "stock": "dark_premium",
    "tech": "dark_coral",
    "productivity": "dark_mint",
    "health": "dark_mint",
}

# 주제 카테고리 → 배경 아이콘 (list_icons bg_icon 용)
CATEGORY_ICONS = {
    "재테크": "💰",
    "투자": "📈",
    "주식": "📊",
    "ETF": "📊",
    "ISA": "🏦",
    "절세": "🧾",
    "세금": "🧾",
    "AI": "🤖",
    "테크": "⚡",
    "기술": "💻",
    "건강": "💪",
    "부동산": "🏠",
    "코인": "🪙",
    "finance": "💰",
    "investing": "📈",
    "tech": "⚡",
    "health": "💪",
}

# 아이템 내용 → 이모지 아이콘 매핑
CONTENT_ICON_MAP = {
    # 재테크/투자
    "수익": "📈", "수익률": "📈", "이익": "💹", "성장": "🚀",
    "손실": "📉", "리스크": "⚠️", "위험": "⚠️",
    "절세": "🧾", "세금": "💸", "비용": "💸",
    "적금": "🏦", "예금": "🏦", "은행": "🏦",
    "ETF": "📊", "주식": "📊", "투자": "💰",
    "배당": "🎯", "이자": "💵",
    # AI/테크
    "AI": "🤖", "인공지능": "🤖",
    "자동화": "⚙️", "데이터": "📊",
    "앱": "📱", "소프트웨어": "💻",
    "보안": "🔒", "해킹": "🔐",
    # 일반
    "시간": "⏰", "속도": "⚡", "빠른": "⚡",
    "방법": "✅", "단계": "🪜", "순서": "📋",
    "비교": "⚖️", "차이": "🔍",
    "무료": "🆓", "비용": "💰",
    "팁": "💡", "전략": "🎯", "핵심": "🔑",
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


def _detect_category_icon(topic: str) -> str:
    """주제에서 카테고리 배경 아이콘 탐지"""
    topic_lower = topic.lower()
    for keyword, icon in CATEGORY_ICONS.items():
        if keyword.lower() in topic_lower:
            return icon
    return ""


def _detect_item_icon(text: str) -> str:
    """아이템 텍스트에서 관련 이모지 탐지"""
    text_lower = text.lower()
    for keyword, icon in CONTENT_ICON_MAP.items():
        if keyword.lower() in text_lower:
            return icon
    return ""


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

        # 기본: dark_premium
        return "dark_premium", THEMES["dark_premium"]

    def _select_template(self, content_type: str, prev_template: str | None) -> str:
        """콘텐츠 타입에 맞는 템플릿 선택 (연속 중복 방지)"""
        candidates = TEMPLATE_MAP.get(content_type, ["editorial"])
        if len(candidates) == 1:
            return candidates[0]

        for template in candidates:
            if template != prev_template:
                return template
        return candidates[0]

    def _extract_chart_data(self, slide_text: str) -> dict:
        """슬라이드 텍스트에서 차트 데이터 추출"""
        import re as _re

        # ── 단일 퍼센트 → 링(도넛) 차트
        single_pct = _re.search(r'\b(\d+(?:\.\d+)?)\s*%', slide_text)
        multi_pcts = _re.findall(r'([가-힣A-Za-z\w]+)[:\s]+(\d+(?:\.\d+)?)\s*%', slide_text)

        if len(multi_pcts) >= 2:
            # 여러 항목: 수평 막대 차트
            labels = [m[0].strip()[:12] for m in multi_pcts[:5]]
            raw_vals = [float(m[1]) for m in multi_pcts[:5]]
            max_val = max(raw_vals) if raw_vals else 1
            percents = [round(v / max_val * 100) for v in raw_vals]
            val_strs = [f"{v:.1f}%" if v != int(v) else f"{int(v)}%" for v in raw_vals]
            return {
                "chart_type": "bars",
                "chart_labels": labels,
                "chart_values": val_strs,
                "chart_percents": percents,
            }
        elif single_pct:
            # 단일 퍼센트: 링 차트
            val = float(single_pct.group(1))
            return {
                "chart_type": "ring",
                "chart_value": val,
            }

        # ── 숫자 비교 (라벨: 숫자 패턴, % 없음)
        labeled_nums = _re.findall(r'([가-힣A-Za-z\w]+)[:\s]+(\d[\d,]*(?:\.\d+)?)\b', slide_text)
        if len(labeled_nums) >= 2:
            labels = [m[0].strip()[:12] for m in labeled_nums[:5]]
            raw_vals = []
            for m in labeled_nums[:5]:
                try:
                    raw_vals.append(float(m[1].replace(",", "")))
                except ValueError:
                    continue
            if len(raw_vals) >= 2:
                max_val = max(raw_vals) if raw_vals else 1
                percents = [round(v / max_val * 100) for v in raw_vals]
                val_strs = [f"{int(v):,}" if v == int(v) else f"{v:,.1f}" for v in raw_vals]
                return {
                    "chart_type": "bars",
                    "chart_labels": labels,
                    "chart_values": val_strs,
                    "chart_percents": percents,
                }

        return {}

    def _build_template_data(
        self, slide_text: str, content_type: str, slide_index: int,
        total_slides: int, content: PlatformContent, theme: dict,
        topic: str = "",
    ) -> dict:
        """슬라이드 텍스트 → 템플릿용 데이터 변환"""
        import re as _re

        lines = [ln.strip() for ln in slide_text.strip().split("\n") if ln.strip()]
        title = lines[0] if lines else slide_text[:40]
        body_lines = lines[1:] if len(lines) > 1 else []
        body = "\n".join(body_lines)

        base_data = {
            **theme,
            "brand_handle": self.brand.get("handle", ""),
            "slide_num": str(slide_index),
            "total_slides": str(total_slides),
        }

        if content_type == "hook":
            hook_text = content.hook if slide_index == 1 and content.hook else title
            title_size = 68 if len(hook_text) <= 12 else 60 if len(hook_text) <= 20 else 52 if len(hook_text) <= 30 else 44
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
            import re as _re3
            numbers = _re3.findall(r'[\d,]+\.?\d*\s*[%원만억$배개명조천]+', slide_text)
            if not numbers:
                numbers = _re3.findall(r'[\d,]+\.?\d*', slide_text)
            hero_num = numbers[0].strip() if numbers else title[:8]
            context_text = _re3.sub(_re3.escape(hero_num), "", slide_text, count=1).strip()
            context_text = context_text or body or title
            num_only = _re3.sub(r'[^0-9,.]', '', hero_num)
            unit_only = _re3.sub(r'[\d,.]', '', hero_num).strip()
            number_size = 160 if len(num_only) <= 3 else 120 if len(num_only) <= 5 else 90

            # 차트 데이터 추출
            chart_data = self._extract_chart_data(slide_text)

            base_data.update({
                "number": num_only,
                "unit": unit_only,
                "context": context_text[:80],
                "label": title if num_only and title != hero_num else "",
                "number_size": number_size,
                "title": title,
                **chart_data,
            })

        elif content_type == "comparison":
            def _strip_marker(s: str) -> str:
                return _re.sub(r'^[\s\-•*\d\.]+\s*', '', s).strip()

            vs_match = _re.search(r'(.+?)\s*[Vv][Ss]\.?\s*(.+)', title)
            ko_match = _re.search(r'(.+?)[와과]\s*(.+?)\s*비교', title)

            _SUFFIX_RE = _re.compile(r'\s*(차이점|비교|차이|대비|분석)$')
            if vs_match:
                left_title = _SUFFIX_RE.sub('', vs_match.group(1).strip()).strip()
                right_title = _SUFFIX_RE.sub('', vs_match.group(2).strip()).strip()
            elif ko_match:
                left_title = ko_match.group(1).strip()
                right_title = ko_match.group(2).strip()
            else:
                clean_items = [_strip_marker(l) for l in body_lines if l.strip()]
                if len(clean_items) >= 2:
                    def _extract_type(s: str) -> str:
                        c = s.split(':')[0].split('(')[0].split('–')[0].strip()
                        return c[:12] if c else s[:12]
                    left_title = _extract_type(clean_items[0])
                    right_title = _extract_type(clean_items[min(1, len(clean_items)-1)])
                else:
                    left_title = "장점"
                    right_title = "단점"

            clean_lines = [_strip_marker(l) for l in body_lines if l.strip()]
            if not clean_lines:
                clean_lines = [body or "항목 1"]
            mid = (len(clean_lines) + 1) // 2
            left_items = clean_lines[:mid]
            right_items = clean_lines[mid:] or clean_lines[-1:]

            # 비교 요약 바: 아이템 수 기준
            left_count = len(left_items)
            right_count = len(right_items)
            total_count = left_count + right_count
            left_strength = round(left_count / total_count * 100) if total_count else 50
            right_strength = 100 - left_strength

            base_data.update({
                "title": title,
                "left_title": left_title,
                "right_title": right_title,
                "left_items": left_items[:4],
                "right_items": right_items[:4],
                "show_summary_bar": True,
                "left_strength": left_strength,
                "right_strength": right_strength,
            })

        elif content_type in ("steps", "list"):
            items = []
            bullet_lines = [ln for ln in body_lines if ln]
            if not bullet_lines:
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
                colon_match = _re.match(r'^[\d\.\-\•\*\s]*(.+?):\s*(.+)$', line)
                num_match = _re.match(r'^[\d\.\-\•\*]+\s+(.+)$', line)
                if colon_match:
                    item_title = colon_match.group(1).strip()[:35]
                    item_desc = colon_match.group(2).strip()[:60]
                elif num_match:
                    item_title = num_match.group(1).strip()[:50]
                    item_desc = ""
                else:
                    item_text = line.strip()
                    if len(item_text) > 30:
                        item_title = item_text[:30]
                        item_desc = item_text[30:].strip()[:60]
                    else:
                        item_title = item_text
                        item_desc = ""

                # 아이콘 탐지
                icon = _detect_item_icon(item_title + " " + item_desc)
                items.append({"title": item_title, "desc": item_desc, "icon": icon})

            if not items:
                items = [{"title": title, "desc": body[:60], "icon": ""}]

            # 카테고리 배경 아이콘
            bg_icon = _detect_category_icon(topic or title)

            base_data.update({
                "title": title if body_lines else "핵심 정리",
                "items": items[:5],
                "category_label": "핵심 정리",
                "bg_icon": bg_icon,
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
            highlight = ""
            if body_lines and len(body_lines) >= 2:
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
            ctype = "explanation"
            if i < len(classifications):
                ctype = classifications[i].get("type", "explanation")

            if i == 0:
                ctype = "hook"
            elif i == total - 1:
                ctype = "cta"

            template_name = self._select_template(ctype, prev_template)
            template_data = self._build_template_data(
                slide_text, ctype, i + 1, total, content, theme,
                topic=content_plan.topic,
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
            canvas_size={"width": 1080, "height": 1350},
            font_primary="Pretendard",
            font_accent="Pretendard",
        )

        logger.info(f"  디자인 플랜 완성: {len(slides)}장 "
                     f"[{', '.join(s.template_name for s in slides)}]")
        return plan
