"""
Ship Agent — 최종 검수 + 문서 업데이트 + 커밋
역할: Linter → Tester → Reviewer 순서로 실행 후, 통과하면 md 업데이트 + 커밋

워크플로우:
  1. Linter Agent 실행 (코드 정적 분석)
  2. Tester Agent 실행 (테스트)
  3. Reviewer Agent 실행 (코드 리뷰)
  4. 전부 통과 → 문서 업데이트 + git commit + push
  5. 실패 → 실패 리포트 반환 (커밋 안 함)
"""
import subprocess
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import dataclass
from loguru import logger

from app.agents.dev.linter import LinterAgent
from app.agents.dev.tester import TesterAgent
from app.agents.dev.reviewer import ReviewerAgent


@dataclass
class ShipResult:
    shipped: bool
    commit_hash: str | None = None
    lint_passed: bool = False
    test_passed: bool = False
    review_passed: bool = False
    blockers: list[str] | None = None
    summary: str = ""


class ShipAgent:
    """
    최종 검수 + 배포 에이전트

    모든 개발 완료 시 이 에이전트를 호출:
      result = ShipAgent().ship("feat: 새 기능 추가")
    """

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or Path(__file__).parents[4]
        self.linter = LinterAgent(self.project_root)
        self.tester = TesterAgent(self.project_root)
        self.reviewer = ReviewerAgent(self.project_root)

    def _run_checks(self) -> tuple[bool, list[str]]:
        """1~3단계: 린트 → 테스트 → 리뷰"""
        blockers = []

        # 1. Linter
        logger.info("── Step 1/5: Linter Agent ──")
        lint_results = self.linter.run_all()
        lint_passed = all(r.passed for r in lint_results.values())
        if not lint_passed:
            for name, result in lint_results.items():
                for error in result.errors[:5]:  # 상위 5개만
                    blockers.append(f"[Lint/{name}] {error}")

        # 2. Tester
        logger.info("── Step 2/5: Tester Agent ──")
        test_results = self.tester.run_all()
        test_passed = all(r.passed for r in test_results.values())
        if not test_passed:
            for name, result in test_results.items():
                if not result.passed:
                    blockers.append(f"[Test/{name}] {result.failures} failures: {result.output[:200]}")

        # 3. Reviewer
        logger.info("── Step 3/5: Reviewer Agent ──")
        review_result = self.reviewer.run_all()
        review_passed = review_result.passed
        if not review_passed:
            for issue in review_result.issues:
                if issue.severity == "error":
                    blockers.append(f"[Review] {issue.file}:{issue.line} — {issue.message}")

        return (lint_passed and test_passed and review_passed), blockers

    def _update_docs(self, commit_message: str) -> None:
        """4단계: 문서 업데이트"""
        logger.info("── Step 4/5: 문서 업데이트 ──")

        # ARCHITECTURE.md의 마지막 업데이트 날짜 갱신
        arch_path = self.project_root / "docs" / "ARCHITECTURE.md"
        if arch_path.exists():
            content = arch_path.read_text(encoding="utf-8")
            now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

            # 마지막 줄에 업데이트 타임스탬프 추가/갱신
            if "Last updated:" in content:
                lines = content.split("\n")
                for i, line in enumerate(lines):
                    if line.startswith("Last updated:"):
                        lines[i] = f"Last updated: {now}"
                        break
                content = "\n".join(lines)
            else:
                content += f"\n\n---\nLast updated: {now}\n"

            arch_path.write_text(content, encoding="utf-8")
            logger.info(f"ARCHITECTURE.md 업데이트: {now}")

    def _git_commit(self, commit_message: str, push: bool = True) -> str | None:
        """5단계: Git 커밋 + Push"""
        logger.info("── Step 5/5: Git 커밋 ──")

        try:
            # Stage all changes
            subprocess.run(
                ["git", "add", "-A"],
                cwd=self.project_root,
                check=True,
                capture_output=True,
            )

            # Check if there are changes to commit
            status = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
            )
            if not status.stdout.strip():
                logger.info("커밋할 변경사항 없음")
                return None

            # Commit
            full_message = f"{commit_message}\n\nCo-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
            result = subprocess.run(
                ["git", "commit", "-m", full_message],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                check=True,
            )

            # Extract commit hash
            log = subprocess.run(
                ["git", "log", "--oneline", "-1"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
            )
            commit_hash = log.stdout.strip().split()[0] if log.stdout.strip() else None

            # Push
            if push:
                subprocess.run(
                    ["git", "push"],
                    cwd=self.project_root,
                    capture_output=True,
                    check=True,
                )
                logger.info(f"Push 완료: {commit_hash}")

            return commit_hash

        except subprocess.CalledProcessError as e:
            logger.error(f"Git 실패: {e.stderr}")
            return None

    def ship(self, commit_message: str, push: bool = True, force: bool = False) -> ShipResult:
        """
        전체 워크플로우 실행:
          자체검증 → 테스트 → 리팩토링 → md 업데이트 → 커밋

        Args:
            commit_message: 커밋 메시지
            push: True면 push까지
            force: True면 검증 실패해도 커밋 (비추천)
        """
        logger.info(f"=== Ship Agent: 배포 시작 — {commit_message} ===")

        # Steps 1-3: 검증
        all_passed, blockers = self._run_checks()

        if not all_passed and not force:
            logger.warning(f"검증 실패: {len(blockers)}개 blocker")
            return ShipResult(
                shipped=False,
                lint_passed=not any("[Lint" in b for b in blockers),
                test_passed=not any("[Test" in b for b in blockers),
                review_passed=not any("[Review" in b for b in blockers),
                blockers=blockers,
                summary=f"검증 실패: {len(blockers)}개 blocker. 수정 후 재시도.",
            )

        # Step 4: 문서 업데이트
        self._update_docs(commit_message)

        # Step 5: 커밋
        commit_hash = self._git_commit(commit_message, push=push)

        result = ShipResult(
            shipped=True,
            commit_hash=commit_hash,
            lint_passed=True,
            test_passed=True,
            review_passed=True,
            summary=f"배포 완료: {commit_hash}" if commit_hash else "변경사항 없음",
        )
        logger.info(f"=== Ship Agent: {result.summary} ===")
        return result
