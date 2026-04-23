"""
엔드투엔드 파이프라인 테스트
주제 입력 → Researcher → Hooksmith → Copywriter → Quality Gate → Creative Director → 이미지 렌더링

실행: cd backend && PYTHONPATH=. python tests/test_e2e_pipeline.py
"""
import asyncio
import json
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

from app.config.market_profile import load_market_profile
from app.agents.research.agent import ResearcherAgent
from app.agents.research.hooksmith import HooksmithAgent
from app.agents.writer.copywriter import CopywriterAgent
from app.agents.writer.quality_gate import QualityGate
from app.agents.media.creative_director import CreativeDirectorAgent
from app.agents.media.design_reviewer import DesignReviewerAgent

from jinja2 import Environment, FileSystemLoader
from playwright.async_api import async_playwright

TEMPLATE_DIR = Path(__file__).parents[1] / "app" / "agents" / "media" / "image_renderer" / "templates"
OUTPUT_DIR = Path(__file__).parents[1] / "output" / "e2e_test"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

jinja_env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))


def divider(title: str):
    print(f"\n{'━' * 20} {title} {'━' * (50 - len(title))}")


async def main():
    topic = "ISA 계좌 절세 전략"
    market = "kr"

    profile = load_market_profile(market)
    print(f"\n주제: {topic}")
    print(f"시장: {profile.display_name} ({profile.language})")
    print(f"플랫폼: {', '.join(profile.active_platforms)}")

    # ─── Stage 1: Research ───
    divider("Stage 1: RESEARCH")
    researcher = ResearcherAgent(profile)
    research = await researcher.research(topic)

    print(f"키워드 {len(research.keywords)}개: {research.keywords[:5]}...")
    print(f"상위 콘텐츠 {len(research.top_content)}개 분석")
    print(f"훅 패턴: {research.winning_formula.hook_patterns[:3]}")
    print(f"빈틈: {research.winning_formula.content_gaps[:2]}")

    # ─── Stage 2: Hooksmith ───
    divider("Stage 2: HOOKSMITH")
    hooksmith = HooksmithAgent(profile)
    hooks = await hooksmith.generate_hooks(research)

    for i, hook in enumerate(hooks.hooks):
        marker = " ★" if i == hooks.recommended_hook_index else ""
        print(f"  [{hook.style}] {hook.text}{marker}")
    print(f"  썸네일: {hooks.thumbnail_copies[0].main_text if hooks.thumbnail_copies else 'N/A'}")

    # ─── Stage 3: Copywriter (Instagram만 테스트) ───
    divider("Stage 3: COPYWRITER")
    copywriter = CopywriterAgent(profile)
    content_plan = await copywriter.write(
        research=research,
        hook_result=hooks,
        target_platforms=["instagram"],
    )

    ig_content = content_plan.platform_contents[0] if content_plan.platform_contents else None
    if ig_content:
        print(f"  플랫폼: {ig_content.platform}")
        print(f"  훅: {ig_content.hook}")
        print(f"  슬라이드: {len(ig_content.body)}장")
        for i, slide in enumerate(ig_content.body[:3], 1):
            print(f"    [{i}] {slide[:60]}...")
        print(f"  해시태그: {ig_content.hashtags}")
        print(f"  CTA: {ig_content.cta}")
    else:
        print("  콘텐츠 생성 실패!")
        return

    # ─── Stage 4: Quality Gate ───
    divider("Stage 4: QUALITY GATE")
    gate = QualityGate(profile)
    quality = gate.evaluate(content_plan)

    print(f"  점수: {quality.score}/100 — {'PASS' if quality.passed else 'FAIL'}")
    for issue in quality.issues[:5]:
        print(f"  [{issue.severity}] {issue.category}: {issue.message}")

    # ─── Stage 5: Creative Director ───
    divider("Stage 5: CREATIVE DIRECTOR")
    cd = CreativeDirectorAgent(profile, brand={"handle": "@allai0011"})
    design_plan = await cd.plan_design(ig_content, content_plan)

    print(f"  테마: {design_plan.theme_name}")
    print(f"  캔버스: {design_plan.canvas_size}")
    for slide in design_plan.slides:
        print(f"  슬라이드 {slide.slide_index}: [{slide.content_type}] → {slide.template_name}")

    # ─── Stage 6: 이미지 렌더링 ───
    divider("Stage 6: IMAGE RENDERING")
    rendered_files = []

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport=design_plan.canvas_size)

        for slide in design_plan.slides:
            template_file = f"{slide.template_name}.html"
            try:
                template = jinja_env.get_template(template_file)
            except Exception:
                # 폴백: editorial
                template = jinja_env.get_template("editorial.html")

            html = template.render(**slide.template_data)
            await page.set_content(html, wait_until="networkidle")
            await page.wait_for_timeout(1000)

            filename = OUTPUT_DIR / f"slide_{slide.slide_index:02d}_{slide.template_name}.png"
            await page.screenshot(
                path=str(filename),
                clip={"x": 0, "y": 0, **design_plan.canvas_size},
            )
            rendered_files.append(filename)
            size_kb = filename.stat().st_size / 1024
            print(f"  {slide.slide_index}/{len(design_plan.slides)} [{slide.template_name}] → {size_kb:.0f}KB")

        await browser.close()

    # ─── Stage 7: Design Review ───
    divider("Stage 7: DESIGN REVIEW")
    reviewer = DesignReviewerAgent()
    review = reviewer.review(design_plan, rendered_files)

    print(f"  점수: {review.score}/100 — {'PASS' if review.passed else 'FAIL'}")
    for issue in review.issues[:5]:
        print(f"  [{issue.severity}] {issue.category}: {issue.message}")

    # ─── 결과 요약 ───
    divider("RESULT")
    print(f"  주제: {topic}")
    print(f"  시장: {profile.display_name}")
    print(f"  훅: {hooks.hooks[hooks.recommended_hook_index].text}")
    print(f"  슬라이드: {len(rendered_files)}장")
    print(f"  콘텐츠 품질: {quality.score}/100")
    print(f"  디자인 품질: {review.score}/100")
    print(f"  출력: {OUTPUT_DIR}")
    print(f"\n  확인: open {OUTPUT_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
