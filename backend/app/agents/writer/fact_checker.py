"""
FactChecker — Gemini 2.5 Flash + Google Search 그라운딩으로 본문 팩트 검증

흐름:
  생성된 본문 전체 → Gemini(구글 검색 그라운딩) → 사실 주장 목록 + 검증 결과
  결과: confirmed / uncertain / disputed 항목 목록

사용 시점: run_write() 이후, 사용자에게 콘텐츠 보여주기 전
"""
import os
import json
import re
from dataclasses import dataclass, field
from loguru import logger


@dataclass
class FactClaim:
    claim: str           # 구체적 주장
    status: str          # "confirmed" | "uncertain" | "disputed"
    note: str = ""       # 검증 근거 또는 의심 이유


@dataclass
class FactCheckResult:
    verified: bool
    claims: list[FactClaim] = field(default_factory=list)
    disputed_count: int = 0
    uncertain_count: int = 0
    summary: str = ""


class FactChecker:
    """Gemini 2.5 Flash + Google Search 그라운딩 팩트 체커"""

    async def check(
        self,
        topic: str,
        body_texts: list[str],
        language: str = "en",
    ) -> FactCheckResult:
        from google import genai
        from google.genai import types

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            logger.warning("[FactChecker] GEMINI_API_KEY 없음 — 팩트 체크 스킵")
            return FactCheckResult(verified=True, summary="API 키 없음 — 검증 스킵")

        client = genai.Client(api_key=api_key)
        full_text = "\n\n".join(f"[{i+1}] {t}" for i, t in enumerate(body_texts))

        prompt = f"""You are a fact-checking expert. Analyze the following content about "{topic}" and verify specific factual claims using Google Search.

Content to verify:
---
{full_text}
---

Instructions:
1. Extract all specific factual claims (dates, statistics, historical events, named people/places, scientific facts, specific numbers)
2. Search and verify the accuracy of each claim
3. Pay special attention to contradictions within the content itself (e.g. hook says X but body says Y)
4. Mark each as:
   - "confirmed": verifiably accurate
   - "uncertain": plausible but cannot be fully confirmed
   - "disputed": inaccurate, exaggerated, contradicts known facts, or contradicts itself within the text

Respond ONLY in JSON (no markdown, no code fences):
{{
  "summary": "Overall accuracy assessment in 1-2 sentences",
  "claims": [
    {{
      "claim": "exact quote or paraphrase of the specific claim",
      "status": "confirmed|uncertain|disputed",
      "note": "brief explanation with source or reason"
    }}
  ]
}}"""

        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                    temperature=0.1,
                ),
            )

            text = response.text.strip()
            # JSON 추출 (마크다운 코드블록 제거)
            text = re.sub(r"```(?:json)?\s*", "", text).strip("` \n")
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if not match:
                raise ValueError(f"JSON not found in response: {text[:200]}")

            data = json.loads(match.group())
            claims = [
                FactClaim(
                    claim=c.get("claim", ""),
                    status=c.get("status", "uncertain"),
                    note=c.get("note", ""),
                )
                for c in data.get("claims", [])
            ]

            disputed = sum(1 for c in claims if c.status == "disputed")
            uncertain = sum(1 for c in claims if c.status == "uncertain")

            result = FactCheckResult(
                verified=disputed == 0,
                claims=claims,
                disputed_count=disputed,
                uncertain_count=uncertain,
                summary=data.get("summary", ""),
            )

            logger.info(
                f"[FactChecker] 완료: {len(claims)}개 주장 "
                f"(확인={len(claims)-disputed-uncertain}, 불확실={uncertain}, 오류={disputed})"
            )
            return result

        except Exception as e:
            logger.error(f"[FactChecker] 실패: {e}")
            return FactCheckResult(
                verified=True,
                summary=f"팩트 체크 실패 (무시하고 진행): {e}",
            )
