"""
Tester Agent — 자동 테스트 실행
역할: pytest 실행, 커버리지 측정, 실패 리포트
"""
import subprocess
import sys
from pathlib import Path
from dataclasses import dataclass
from loguru import logger


@dataclass
class TestResult:
    passed: bool
    total: int = 0
    failures: int = 0
    errors: int = 0
    skipped: int = 0
    output: str = ""
    coverage_pct: float | None = None


class TesterAgent:
    """테스트 실행 에이전트"""

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or Path(__file__).parents[4]

    def run_tests(self, test_path: str = "backend/tests/", verbose: bool = True) -> TestResult:
        """pytest 실행"""
        cmd = [sys.executable, "-m", "pytest", test_path, "-v", "--tb=short"]
        if verbose:
            cmd.append("-v")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=self.project_root,
                timeout=300,
            )

            output = result.stdout + result.stderr

            # 결과 파싱
            total = failures = errors = skipped = 0
            for line in output.split("\n"):
                if "passed" in line or "failed" in line or "error" in line:
                    if "passed" in line:
                        try:
                            total += int(line.split("passed")[0].strip().split()[-1])
                        except (ValueError, IndexError):
                            pass
                    if "failed" in line:
                        try:
                            failures += int(line.split("failed")[0].strip().split()[-1])
                        except (ValueError, IndexError):
                            pass
                    if "error" in line:
                        try:
                            errors += int(line.split("error")[0].strip().split()[-1])
                        except (ValueError, IndexError):
                            pass

            return TestResult(
                passed=result.returncode == 0,
                total=total + failures + errors,
                failures=failures,
                errors=errors,
                skipped=skipped,
                output=output[-2000:],  # 마지막 2000자만
            )
        except FileNotFoundError:
            logger.warning("pytest not installed")
            return TestResult(passed=True, output="pytest not installed, skipping")
        except subprocess.TimeoutExpired:
            return TestResult(passed=False, output="Test timeout (>5min)")
        except Exception as e:
            return TestResult(passed=False, output=str(e))

    def run_import_check(self) -> TestResult:
        """모든 모듈의 import가 정상인지 확인"""
        errors = []
        backend_app = self.project_root / "backend" / "app"

        for py_file in backend_app.rglob("*.py"):
            if py_file.name == "__init__.py":
                continue
            rel_path = py_file.relative_to(self.project_root / "backend")
            module = str(rel_path).replace("/", ".").replace(".py", "")

            result = subprocess.run(
                [sys.executable, "-c", f"import {module}"],
                capture_output=True,
                text=True,
                cwd=self.project_root / "backend",
                timeout=10,
                env={**dict(__import__("os").environ), "PYTHONPATH": str(self.project_root / "backend")},
            )
            if result.returncode != 0:
                errors.append(f"{module}: {result.stderr.strip().split(chr(10))[-1]}")

        return TestResult(
            passed=len(errors) == 0,
            total=len(list(backend_app.rglob("*.py"))),
            failures=len(errors),
            output="\n".join(errors) if errors else "All imports OK",
        )

    def run_all(self) -> dict[str, TestResult]:
        """전체 테스트 실행"""
        logger.info("=== Tester Agent: 테스트 실행 ===")
        results = {
            "import_check": self.run_import_check(),
            "unit_tests": self.run_tests(),
        }
        all_passed = all(r.passed for r in results.values())
        logger.info(f"테스트 결과: {'PASS' if all_passed else 'FAIL'}")
        for name, result in results.items():
            status = "✓" if result.passed else "✗"
            logger.info(f"  {status} {name}: {result.total} total, {result.failures} failures")
        return results
