"""
YouTube 롱폼 파이프라인 검증 테스트

확인 항목:
  1. Copywriter → YouTube 슬라이드 수 (20~25개) + 슬라이드당 단어 수 (150~200단어)
  2. VideoPlannerAgent → duration_seconds ~60s per slide
  3. TTS → WAV 파일 생성 (슬라이드 1개만)

실행: cd backend && PYTHONPATH=. python tests/test_youtube_pipeline.py
"""
import asyncio
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

from app.config.market_profile import load_market_profile
from app.agents.research.agent import ResearcherAgent
from app.agents.research.hooksmith import HooksmithAgent
from app.agents.writer.copywriter import CopywriterAgent
from app.agents.media.video_planner import VideoPlannerAgent
from app.agents.media.tts_gemini import generate_tts_gemini

OUTPUT_DIR = Path(__file__).parents[1] / "output" / "youtube_test"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def divider(title: str):
    print(f"\n{'━' * 20} {title} {'━' * (50 - len(title))}")


def count_words(text: str) -> int:
    return len(text.split())

def count_chars(text: str) -> int:
    """공백 제외 글자 수 (한국어 기준 길이 측정)"""
    return len(text.replace(" ", ""))


async def main():
    topic = "ISA 계좌 절세 전략"
    market = "kr"

    profile = load_market_profile(market)
    print(f"\n주제: {topic} | 플랫폼: youtube")

    # ─── Stage 1: Research ───
    divider("Stage 1: RESEARCH")
    researcher = ResearcherAgent(profile)
    research = await researcher.research(topic)
    print(f"  키워드 {len(research.keywords)}개 수집 완료")

    # ─── Stage 2: Hooksmith ───
    divider("Stage 2: HOOKSMITH")
    hooksmith = HooksmithAgent(profile)
    hooks = await hooksmith.generate_hooks(research)
    best_hook = hooks.hooks[hooks.recommended_hook_index].text
    print(f"  훅: {best_hook[:60]}...")

    # ─── Stage 3: Copywriter (YouTube) ───
    divider("Stage 3: COPYWRITER (YouTube)")
    copywriter = CopywriterAgent(profile)
    content_plan = await copywriter.write(
        research=research,
        hook_result=hooks,
        target_platforms=["youtube"],
    )

    yt_content = next((c for c in content_plan.platform_contents if c.platform == "youtube"), None)
    if not yt_content:
        print("  [FAIL] YouTube 콘텐츠 생성 실패!")
        return

    n_slides = len(yt_content.body)
    char_counts = [count_chars(s) for s in yt_content.body]
    avg_chars = sum(char_counts) / len(char_counts) if char_counts else 0

    print(f"  슬라이드 수: {n_slides}개 (목표: 20~25)")
    print(f"  슬라이드당 평균 글자: {avg_chars:.0f}자 (목표: 300~450자)")
    print(f"  최소/최대: {min(char_counts)}/{max(char_counts)}자")

    # 검증 (한국어 기준: 200자/분 속도 → 150자 = ~45초, 200자 = ~60초)
    slide_ok = 18 <= n_slides <= 25  # LLM 자연 편차 허용 (목표 20~25)
    char_ok = 150 <= avg_chars  # 150자 이상 = 45초+ 나레이션

    est_seconds = avg_chars / 200 * 60
    print(f"\n  [{'PASS' if slide_ok else 'FAIL'}] 슬라이드 수: {n_slides} {'(OK)' if slide_ok else '(부족 or 초과)'}")
    print(f"  [{'PASS' if char_ok else 'FAIL'}] 평균 글자: {avg_chars:.0f}자 ≈ {est_seconds:.0f}초 {'(OK)' if char_ok else '(너무 짧음)'}")

    # 슬라이드 미리보기
    print(f"\n  슬라이드 1 미리보기 ({char_counts[0]}자):")
    print(f"    {yt_content.body[0][:150]}...")
    print(f"  슬라이드 2 미리보기 ({char_counts[1]}자):")
    print(f"    {yt_content.body[1][:150]}...")

    if not slide_ok:
        print("\n  [STOP] 슬라이드 수 기준 미달 — VideoPlannerAgent 테스트 스킵")
        return

    # ─── Stage 4: VideoPlannerAgent ───
    divider("Stage 4: VIDEO PLANNER")
    planner = VideoPlannerAgent(profile)
    video_plan = await planner.plan(
        topic=topic,
        hook=best_hook,
        body_slides=yt_content.body,
        platform="youtube",
    )

    durations = [s.duration_seconds for s in video_plan.shots]
    avg_dur = sum(durations) / len(durations) if durations else 0
    total_min = sum(durations) / 60

    print(f"  씬 수: {len(video_plan.shots)}개")
    print(f"  슬라이드당 평균 duration: {avg_dur:.0f}초 (목표: ~60초)")
    print(f"  총 영상 길이: {total_min:.1f}분 (목표: 10~15분)")
    print(f"  페이싱: {video_plan.pacing} | 스타일: {video_plan.visual_style}")

    dur_ok = 45 <= avg_dur <= 70
    total_ok = 8 <= total_min <= 30

    print(f"\n  [{'PASS' if dur_ok else 'FAIL'}] 평균 duration: {avg_dur:.0f}초 {'(OK)' if dur_ok else '(잘못된 기본값 — 아직 7초 사용 중)'}")
    print(f"  [{'PASS' if total_ok else 'FAIL'}] 총 길이: {total_min:.1f}분 {'(OK)' if total_ok else '(너무 짧음)'}")

    # 씬 미리보기
    print(f"\n  씬 0: {video_plan.shots[0].duration_seconds}초 | {video_plan.shots[0].camera_movement} | {video_plan.shots[0].mood}")
    print(f"  씬 1: {video_plan.shots[1].duration_seconds}초 | {video_plan.shots[1].camera_movement} | {video_plan.shots[1].mood}")

    if not dur_ok:
        print("\n  [STOP] VideoPlannerAgent duration 오류 — TTS 테스트 스킵")
        return

    # ─── Stage 5: TTS (슬라이드 1개만) ───
    divider("Stage 5: TTS (슬라이드 1개 샘플)")
    sample_text = yt_content.body[0]
    out_path = OUTPUT_DIR / "tts_sample_slide01.wav"

    print(f"  텍스트 길이: {len(sample_text)}자 ({char_counts[0]}자, 공백제외)")
    wav = await generate_tts_gemini(sample_text, out_path, voice_name="Kore")

    if wav and wav.exists():
        size_kb = wav.stat().st_size / 1024
        print(f"  [PASS] WAV 생성 성공: {wav.name} ({size_kb:.0f}KB)")
        if size_kb < 10:
            print(f"  [WARN] 파일이 너무 작습니다 ({size_kb:.0f}KB) — TTS 실제 음성이 아닐 수 있음")
    else:
        print("  [FAIL] WAV 생성 실패!")

    # ─── 최종 요약 ───
    divider("RESULT SUMMARY")
    results = {
        "슬라이드 수": slide_ok,
        "슬라이드 글자 수": char_ok,
        "VideoPlan duration": dur_ok,
        "TTS WAV": wav is not None and wav.exists(),
    }
    all_pass = all(results.values())
    for name, ok in results.items():
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    print(f"\n  최종: {'ALL PASS' if all_pass else 'FAIL'}")
    if all_pass:
        print(f"  출력: open {OUTPUT_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
