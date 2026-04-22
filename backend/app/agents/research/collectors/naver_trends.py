"""
네이버 트렌드 수집기
네이버 DataLab API와 한국 IT/재테크 뉴스 RSS에서 트렌드를 수집한다

API 키 발급: developers.naver.com → Application 등록
  - 검색 API 선택
  - Client ID, Client Secret 발급
"""
import os
from datetime import datetime, timedelta
import requests
import feedparser
from loguru import logger


# 한국 IT/재테크 뉴스 RSS (에펨코리아 대체 — JS 렌더링으로 RSS 불가)
KOREAN_NEWS_RSS = [
    ("매경 IT·모바일", "https://www.mk.co.kr/rss/50200011/", "AI/테크"),
    ("매경 경제일반",  "https://www.mk.co.kr/rss/30000001/", "재테크"),
    ("테크42",        "https://www.tech42.co.kr/feed/",       "AI/테크"),
]

# 네이버 DataLab 검색어 트렌드 API
NAVER_DATALAB_URL = "https://openapi.naver.com/v1/datalab/search"

# 추적할 키워드 그룹
NAVER_KEYWORD_GROUPS = {
    "AI/테크": [
        {"groupName": "AI", "keywords": ["AI", "인공지능", "ChatGPT", "클로드", "제미나이"]},
        {"groupName": "테크", "keywords": ["스타트업", "앱", "IT", "개발자", "코딩"]},
    ],
    "재테크": [
        {"groupName": "투자", "keywords": ["ETF", "주식", "코인", "비트코인", "배당"]},
        {"groupName": "절약", "keywords": ["재테크", "절약", "ISA", "청약", "적금"]},
    ],
}


def fetch_naver_datalab(keyword_group: dict, category: str) -> list[dict]:
    """
    네이버 DataLab 검색어 트렌드를 수집한다

    Args:
        keyword_group: {"groupName": str, "keywords": [...]}
        category: AI/테크 or 재테크

    Returns:
        트렌드 데이터 리스트
    """
    client_id = os.getenv("NAVER_CLIENT_ID", "")
    client_secret = os.getenv("NAVER_CLIENT_SECRET", "")

    if not client_id or not client_secret:
        logger.warning("NAVER_CLIENT_ID/SECRET 미설정, 스킵")
        return []

    today = datetime.now().strftime("%Y-%m-%d")
    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

    body = {
        "startDate": week_ago,
        "endDate": today,
        "timeUnit": "date",
        "keywordGroups": [keyword_group],
        "device": "mo",  # 모바일 (MZ세대 주 사용 기기)
        "ages": ["3", "4", "5"],  # 20대~30대
    }

    try:
        response = requests.post(
            NAVER_DATALAB_URL,
            headers={
                "X-Naver-Client-Id": client_id,
                "X-Naver-Client-Secret": client_secret,
                "Content-Type": "application/json",
            },
            json=body,
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()

        results = []
        for result in data.get("results", []):
            # 최근 데이터의 평균 ratio를 volume으로 사용
            recent_data = result.get("data", [])[-3:]
            avg_ratio = sum(d["ratio"] for d in recent_data) / len(recent_data) if recent_data else 0

            results.append({
                "source": "naver_datalab",
                "keyword": result["title"],
                "volume": avg_ratio,
                "collected_at": datetime.now().isoformat(),
                "category": category,
            })

        logger.info(f"네이버 DataLab [{keyword_group['groupName']}] 수집: {len(results)}개")
        return results

    except Exception as e:
        logger.error(f"네이버 DataLab 수집 실패: {e}")
        return []


def fetch_korean_news() -> list[dict]:
    """한국 IT/재테크 뉴스 RSS에서 최신 기사를 수집한다"""
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
    all_results = []

    for source_name, url, category in KOREAN_NEWS_RSS:
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            feed = feedparser.parse(resp.text)

            for entry in feed.entries[:15]:
                title = entry.get("title", "").strip()
                if not title:
                    continue

                all_results.append({
                    "source": source_name,
                    "keyword": title[:50],
                    "title": title,
                    "url": entry.get("link", ""),
                    "volume": 40,
                    "collected_at": datetime.now().isoformat(),
                    "category": category,
                })

            logger.info(f"{source_name} 수집: {len(feed.entries[:15])}개")

        except Exception as e:
            logger.error(f"{source_name} 수집 실패: {e}")

    return all_results


def collect_all() -> list[dict]:
    """네이버 DataLab + 한국 뉴스 RSS 전체 수집"""
    all_results = []

    # 네이버 DataLab
    for category, groups in NAVER_KEYWORD_GROUPS.items():
        for group in groups:
            results = fetch_naver_datalab(group, category)
            all_results.extend(results)

    # 한국 IT/재테크 뉴스 RSS
    all_results.extend(fetch_korean_news())

    logger.info(f"네이버/뉴스RSS 전체 수집: {len(all_results)}개")
    return all_results


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    results = collect_all()
    for r in sorted(results, key=lambda x: x["volume"], reverse=True)[:5]:
        print(f"[{r['source']}] [{r['category']}] {r['keyword']} (volume: {r['volume']})")
