"""Claude API 클라이언트 (글쓰기용)"""
import json
import asyncio
from loguru import logger

import anthropic

from app.settings import settings
from app.llm.base import BaseLLMClient, LLMResponse

# Claude Sonnet 4 pricing (per million tokens)
SONNET_INPUT_PRICE = 3.0  # $/M tokens
SONNET_OUTPUT_PRICE = 15.0  # $/M tokens


class ClaudeClient(BaseLLMClient):
    def __init__(self, model: str = "claude-sonnet-4-6-20250514"):
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.model_name = model

    async def generate(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse | None:
        for attempt in range(3):
            try:
                kwargs = {
                    "model": self.model_name,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "messages": [{"role": "user", "content": prompt}],
                }
                if system:
                    kwargs["system"] = system

                response = await self.client.messages.create(**kwargs)

                input_tokens = response.usage.input_tokens
                output_tokens = response.usage.output_tokens
                cost = (input_tokens * SONNET_INPUT_PRICE + output_tokens * SONNET_OUTPUT_PRICE) / 1_000_000

                return LLMResponse(
                    text=response.content[0].text.strip(),
                    model=self.model_name,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_usd=cost,
                )
            except anthropic.RateLimitError:
                wait = 2 ** (attempt + 1)
                logger.warning(f"Claude rate limit, waiting {wait}s")
                await asyncio.sleep(wait)
            except Exception as e:
                wait = 2 ** (attempt + 1)
                logger.warning(f"Claude retry {attempt+1}/3: {e}, waiting {wait}s")
                await asyncio.sleep(wait)

        logger.error("Claude 3회 재시도 실패")
        return None

    async def generate_json(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.3,
    ) -> dict | None:
        json_prompt = f"{prompt}\n\nRespond ONLY with valid JSON. No markdown, no code blocks, no explanation."
        response = await self.generate(json_prompt, system, temperature)
        if not response:
            return None

        try:
            text = response.text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0]
            return json.loads(text)
        except json.JSONDecodeError:
            logger.error(f"Claude JSON 파싱 실패: {response.text[:200]}")
            return None
