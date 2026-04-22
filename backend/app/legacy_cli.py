"""
automated-posting 레거시 CLI
shadow-meteorite에서 분리한 기존 파이프라인 (트렌드 수집 → 생성 → 발행)
새 웹 시스템 완성 전까지 CLI로 사용 가능
"""
from dotenv import load_dotenv
load_dotenv()

from loguru import logger
from app.agents.research.collectors import google_trends, hacker_news, finance_news, naver_trends, discord_trends
from app.agents.research.analyzer.trend_scorer import get_top_trends
from app.agents.writer.generator.instagram_format import generate_carousel
from app.agents.writer.generator.x_format import generate_thread
from app.agents.publisher.legacy.x_publisher import post_thread


def collect_all_trends() -> list[dict]:
    """모든 수집기에서 트렌드를 수집한다"""
    logger.info("=== 트렌드 수집 시작 ===")
    all_trends = []
    all_trends.extend(google_trends.collect_all())
    all_trends.extend(hacker_news.collect_all())
    all_trends.extend(finance_news.collect_all())
    all_trends.extend(naver_trends.collect_all())
    all_trends.extend(discord_trends.collect_all())
    logger.info(f"전체 수집 완료: {len(all_trends)}개")
    return all_trends


def generate_contents(top_trends: dict) -> dict:
    """선정된 트렌드로 플랫폼별 콘텐츠를 생성한다"""
    logger.info("=== 콘텐츠 생성 시작 ===")

    instagram_contents = []
    for trend in top_trends["instagram"]:
        content = generate_carousel(trend)
        if content:
            instagram_contents.append(content)
            logger.info(f"Instagram 캐러셀 생성: {trend['keyword']} ({content['slide_count']}장)")

    x_contents = []
    for trend in top_trends["x"]:
        content = generate_thread(trend)
        if content:
            x_contents.append(content)
            logger.info(f"X 스레드 생성: {trend['keyword']} ({content['tweet_count']}개)")

    return {"instagram": instagram_contents, "x": x_contents}


def publish_x(contents: list[dict], dry_run: bool = False) -> None:
    """X 콘텐츠를 발행한다"""
    logger.info("=== X 발행 시작 ===")
    for content in contents:
        result = post_thread(content, dry_run=dry_run)
        if result["success"]:
            logger.info(f"X 발행 완료: {content['keyword']}")
        else:
            logger.warning(f"X 발행 실패: {content['keyword']}")


def main(dry_run: bool = False):
    logger.info(f"automated-posting CLI 시작 {'[DRY RUN]' if dry_run else ''}")

    # 1. 트렌드 수집
    raw_trends = collect_all_trends()

    # 2. 분석 및 우선순위 선정
    top_trends = get_top_trends(raw_trends)

    # 3. 콘텐츠 생성
    contents = generate_contents(top_trends)
    logger.info(f"생성 완료 — Instagram: {len(contents['instagram'])}개, X: {len(contents['x'])}개")

    # 4. X 발행
    publish_x(contents["x"], dry_run=dry_run)


if __name__ == "__main__":
    import sys
    dry_run = "--dry-run" in sys.argv
    main(dry_run=dry_run)
