"""
재테크 뉴스 수집기
한국경제 RSS, CoinGecko, Yahoo Finance에서 데이터를 수집한다

참고: 네이버 금융(finance.naver.com) RSS 피드는 HTML을 반환하여 사용 불가.
한국경제(hankyung.com) RSS로 대체.
"""
import io
import sys
from datetime import datetime
import feedparser
import pandas as pd
import requests
import yfinance as yf
from loguru import logger


# 한국경제 RSS 피드 (네이버 금융 RSS 대체 — 네이버는 HTML 반환으로 RSS 불가)
FINANCE_RSS_FEEDS = {
    "경제": "https://www.hankyung.com/feed/economy",
    "IT": "https://www.hankyung.com/feed/it",
}

# 주요 주식 심볼 (한국 + 미국 AI 관련)
STOCK_SYMBOLS = {
    "한국": ["005930.KS", "000660.KS", "035420.KS"],  # 삼성전자, SK하이닉스, NAVER
    "미국 AI": ["NVDA", "MSFT", "GOOGL", "META", "AMZN"],
}

# CoinGecko 주요 코인
COINS = ["bitcoin", "ethereum", "solana"]


def fetch_finance_news(limit: int = 10) -> list[dict]:
    """한국경제 RSS에서 최신 재테크/IT 뉴스를 수집한다"""
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
    results = []

    for topic, url in FINANCE_RSS_FEEDS.items():
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            feed = feedparser.parse(resp.text)
            for entry in feed.entries[:limit]:
                title = entry.get("title", "").strip()
                if not title:
                    continue
                results.append({
                    "source": "hankyung",
                    "keyword": title[:50],
                    "title": title,
                    "topic": topic,
                    "url": entry.get("link", ""),
                    "volume": 50,  # 뉴스 기본 점수
                    "collected_at": datetime.now().isoformat(),
                    "category": "재테크" if topic == "경제" else "AI/테크",
                })
            logger.info(f"한국경제 {topic} 수집: {len(feed.entries[:limit])}개")
        except Exception as e:
            logger.error(f"한국경제 RSS 수집 실패 ({topic}): {e}")

    return results


def fetch_coingecko() -> list[dict]:
    """CoinGecko API에서 코인 시황을 수집한다 (API 키 불필요)"""
    try:
        url = "https://api.coingecko.com/api/v3/coins/markets"
        params = {
            "vs_currency": "krw",
            "ids": ",".join(COINS),
            "order": "market_cap_desc",
            "price_change_percentage": "24h",
        }
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        results = []
        for coin in data:
            change = coin.get("price_change_percentage_24h", 0) or 0
            # 변동률이 클수록 volume 높게 산정
            volume = min(100, abs(change) * 10)
            results.append({
                "source": "coingecko",
                "keyword": coin["name"],
                "symbol": coin["symbol"].upper(),
                "price_krw": coin["current_price"],
                "change_24h": round(change, 2),
                "volume": volume,
                "collected_at": datetime.now().isoformat(),
                "category": "재테크",
            })

        logger.info(f"CoinGecko 수집 완료: {len(results)}개 코인")
        return results

    except Exception as e:
        logger.error(f"CoinGecko 수집 실패: {e}")
        return []


def fetch_yahoo_finance() -> list[dict]:
    """Yahoo Finance에서 주요 주식 데이터를 배치로 수집한다"""
    all_symbols = [s for symbols in STOCK_SYMBOLS.values() for s in symbols]

    try:
        # yfinance가 rate limit 에러를 stdout/stderr로 출력하므로 억제
        _stdout, _stderr = sys.stdout, sys.stderr
        sys.stdout = sys.stderr = io.StringIO()
        try:
            df = yf.download(
                tickers=" ".join(all_symbols),
                period="2d",
                interval="1d",
                progress=False,
                auto_adjust=True,
            )
        finally:
            sys.stdout, sys.stderr = _stdout, _stderr

        if df.empty:
            logger.warning("Yahoo Finance 배치 수집: 데이터 없음 (rate limit 가능성)")
            return []

        results = []
        close = df["Close"]

        # MultiIndex DataFrame: close[symbol] 접근
        # 단일 심볼 성공 시 close가 Series가 될 수 있으므로 안전하게 처리
        if isinstance(close, pd.DataFrame):
            available_symbols = close.columns.tolist()
        else:
            available_symbols = []

        for symbol in all_symbols:
            try:
                if symbol not in available_symbols:
                    continue
                prices = close[symbol].dropna()
                if len(prices) < 2:
                    continue
                prev, last = float(prices.iloc[-2]), float(prices.iloc[-1])
                change_pct = (last - prev) / prev * 100 if prev else 0
                volume = min(100, abs(change_pct) * 10)
                results.append({
                    "source": "yahoo_finance",
                    "keyword": symbol,
                    "price": round(last, 2),
                    "change_pct": round(change_pct, 2),
                    "volume": volume,
                    "collected_at": datetime.now().isoformat(),
                    "category": "재테크",
                })
            except Exception:
                continue

        logger.info(f"Yahoo Finance 수집 완료: {len(results)}개 종목")
        return results

    except Exception as e:
        logger.warning(f"Yahoo Finance 수집 실패: {e}")
        return []


def collect_all() -> list[dict]:
    """모든 재테크 뉴스/시황을 수집한다"""
    results = []
    results.extend(fetch_finance_news())
    results.extend(fetch_coingecko())
    results.extend(fetch_yahoo_finance())
    logger.info(f"재테크 뉴스 전체 수집: {len(results)}개")
    return results


if __name__ == "__main__":
    results = collect_all()
    for r in sorted(results, key=lambda x: x["volume"], reverse=True)[:5]:
        print(f"[{r['source']}] {r['keyword']}: volume={r['volume']}")
