"""Gemini API 클라이언트 (리서치용)"""
import json
import asyncio
from loguru import logger

import google.generativeai as genai

from app.settings import settings
from app.llm.base import BaseLLMClient, LLMResponse


class GeminiClient(BaseLLMClient):
    def __init__(self, model: str = "gemini-2.5-pro"):
        genai.configure(api_key=settings.gemini_api_key)
        self.model_name = model
        self._model = genai.GenerativeModel(model)

    async def generate(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse | None:
        full_prompt = f"{system}\n\n{prompt}" if system else prompt

        for attempt in range(3):
            try:
                response = await asyncio.to_thread(
                    self._model.generate_content,
                    full_prompt,
                    generation_config=genai.GenerationConfig(
                        temperature=temperature,
                        max_output_tokens=max_tokens,
                    ),
                )
                return LLMResponse(
                    text=response.text.strip(),
                    model=self.model_name,
                )
            except Exception as e:
                wait = 2 ** (attempt + 1)
                logger.warning(f"Gemini retry {attempt+1}/3: {e}, waiting {wait}s")
                await asyncio.sleep(wait)

        logger.error("Gemini 3회 재시도 실패")
        return None

    async def generate_json(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> dict | None:
        json_prompt = f"{prompt}\n\nRespond ONLY with valid JSON. No markdown, no code blocks."
        response = await self.generate(json_prompt, system, temperature, max_tokens=max_tokens)
        if not response:
            return None

        try:
            text = response.text.strip()
            # 마크다운 코드블록 제거
            if text.startswith("```"):
                text = text.split("\n", 1)[1]
                if "```" in text:
                    text = text.rsplit("```", 1)[0]
            text = text.strip()
            return json.loads(text)
        except json.JSONDecodeError:
            # 응답이 잘린 경우 마지막 완전한 JSON 객체까지만 복구 시도
            try:
                text = response.text.strip()
                if text.startswith("```"):
                    text = text.split("\n", 1)[1]
                # 열린 브라켓 수만큼 닫기
                open_braces = text.count("{") - text.count("}")
                open_brackets = text.count("[") - text.count("]")
                if open_braces > 0 or open_brackets > 0:
                    text = text.rstrip(",\n ")
                    text += "]" * open_brackets + "}" * open_braces
                    return json.loads(text)
            except Exception:
                pass
            logger.error(f"Gemini JSON 파싱 실패: {response.text[:200]}")
            return None
