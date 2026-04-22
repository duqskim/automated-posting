"""
automated-posting 검토 모드 (레거시 CLI)
shadow-meteorite에서 분리 — 수집된 트렌드와 생성된 콘텐츠를 발행 전에 확인

실행: python -m app.legacy_review
"""
from dotenv import load_dotenv
load_dotenv()

from app.agents.research.collectors import google_trends, hacker_news, finance_news, naver_trends, discord_trends
from app.agents.research.analyzer.trend_scorer import get_top_trends
from app.agents.writer.generator.instagram_format import generate_carousel
from app.agents.writer.generator.x_format import generate_thread


def divider(title: str = ""):
    width = 60
    if title:
        print(f"\n{'━' * 20} {title} {'━' * (width - len(title) - 22)}")
    else:
        print("━" * width)


def step1_collect() -> list[dict]:
    """Step 1: 트렌드 수집 결과 출력"""
    divider("STEP 1. 트렌드 수집")

    all_trends = []
    sources = {
        "Google Trends": google_trends.collect_all,
        "Hacker News":   hacker_news.collect_all,
        "재테크 뉴스":    finance_news.collect_all,
        "네이버/에펨코리아": naver_trends.collect_all,
        "Discord":       discord_trends.collect_all,
    }

    for name, collector in sources.items():
        try:
            results = collector()
            all_trends.extend(results)
            print(f"  OK {name}: {len(results)}개 수집")
        except Exception as e:
            print(f"  FAIL {name}: 실패 ({e})")

    print(f"\n  총 수집: {len(all_trends)}개")
    return all_trends


def step2_analyze(raw_trends: list[dict]) -> dict:
    divider("STEP 2. 트렌드 분석 (상위 선정)")

    top = get_top_trends(raw_trends)

    print("\n  Instagram 발행 예정:")
    for i, t in enumerate(top["instagram"], 1):
        print(f"    {i}. [{t['category']}] {t['keyword']} "
              f"(점수: {t['final_score']}, 출처: {t['source']})")

    print("\n  X 발행 예정:")
    for i, t in enumerate(top["x"], 1):
        print(f"    {i}. [{t['category']}] {t['keyword']} "
              f"(점수: {t['final_score']}, 출처: {t['source']})")

    return top


def step3_generate(top_trends: dict) -> dict:
    divider("STEP 3. 콘텐츠 생성 (Gemini API)")

    instagram_contents = []
    x_contents = []

    print("\n  Instagram 캐러셀:")
    for trend in top_trends["instagram"]:
        print(f"\n  생성 중: [{trend['category']}] {trend['keyword']}...")
        content = generate_carousel(trend)
        if content:
            instagram_contents.append(content)
            print(f"  OK {content['slide_count']}장 생성 완료")
            for i, slide in enumerate(content["slides"], 1):
                print(f"\n    [슬라이드{i}]\n    {slide.replace(chr(10), chr(10)+'    ')}")
            print(f"\n    [캡션]\n    {content['caption']}")
            print(f"\n    [해시태그] {content['hashtags']}")
        else:
            print("  FAIL 생성 실패")

    divider()

    print("\n  X 스레드:")
    for trend in top_trends["x"]:
        print(f"\n  생성 중: [{trend['category']}] {trend['keyword']}...")
        content = generate_thread(trend)
        if content:
            x_contents.append(content)
            print(f"  OK {content['tweet_count']}개 트윗 생성 완료")
            for i, tweet in enumerate(content["tweets"], 1):
                print(f"\n    [트윗{i}] ({len(tweet)}자)\n    {tweet}")
            print(f"\n    [해시태그] {content['hashtags']}")
        else:
            print("  FAIL 생성 실패")

    return {"instagram": instagram_contents, "x": x_contents}


def main():
    print("\nautomated-posting 검토 모드")
    print("발행 전에 모든 단계를 눈으로 확인합니다.\n")

    raw_trends = step1_collect()
    if not raw_trends:
        print("\n수집된 트렌드가 없습니다. 종료합니다.")
        return

    top_trends = step2_analyze(raw_trends)

    print("\n콘텐츠를 생성하시겠습니까? (Gemini API 호출)")
    if input("  [y/n]: ").strip().lower() != "y":
        print("종료합니다.")
        return

    contents = step3_generate(top_trends)

    divider("STEP 4. 발행 확인")
    print(f"\n  생성된 콘텐츠:")
    print(f"    Instagram: {len(contents['instagram'])}개")
    print(f"    X:         {len(contents['x'])}개")

    print("\n  이 콘텐츠를 지금 발행할까요?")
    print("  [y] 발행  [n] 취소  [d] dry-run")

    choice = input("\n  선택: ").strip().lower()

    if choice == "y":
        from app.agents.publisher.legacy.x_publisher import post_thread
        print("\nX 발행 시작...")
        for content in contents["x"]:
            result = post_thread(content, dry_run=False)
            status = "OK" if result["success"] else "FAIL"
            print(f"  {status} {content['keyword']}")
        print("\n완료!")

    elif choice == "d":
        from app.agents.publisher.legacy.x_publisher import post_thread
        print("\nX Dry-run 실행...")
        for content in contents["x"]:
            post_thread(content, dry_run=True)

    else:
        print("\n취소됐습니다.")


if __name__ == "__main__":
    main()
