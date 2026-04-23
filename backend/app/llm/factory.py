"""LLM 팩토리 — 역할에 따라 적절한 클라이언트 반환"""
from app.llm.base import BaseLLMClient
from app.llm.gemini import GeminiClient
from app.llm.claude import ClaudeClient


def get_llm_client(role: str) -> BaseLLMClient:
    """
    역할에 따라 최적의 LLM 클라이언트 반환

    - research: Gemini Flash (빠르고 저렴, 대량 분석)
    - writing: Claude Sonnet (한국어/영어 글쓰기 품질 최고)
    - hooksmith: Claude Sonnet (창의적 훅 생성)
    - analysis: Gemini Flash (성과 데이터 분석)
    """
    if role in ("research", "keyword_expansion"):
        return GeminiClient(model="gemini-2.5-pro")  # 분석/추론은 Pro
    elif role in ("writing", "hooksmith", "copywriting", "editing"):
        return ClaudeClient()  # 글쓰기/창의성은 Sonnet 4.6
    elif role == "analysis":
        return GeminiClient(model="gemini-2.5-flash")  # 데이터 분석은 Flash (비용 효율)
    else:
        return GeminiClient(model="gemini-2.5-flash")
