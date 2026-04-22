"""
Discord 트렌드 수집기
AI/재테크 관련 Discord 서버의 인기 메시지를 수집한다

모니터링 대상 서버 (봇을 초대해야 함):
  AI/테크: Midjourney, OpenAI, Hugging Face, LangChain
  재테크 : 국내 주식/코인 커뮤니티 서버

설정 방법:
  1. discord.com/developers 에서 앱 생성
  2. Bot 토큰 발급 → .env의 DISCORD_BOT_TOKEN에 저장
  3. 모니터링할 서버에 봇 초대
  4. 아래 CHANNELS 딕셔너리에 채널 ID 추가
"""
import os
from datetime import datetime, timedelta, timezone
import requests
from loguru import logger


# 모니터링할 Discord 채널 ID (봇이 접근 가능한 채널만)
# 채널 ID 확인 방법: Discord 설정 → 고급 → 개발자 모드 → 채널 우클릭 → ID 복사
CHANNELS = {
    "AI/테크": [
        # ("서버명", "채널ID"),
        # ("Midjourney", "989255679544348703"),  # 예시
    ],
    "재테크": [
        # ("국내 주식 서버", "채널ID"),  # 예시
    ],
}


def get_headers() -> dict:
    """Discord API 요청 헤더를 반환한다"""
    token = os.getenv("DISCORD_BOT_TOKEN", "")
    return {"Authorization": f"Bot {token}"}


def fetch_channel_messages(
    server_name: str,
    channel_id: str,
    category: str,
    hours: int = 6,
    limit: int = 50,
) -> list[dict]:
    """
    특정 채널의 최근 메시지를 수집한다

    Args:
        server_name: 서버 이름 (로깅용)
        channel_id: Discord 채널 ID
        category: 카테고리 (AI/테크 or 재테크)
        hours: 최근 몇 시간 이내 메시지만 수집
        limit: 최대 메시지 수

    Returns:
        메시지 데이터 리스트
    """
    token = os.getenv("DISCORD_BOT_TOKEN", "")
    if not token:
        logger.warning("DISCORD_BOT_TOKEN이 설정되지 않았습니다")
        return []

    try:
        url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
        params = {"limit": limit}
        response = requests.get(url, headers=get_headers(), params=params, timeout=10)

        if response.status_code == 401:
            logger.error("Discord Bot Token이 유효하지 않습니다")
            return []
        if response.status_code == 403:
            logger.warning(f"Discord 채널 접근 권한 없음: {server_name} #{channel_id}")
            return []

        response.raise_for_status()
        messages = response.json()

        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        results = []

        for msg in messages:
            # 봇 메시지 제외
            if msg.get("author", {}).get("bot"):
                continue

            # 시간 필터
            created_at = datetime.fromisoformat(
                msg["timestamp"].replace("Z", "+00:00")
            )
            if created_at < cutoff:
                continue

            content = msg.get("content", "").strip()
            if not content or len(content) < 10:
                continue

            # 반응(이모지) 수로 인기도 산정
            reactions = sum(
                r.get("count", 0) for r in msg.get("reactions", [])
            )

            results.append({
                "source": "discord",
                "keyword": content[:50],
                "server": server_name,
                "channel_id": channel_id,
                "message_id": msg["id"],
                "content": content[:200],
                "reactions": reactions,
                "volume": reactions * 5 + 10,  # 기본 점수 + 반응 가중치
                "collected_at": datetime.now().isoformat(),
                "category": category,
            })

        logger.info(f"Discord #{server_name}: {len(results)}개 수집")
        return results

    except Exception as e:
        logger.error(f"Discord 수집 실패 ({server_name}): {e}")
        return []


def collect_all() -> list[dict]:
    """설정된 모든 Discord 채널에서 트렌드를 수집한다"""
    all_results = []

    has_channels = any(channels for channels in CHANNELS.values())
    if not has_channels:
        logger.info("Discord: 모니터링 채널 미설정, 스킵")
        return []

    for category, channels in CHANNELS.items():
        for server_name, channel_id in channels:
            results = fetch_channel_messages(server_name, channel_id, category)
            all_results.extend(results)

    logger.info(f"Discord 전체 수집: {len(all_results)}개")
    return all_results


if __name__ == "__main__":
    results = collect_all()
    if not results:
        print("수집된 Discord 메시지 없음 (채널 설정 또는 Bot Token 확인)")
    for r in sorted(results, key=lambda x: x["volume"], reverse=True)[:5]:
        print(f"[{r['server']}] {r['keyword']} (반응: {r['reactions']})")
