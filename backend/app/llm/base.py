"""LLM 클라이언트 추상 인터페이스"""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class LLMResponse:
    text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


class BaseLLMClient(ABC):
    """LLM 클라이언트 공통 인터페이스"""

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse | None:
        pass

    @abstractmethod
    async def generate_json(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.3,
    ) -> dict | None:
        """JSON 구조화 출력"""
        pass
