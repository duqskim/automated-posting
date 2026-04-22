"""
Engager Agent — 댓글 모니터링 + 답변 초안 추천
역할: 발행 후 댓글 수집 → 알림 → 답변 초안 (자동 답변 ✕)
"""
from dataclasses import dataclass, field
from loguru import logger

from app.llm.factory import get_llm_client
from app.config.market_profile import MarketProfile


@dataclass
class Comment:
    platform: str
    post_id: str
    comment_id: str
    author: str
    text: str
    timestamp: str
    sentiment: str | None = None  # positive, negative, question, neutral


@dataclass
class ReplyDraft:
    comment_id: str
    draft_text: str
    tone: str
    auto_post: bool = False  # 항상 False (자동 답변 안 함)


@dataclass
class EngagerResult:
    comments: list[Comment] = field(default_factory=list)
    reply_drafts: list[ReplyDraft] = field(default_factory=list)
    alert_count: int = 0


class EngagerAgent:
    """댓글 모니터링 + 답변 초안 에이전트"""

    def __init__(self, market_profile: MarketProfile):
        self.profile = market_profile
        self.llm = get_llm_client("writing")

    async def classify_comment(self, comment: Comment) -> str:
        """댓글 분류 (question, positive, negative, neutral)"""
        question_markers = {
            "ko": ["?", "어떻게", "뭔가요", "알려주세요", "궁금", "방법"],
            "en": ["?", "how", "what", "why", "can you", "please explain"],
            "ja": ["?", "ですか", "教えて", "どう", "なぜ"],
        }
        negative_markers = {
            "ko": ["별로", "아닌데", "틀렸", "에바", "ㅋㅋ"],
            "en": ["wrong", "disagree", "not true", "terrible", "bad"],
            "ja": ["違う", "間違い", "ダメ"],
        }

        markers = question_markers.get(self.profile.language, [])
        neg_markers = negative_markers.get(self.profile.language, [])

        text_lower = comment.text.lower()

        if any(m in text_lower for m in markers):
            return "question"
        if any(m in text_lower for m in neg_markers):
            return "negative"
        return "neutral"

    async def generate_reply_draft(self, comment: Comment) -> ReplyDraft:
        """댓글 답변 초안 생성"""
        prompt = f"""플랫폼: {comment.platform}
댓글: "{comment.text}"
댓글 유형: {comment.sentiment}
우리 계정 톤: {self.profile.tone}
언어: {self.profile.language}

이 댓글에 대한 답변 초안을 작성해주세요.
- 톤: {self.profile.tone}
- 2~3문장 이내
- 질문이면 도움이 되는 답변
- 부정적이면 정중하게 대응
- 긍정적이면 감사 + 추가 가치 제공

답변 텍스트만 작성 (JSON 아님)."""

        response = await self.llm.generate(prompt, temperature=0.6, max_tokens=200)

        return ReplyDraft(
            comment_id=comment.comment_id,
            draft_text=response.text if response else "감사합니다!",
            tone=comment.sentiment or "neutral",
            auto_post=False,  # 절대 자동 답변 안 함
        )

    async def monitor(self, post_ids: dict[str, str]) -> EngagerResult:
        """댓글 모니터링 (현재는 구조만, API 연동 추후)"""
        logger.info(f"=== Engager: {len(post_ids)}개 포스트 댓글 모니터링 ===")

        # TODO: 각 플랫폼 API로 댓글 수집
        # post_ids: {"instagram": "post_123", "x": "tweet_456", ...}

        result = EngagerResult()
        logger.info(f"Engager: {result.alert_count}개 알림, "
                     f"{len(result.reply_drafts)}개 답변 초안")
        return result
