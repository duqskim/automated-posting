"""
Gemini API 콘텐츠 생성기
트렌드 데이터를 받아 플랫폼별 콘텐츠를 생성한다
"""
import os
import time
from loguru import logger
import google.generativeai as genai


def get_client():
    """Gemini API 클라이언트를 초기화한다"""
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    return genai.GenerativeModel("gemini-2.5-flash")


def generate(prompt: str, retries: int = 3) -> str | None:
    """
    Gemini API에 프롬프트를 전송하고 응답을 반환한다

    Args:
        prompt: 생성 프롬프트
        retries: 최대 재시도 횟수

    Returns:
        생성된 텍스트 또는 None
    """
    model = get_client()

    for attempt in range(retries):
        try:
            response = model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            err_str = str(e)
            # API가 retry_delay를 알려주면 그 시간만큼 대기
            import re
            m = re.search(r"retry_delay\s*\{\s*seconds:\s*(\d+)", err_str)
            wait = int(m.group(1)) + 1 if m else 2 ** (attempt + 1)
            logger.warning(f"Gemini API 실패 ({attempt+1}/{retries}): 429 quota → {wait}초 후 재시도")
            time.sleep(wait)

    logger.error("Gemini API 최대 재시도 초과")
    return None


SYSTEM_ROLE = """
당신은 AI/재테크 인사이트를 쉽게 설명하는 한국어 콘텐츠 크리에이터입니다.
타겟: AI와 재테크를 공부하는 20~35세 한국 직장인
톤: 친근하고 명확하게, 전문용어 최소화, 존댓말(~해요 체)
제약: 투자 권유 없이 정보 전달만, 재테크 내용은 반드시 "참고용입니다" 명시
""".strip()
