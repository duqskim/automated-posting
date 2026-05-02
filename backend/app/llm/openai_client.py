"""OpenAI API 클라이언트 (글쓰기용)"""
import json
import asyncio
from loguru import logger

from openai import AsyncOpenAI

from app.settings import settings
from app.llm.base import BaseLLMClient, LLMResponse

# GPT-4o pricing (per million tokens)
GPT4O_INPUT_PRICE = 2.5   # $/M tokens
GPT4O_OUTPUT_PRICE = 10.0  # $/M tokens

# GPT-4o mini pricing
GPT4O_MINI_INPUT_PRICE = 0.15   # $/M tokens
GPT4O_MINI_OUTPUT_PRICE = 0.60  # $/M tokens

PRICE_MAP = {
    "gpt-4o": (GPT4O_INPUT_PRICE, GPT4O_OUTPUT_PRICE),
    "gpt-4o-mini": (GPT4O_MINI_INPUT_PRICE, GPT4O_MINI_OUTPUT_PRICE),
}


class OpenAIClient(BaseLLMClient):
    def __init__(self, model: str = "gpt-4o"):
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model_name = model

    async def generate(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse | None:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        for attempt in range(3):
            try:
                response = await self.client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )

                input_tokens = response.usage.prompt_tokens
                output_tokens = response.usage.completion_tokens
                in_price, out_price = PRICE_MAP.get(self.model_name, (GPT4O_INPUT_PRICE, GPT4O_OUTPUT_PRICE))
                cost = (input_tokens * in_price + output_tokens * out_price) / 1_000_000

                return LLMResponse(
                    text=response.choices[0].message.content.strip(),
                    model=self.model_name,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_usd=cost,
                )
            except Exception as e:
                wait = 2 ** (attempt + 1)
                logger.warning(f"OpenAI retry {attempt+1}/3: {e}, waiting {wait}s")
                await asyncio.sleep(wait)

        logger.error("OpenAI 3회 재시도 실패")
        return None

    async def generate_json(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> dict | None:
        json_prompt = f"{prompt}\n\nRespond ONLY with valid JSON. No markdown, no code blocks, no explanation."
        response = await self.generate(json_prompt, system, temperature, max_tokens=max_tokens)
        if not response:
            return None

        try:
            text = response.text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0]
            return json.loads(text)
        except json.JSONDecodeError:
            logger.error(f"OpenAI JSON 파싱 실패: {response.text[:200]}")
            return None
