"""LLM 팩토리 — 역할에 따라 적절한 클라이언트 반환"""
from app.llm.base import BaseLLMClient
from app.llm.gemini import GeminiClient
from app.llm.claude import ClaudeClient


def get_llm_client(role: str) -> BaseLLMClient:
    """
    역할에 따라 최적의 LLM 클라이언트 반환

    - character_design: Claude Opus 4.6 (캐릭터 IP 생성 — 깊이·창의성 최우선)
    - research: Gemini 2.5 Pro (대량 분석·추론)
    - writing: Claude Sonnet 4.6 (콘텐츠 글쓰기 — 속도·품질 균형)
    - hooksmith: Claude Sonnet 4.6 (창의적 훅 생성)
    - analysis: Gemini 2.5 Flash (성과 데이터 분석 — 비용 효율)
    """
    if role == "character_design":
        return ClaudeClient(model="claude-opus-4-5")  # IP 창작은 Opus
    elif role in ("research", "keyword_expansion"):
        return GeminiClient(model="gemini-2.5-pro")  # 분석/추론은 Pro
    elif role in ("writing", "hooksmith", "copywriting", "editing"):
        return ClaudeClient()  # 콘텐츠 글쓰기는 Sonnet 4.6
    elif role == "analysis":
        return GeminiClient(model="gemini-2.5-flash")  # 데이터 분석은 Flash
    else:
        return GeminiClient(model="gemini-2.5-flash")
