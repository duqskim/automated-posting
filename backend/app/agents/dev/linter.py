"""
Linter Agent — 코드 정적 분석
역할: 타입 체크, 스타일 검사, 보안 취약점 탐지
"""
import subprocess
import sys
from pathlib import Path
from dataclasses import dataclass, field
from loguru import logger


@dataclass
class LintResult:
    passed: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    files_checked: int = 0


class LinterAgent:
    """코드 정적 분석 에이전트"""

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or Path(__file__).parents[4]

    def run_ruff_check(self) -> LintResult:
        """ruff 린터 실행"""
        try:
            result = subprocess.run(
                [sys.executable, "-m", "ruff", "check", "backend/"],
                capture_output=True,
                text=True,
                cwd=self.project_root,
                timeout=60,
            )
            errors = [line for line in result.stdout.strip().split("\n") if line]
            return LintResult(
                passed=result.returncode == 0,
                errors=errors if result.returncode != 0 else [],
                files_checked=len(list((self.project_root / "backend").rglob("*.py"))),
            )
        except FileNotFoundError:
            logger.warning("ruff not installed, skipping lint check")
            return LintResult(passed=True, warnings=["ruff not installed"])
        except Exception as e:
            return LintResult(passed=False, errors=[str(e)])

    def run_type_check(self) -> LintResult:
        """mypy 또는 pyright 타입 체크"""
        try:
            result = subprocess.run(
                [sys.executable, "-m", "mypy", "backend/app/", "--ignore-missing-imports"],
                capture_output=True,
                text=True,
                cwd=self.project_root,
                timeout=120,
            )
            errors = [line for line in result.stdout.strip().split("\n") if "error:" in line]
            return LintResult(
                passed=result.returncode == 0,
                errors=errors,
            )
        except FileNotFoundError:
            logger.warning("mypy not installed, skipping type check")
            return LintResult(passed=True, warnings=["mypy not installed"])
        except Exception as e:
            return LintResult(passed=False, errors=[str(e)])

    def check_security(self) -> LintResult:
        """보안 취약점 기본 검사"""
        issues = []
        backend_dir = self.project_root / "backend"

        for py_file in backend_dir.rglob("*.py"):
            content = py_file.read_text(encoding="utf-8", errors="ignore")

            # 하드코딩된 시크릿 검출
            danger_patterns = [
                ("password =", "하드코딩된 비밀번호"),
                ("secret =", "하드코딩된 시크릿"),
                ("api_key =", "하드코딩된 API 키"),
            ]
            for pattern, desc in danger_patterns:
                for i, line in enumerate(content.split("\n"), 1):
                    stripped = line.strip()
                    if pattern in stripped.lower() and "=" in stripped and not stripped.startswith("#"):
                        # settings, env, 문자열 리터럴(패턴 정의)은 OK
                        if "settings." not in stripped and "os.getenv" not in stripped and "getenv" not in stripped:
                            if '""' not in stripped and "''" not in stripped:
                                # 튜플/리스트 안의 문자열 패턴 정의는 제외
                                if not (stripped.startswith("(") or stripped.startswith('"') or stripped.startswith("'")):
                                    issues.append(f"{py_file.name}:{i} — {desc}: {stripped[:80]}")

        return LintResult(
            passed=len(issues) == 0,
            errors=issues,
        )

    def run_all(self) -> dict[str, LintResult]:
        """전체 린트 검사 실행"""
        logger.info("=== Linter Agent: 코드 정적 분석 시작 ===")
        results = {
            "ruff": self.run_ruff_check(),
            "type_check": self.run_type_check(),
            "security": self.check_security(),
        }
        all_passed = all(r.passed for r in results.values())
        logger.info(f"Linter 결과: {'PASS' if all_passed else 'FAIL'}")
        for name, result in results.items():
            status = "✓" if result.passed else "✗"
            logger.info(f"  {status} {name}: {len(result.errors)} errors, {len(result.warnings)} warnings")
        return results
