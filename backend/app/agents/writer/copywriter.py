"""
Copywriter Agent — 플랫폼별 독립 콘텐츠 생성
역할: 훅 + 리서치 → 플랫폼별 "재해석" 콘텐츠 (리포맷 ✕)
원칙: 같은 주제라도 플랫폼마다 완전히 다른 콘텐츠 (VaynerMedia 방식)
"""
from dataclasses import dataclass, field
from loguru import logger

from app.llm.factory import get_llm_client
from app.config.market_profile import MarketProfile
from app.agents.research.agent import ResearchResult
from app.agents.research.hooksmith import HookResult


@dataclass
class PlatformContent:
    platform: str
    hook: str
    body: list[str]  # 슬라이드별 / 트윗별 / 단락별
    caption: str
    hashtags: list[str]
    cta: str  # Call to Action
    image_prompts: list[str] = field(default_factory=list)  # 슬라이드별 이미지 생성 프롬프트
    metadata: dict = field(default_factory=dict)  # 플랫폼별 추가 데이터


@dataclass
class ContentPlan:
    topic: str
    market: str
    master_narrative: str  # 전체 스토리 요약
    platform_contents: list[PlatformContent]
    thumbnail_text: str


class CopywriterAgent:
    """플랫폼별 독립 콘텐츠 생성 에이전트"""

    def __init__(self, market_profile: MarketProfile):
        self.profile = market_profile
        self.llm = get_llm_client("writing")

    async def _generate_platform_content(
        self,
        platform: str,
        topic: str,
        hook: str,
        research: ResearchResult,
        series_context: str | None = None,
        fact_corrections: list[dict] | None = None,
        character: dict | None = None,
    ) -> PlatformContent | None:
        """단일 플랫폼용 콘텐츠 생성 (독립 LLM 호출)"""

        # 플랫폼별 포맷 지침
        format_guides = {
            "instagram": f"""Instagram 캐러셀 (7~10 슬라이드):
- 슬라이드 1: 훅 (반드시 "{hook}" 사용)
- 슬라이드 2: 두 번째 훅 (독립적으로 알고리즘 노출 가능)
- 슬라이드 3~(N-1): 핵심 내용 (슬라이드당 포인트 1개, {self.profile.get_text_limit()})
- 마지막 슬라이드: CTA + 핵심 요약
- 해시태그: {self.profile.hashtag.count}개""",

            "youtube": f"""YouTube 롱폼 나레이션 대본 (목표: 10~15분 영상):

슬라이드 구성 — 반드시 20~25개:
  슬라이드 1 (인트로/훅): 첫 30초 안에 시청자를 잡는 강렬한 오프닝. "{hook}" 사용.
  슬라이드 2~4 (배경): 왜 이 주제가 중요한가 / 문제 제기
  슬라이드 5~18 (본론): 핵심 내용을 챕터 단위로 전개 (챕터당 3~5슬라이드)
  슬라이드 19~22 (심화): 놀라운 반전 / 숨겨진 사실 / 현대적 의미
  슬라이드 23~25 (아웃트로): 요약 + 다음 영상 예고 + 구독 CTA

각 슬라이드 텍스트 작성 규칙:
  ★ 가장 중요한 규칙: 슬라이드당 반드시 400~500자 분량으로 작성할 것 (한국어 글자 수 기준, 공백 포함)
  ★ 이는 TTS 나레이션 약 1분 분량에 해당. 400자 미만이면 반드시 내용을 더 추가할 것.
  - 반드시 완전한 나레이션 문장으로 작성 (bullet point 절대 금지)
  - 자연스러운 구어체 문장 ({self.profile.tone})
  - 각 슬라이드는 앞 슬라이드에서 자연스럽게 이어지는 흐름
  - 청중에게 직접 말하는 형식 ("여러분", "생각해보세요" 등)
  - 예시, 수치, 구체적 사례를 충분히 포함해서 길이를 채울 것""",

            "youtube_shorts": f"""YouTube Shorts 대본 (30~45초):
- 첫 1.5초: 패턴 인터럽트 ("{hook}")
- 핵심 포인트 1~2개만
- 마지막: 루프 유도 또는 CTA""",

            "x": f"""X 스레드 (6~8 트윗):
- 트윗 1: 훅 ("{hook}", 더보기 전 첫 줄이 전부)
- 트윗 2~(N-1): 포인트 1개씩, 250자 이내
- 마지막 트윗: 핵심 교훈 + 팔로우/북마크 CTA
- 외부 링크는 마지막 트윗에만
- 해시태그: {self.profile.hashtag.count}개 이하""",

            "linkedin": f"""LinkedIn 텍스트 포스트 (1300자 이내):
- 첫 줄: 훅 ("{hook}", "더 보기" 전에 보이는 유일한 줄)
- 짧은 단락, 줄바꿈 활용
- 개인 경험/관점 포함
- 전문적이지만 접근 가능한 톤
- CTA: 의견 요청 or 공유 유도
- 해시태그: 3~5개 (하단에 배치)""",

            "threads": f"""Threads 포스트 (500자 이내):
- 훅: "{hook}"
- 캐주얼한 톤
- 1~2개 핵심 포인트
- 이미지/캐러셀 첨부 가능""",

            "newsletter": f"""뉴스레터 (800~1500자):
- 제목: "{hook}" 변형
- 인트로: 왜 이게 중요한지 1~2문장
- 본문: 3~5개 핵심 포인트, 각각 2~3문장
- 결론: 액션 아이템 1~2개
- PS: 다음 주 예고 or 추가 리소스""",

            "naver_blog": f"""네이버 블로그 포스트 (1500~2500자):
- SEO 최적화 제목
- 소제목(H2, H3) 활용
- 핵심 키워드 자연스럽게 배치
- 이미지 설명 태그 포함
- 본문 중간에 요약 박스""",
        }

        format_guide = format_guides.get(platform, f"{platform} 플랫폼에 적합한 포맷으로")

        lang = self.profile.language  # "ko", "en", "ja"
        LANG_NAMES = {"ko": "Korean", "en": "English", "ja": "Japanese"}
        lang_name = LANG_NAMES.get(lang, lang)

        series_prompt = ""
        if series_context:
            series_prompt = f"\n\nSeries context (reference previous episode):\n{series_context}" \
                if lang == "en" else \
                f"\n\nシリーズコンテキスト（前回参照）:\n{series_context}" \
                if lang == "ja" else \
                f"\n\n시리즈 컨텍스트 (이전 회차 참조):\n{series_context}"

        fact_correction_prompt = ""
        if fact_corrections:
            lines = "\n".join(
                f'- "{c["claim"]}" → {c["note"]}'
                for c in fact_corrections
                if c.get("status") == "disputed"
            )
            if lines:
                fact_correction_prompt = (
                    f"\n\n[FACT CORRECTIONS — 이전 팩트체크에서 발견된 오류. 반드시 수정해서 작성할 것]\n{lines}"
                )

        character_prompt = ""
        if character:
            char_name = character.get("name", "")
            char_personality = character.get("personality", "")
            char_tagline = character.get("concept", "")
            bible = character.get("bible") or {}
            char_voice = bible.get("voice_description") or character.get("voice_description", "")
            char_speaking = bible.get("speaking_style") or ""
            character_prompt = f"""
[CHARACTER NARRATOR — 반드시 이 캐릭터가 말하는 것처럼 작성할 것]
이름: {char_name}
컨셉: {char_tagline}
성격: {char_personality}
목소리: {char_voice}
말투: {char_speaking}

모든 내용을 {char_name}이(가) 시청자에게 직접 설명하는 형식으로 작성하세요.
{char_name}의 개성과 말투가 텍스트 전체에서 일관되게 드러나야 합니다.
첫 슬라이드에서 {char_name}이(가) 자기소개를 하고 주제를 제시하세요.
"""

        # YouTube는 image_prompts 제외 (토큰 절약 → body 텍스트 길이 확보, ImagePrompterAgent가 별도 생성)
        if platform == "youtube":
            json_schema = f"""Respond in JSON:
{{
  "hook": "hook text (in {lang_name})",
  "body": ["slide 1 narration (in {lang_name}, 400~500 chars)", "slide 2", ...],
  "caption": "caption text (in {lang_name})",
  "hashtags": ["hashtag1", "hashtag2"],
  "cta": "call to action text (in {lang_name})"
}}"""
        else:
            json_schema = f"""Respond in JSON:
{{
  "hook": "hook text (in {lang_name})",
  "body": ["part 1 (slide/tweet/paragraph, in {lang_name})", "part 2", ...],
  "image_prompts": [
    "detailed AI image generation prompt for slide 1",
    "detailed AI image generation prompt for slide 2",
    ...
  ],
  "caption": "caption text (in {lang_name})",
  "hashtags": ["hashtag1", "hashtag2"],
  "cta": "call to action text (in {lang_name})"
}}

image_prompts rules — write as a rich Imagen AI image generation prompt (NOT a UI design description):
- Same count as body array (1:1 match)
- Always write image_prompts in ENGLISH regardless of content language (Imagen works best with English prompts)
- 40-80 words per prompt — be specific and descriptive
- Structure: [main subject + specific details from slide] + [visual style] + [camera angle/composition] + [lighting/atmosphere]
- Pull concrete details from the slide: exact names, years, numbers, locations, objects mentioned
- Choose the most visually powerful representation for the slide's key idea
- Styles to use: cinematic photography, dramatic portrait, aerial photography, macro close-up, split-screen comparison, documentary style, infographic visualization
- Bad example: "ring chart 93%, dark background"
- Good example: "Macro close-up of 14th century Korean metal movable type characters arranged in a wooden printing frame, dramatic side lighting revealing bronze texture, dark workshop atmosphere, shallow depth of field, photorealistic 8K"
- Good example: "Split-screen: left side shows Korean scholar in Joseon-era hanbok reading ancient manuscript by candlelight, right side shows modern Korean woman in cafe using smartphone, warm vs cool lighting contrast, cinematic photography"
"""

        prompt = f"""Topic: "{topic}"
Market: {self.profile.display_name}
Language: {lang_name}
Tone: {self.profile.tone}
Info density: {self.profile.info_density}
Disclaimer: {self.profile.content_rules.disclaimer_finance}
AI disclosure: {self.profile.content_rules.ai_disclosure}

Winning content structure from research:
{research.winning_formula.content_structure}
{series_prompt}{fact_correction_prompt}{character_prompt}
Format guide:
{format_guide}

Rules:
- WRITE ENTIRELY IN {lang_name.upper()} — every word, every sentence
- Tone: {self.profile.tone}
- Use specific numbers (47.3% YES, "about 50%" NO)
- Include disclaimer if finance-related
- Include AI disclosure

{json_schema}
"""

        # YouTube 롱폼: 25슬라이드 × 400자 한국어 ≈ 8,000토큰 (image_prompts 제외로 절약)
        max_tokens = 16000 if platform == "youtube" else 4096
        result = await self.llm.generate_json(prompt, max_tokens=max_tokens)
        if result:
            body = result.get("body", [])
            image_prompts = result.get("image_prompts", [])
            # YouTube: image_prompts는 ImagePrompterAgent가 별도 생성 — 슬라이드 텍스트로 대체
            if platform == "youtube":
                image_prompts = [f"Cinematic scene for: {s[:60]}" for s in body]
            else:
                while len(image_prompts) < len(body):
                    image_prompts.append(f"슬라이드 {len(image_prompts)+1}: 텍스트 강조 타이포그래피")
            return PlatformContent(
                platform=platform,
                hook=result.get("hook", hook),
                body=body,
                image_prompts=image_prompts[:len(body)],
                caption=result.get("caption", ""),
                hashtags=result.get("hashtags", []),
                cta=result.get("cta", ""),
            )
        return None

    async def write(
        self,
        research: ResearchResult,
        hook_result: HookResult,
        target_platforms: list[str],
        series_context: str | None = None,
        fact_corrections: list[dict] | None = None,
        character: dict | None = None,
    ) -> ContentPlan:
        """전체 콘텐츠 생성 파이프라인"""
        logger.info(f"=== Copywriter Agent: '{research.topic}' 콘텐츠 생성 ===")
        logger.info(f"타겟 플랫폼: {', '.join(target_platforms)}")

        # 추천 훅 선택
        best_hook = hook_result.hooks[hook_result.recommended_hook_index]

        # 플랫폼별 독립 생성
        platform_contents = []
        for platform in target_platforms:
            # 플랫폼에 가장 적합한 훅 선택
            platform_hook = best_hook.text
            for hook in hook_result.hooks:
                if platform in hook.platform_fit:
                    platform_hook = hook.text
                    break

            logger.info(f"  [{platform}] 생성 중... (훅: {platform_hook[:30]}...)")
            content = await self._generate_platform_content(
                platform=platform,
                topic=research.topic,
                hook=platform_hook,
                research=research,
                series_context=series_context,
                fact_corrections=fact_corrections,
                character=character,
            )
            if content:
                platform_contents.append(content)
                logger.info(f"  [{platform}] 완료: {len(content.body)}개 파트")
            else:
                logger.warning(f"  [{platform}] 생성 실패")

        plan = ContentPlan(
            topic=research.topic,
            market=self.profile.market,
            master_narrative=research.winning_formula.content_structure,
            platform_contents=platform_contents,
            thumbnail_text=hook_result.thumbnail_copies[0].main_text if hook_result.thumbnail_copies else research.topic,
        )

        logger.info(f"콘텐츠 생성 완료: {len(platform_contents)}/{len(target_platforms)} 플랫폼")
        return plan
