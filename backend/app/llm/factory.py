"""LLM 팩토리 — 역할에 따라 적절한 클라이언트 반환"""
from app.llm.base import BaseLLMClient
from app.llm.gemini import GeminiClient
from app.llm.openai_client import OpenAIClient


def get_llm_client(role: str) -> BaseLLMClient:
    """
    역할에 따라 최적의 LLM 클라이언트 반환

    - character_design: Gemini 2.5 Pro (캐릭터 IP 생성)
    - research: Gemini 2.5 Pro (대량 분석·추론)
    - hooksmith: Gemini 2.5 Pro (창의적 훅 생성)
    - writing: Gemini 2.5 Pro (콘텐츠 글쓰기)
    - analysis: Gemini 2.5 Flash (성과 데이터 분석 — 비용 효율)
    """
    if role == "character_design":
        return GeminiClient(model="gemini-2.5-pro")
    elif role in ("research", "keyword_expansion"):
        return GeminiClient(model="gemini-2.5-pro")
    elif role in ("writing", "hooksmith", "copywriting", "editing"):
        return GeminiClient(model="gemini-2.5-pro")
    elif role == "analysis":
        return GeminiClient(model="gemini-2.5-flash")
    else:
        return GeminiClient(model="gemini-2.5-flash")
