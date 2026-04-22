"""
X (Twitter) 발행기
생성된 스레드를 X API v2로 자동 발행한다

주의사항:
- Free tier: 월 1,500 트윗 한도
- 스레드는 첫 트윗 발행 후 순서대로 답글로 연결
- 외부 링크는 본문 금지 → 마지막 트윗 답글에 삽입
"""
import os
import time
from datetime import datetime
from loguru import logger
import tweepy


def get_client() -> tweepy.Client:
    """Twitter API v2 클라이언트를 반환한다"""
    return tweepy.Client(
        consumer_key=os.getenv("X_API_KEY"),
        consumer_secret=os.getenv("X_API_SECRET"),
        access_token=os.getenv("X_ACCESS_TOKEN"),
        access_token_secret=os.getenv("X_ACCESS_SECRET"),
        wait_on_rate_limit=True,
    )


def post_thread(content: dict, dry_run: bool = False) -> dict:
    """
    X 스레드를 발행한다

    Args:
        content: x_format.py에서 생성된 콘텐츠
                 {tweets: [...], hashtags: str, keyword: str}
        dry_run: True이면 실제 발행 없이 내용만 출력 (테스트용)

    Returns:
        {success: bool, tweet_ids: [...], published_at: str}
    """
    tweets = content.get("tweets", [])
    hashtags = content.get("hashtags", "")
    keyword = content.get("keyword", "")

    if not tweets:
        logger.warning(f"발행할 트윗 없음: {keyword}")
        return {"success": False, "tweet_ids": [], "published_at": None}

    # 첫 번째 트윗에 해시태그 추가
    tweets_to_post = tweets.copy()
    if hashtags:
        tweets_to_post[0] = f"{tweets_to_post[0]}\n\n{hashtags}"

    if dry_run:
        logger.info(f"[DRY RUN] X 스레드 발행 시뮬레이션: {keyword}")
        for i, tweet in enumerate(tweets_to_post, 1):
            print(f"\n[트윗{i}] ({len(tweet)}자)\n{tweet}")
        return {
            "success": True,
            "tweet_ids": [f"dry_run_{i}" for i in range(len(tweets_to_post))],
            "published_at": datetime.now().isoformat(),
        }

    client = get_client()
    tweet_ids = []
    reply_to_id = None

    for i, tweet_text in enumerate(tweets_to_post):
        try:
            if reply_to_id:
                # 이전 트윗에 답글로 연결 (스레드 구성)
                response = client.create_tweet(
                    text=tweet_text,
                    in_reply_to_tweet_id=reply_to_id,
                )
            else:
                # 첫 번째 트윗
                response = client.create_tweet(text=tweet_text)

            tweet_id = response.data["id"]
            tweet_ids.append(tweet_id)
            reply_to_id = tweet_id
            logger.info(f"트윗 {i+1}/{len(tweets_to_post)} 발행 완료: {tweet_id}")

            # 스레드 간 딜레이 (Rate Limit 방지)
            if i < len(tweets_to_post) - 1:
                time.sleep(2)

        except tweepy.TooManyRequests:
            logger.error("X API Rate Limit 초과")
            break
        except tweepy.Forbidden as e:
            logger.error(f"X API 권한 오류: {e}")
            break
        except Exception as e:
            logger.error(f"트윗 {i+1} 발행 실패: {e}")
            break

    success = len(tweet_ids) == len(tweets_to_post)
    result = {
        "success": success,
        "tweet_ids": tweet_ids,
        "published_at": datetime.now().isoformat(),
        "keyword": keyword,
    }

    if success:
        logger.info(f"X 스레드 발행 완료: {keyword} ({len(tweet_ids)}개 트윗)")
    else:
        logger.warning(f"X 스레드 부분 발행: {len(tweet_ids)}/{len(tweets_to_post)}")

    return result


def post_single_tweet(text: str, dry_run: bool = False) -> dict:
    """
    단일 트윗을 발행한다 (시황, 뉴스 요약용)

    Args:
        text: 트윗 내용 (280자 이내)
        dry_run: 테스트 모드

    Returns:
        {success: bool, tweet_id: str, published_at: str}
    """
    if len(text) > 280:
        text = text[:277] + "..."

    if dry_run:
        logger.info(f"[DRY RUN] 단일 트윗: {text[:50]}...")
        return {"success": True, "tweet_id": "dry_run", "published_at": datetime.now().isoformat()}

    try:
        client = get_client()
        response = client.create_tweet(text=text)
        tweet_id = response.data["id"]
        logger.info(f"단일 트윗 발행 완료: {tweet_id}")
        return {"success": True, "tweet_id": tweet_id, "published_at": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"단일 트윗 발행 실패: {e}")
        return {"success": False, "tweet_id": None, "published_at": None}


if __name__ == "__main__":
    # 테스트: dry_run=True로 실제 발행 없이 확인
    test_content = {
        "keyword": "ChatGPT",
        "category": "AI/테크",
        "tweets": [
            "ChatGPT가 바꾸는 직장인의 하루 🧵",
            "1/ 이메일 초안 작성: 5분 → 30초로 단축됩니다.",
            "2/ 회의 요약: 녹음 파일을 붙여넣으면 핵심만 정리해줘요.",
            "3/ 데이터 분석: 엑셀 파일을 올리면 인사이트를 바로 뽑아줍니다.",
            "4/ 번역: 영어 문서를 자연스러운 한국어로 즉시 변환.",
            "팔로우하면 매일 이런 AI 활용 인사이트를 드려요 🔔",
        ],
        "hashtags": "#AI #테크트렌드",
    }
    result = post_thread(test_content, dry_run=True)
    print(f"\n결과: {result}")
