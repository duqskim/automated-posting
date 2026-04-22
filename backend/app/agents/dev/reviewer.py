"""
Reviewer Agent — 코드 리뷰 + 리팩토링 제안
역할: 중복 코드 탐지, 코드 복잡도 분석, 개선 제안
"""
import ast
from pathlib import Path
from dataclasses import dataclass, field
from loguru import logger


@dataclass
class ReviewIssue:
    file: str
    line: int
    severity: str  # "error", "warning", "info"
    message: str


@dataclass
class ReviewResult:
    passed: bool
    issues: list[ReviewIssue] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    files_reviewed: int = 0


class ReviewerAgent:
    """코드 리뷰 에이전트"""

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or Path(__file__).parents[4]

    def check_function_length(self, max_lines: int = 50) -> list[ReviewIssue]:
        """함수가 너무 긴지 검사"""
        issues = []
        backend_app = self.project_root / "backend" / "app"

        for py_file in backend_app.rglob("*.py"):
            try:
                source = py_file.read_text(encoding="utf-8")
                tree = ast.parse(source)

                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        func_lines = node.end_lineno - node.lineno + 1
                        if func_lines > max_lines:
                            issues.append(ReviewIssue(
                                file=py_file.name,
                                line=node.lineno,
                                severity="warning",
                                message=f"함수 '{node.name}'이 {func_lines}줄 (>{max_lines}줄). 분리 검토 필요",
                            ))
            except SyntaxError:
                issues.append(ReviewIssue(
                    file=py_file.name, line=0, severity="error",
                    message="구문 오류 (SyntaxError)",
                ))
            except Exception:
                pass

        return issues

    def check_todo_fixme(self) -> list[ReviewIssue]:
        """TODO/FIXME 주석 수집"""
        issues = []
        backend_app = self.project_root / "backend" / "app"

        for py_file in backend_app.rglob("*.py"):
            try:
                for i, line in enumerate(py_file.read_text(encoding="utf-8").split("\n"), 1):
                    stripped = line.strip()
                    if "# TODO" in stripped or "# FIXME" in stripped or "# HACK" in stripped:
                        issues.append(ReviewIssue(
                            file=py_file.name,
                            line=i,
                            severity="info",
                            message=stripped,
                        ))
            except Exception:
                pass

        return issues

    def check_unused_imports(self) -> list[ReviewIssue]:
        """사용되지 않는 import 감지 (기본적인 수준)"""
        issues = []
        backend_app = self.project_root / "backend" / "app"

        for py_file in backend_app.rglob("*.py"):
            if py_file.name == "__init__.py":
                continue
            try:
                source = py_file.read_text(encoding="utf-8")
                tree = ast.parse(source)

                imports = []
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            name = alias.asname or alias.name.split(".")[-1]
                            imports.append((name, node.lineno))
                    elif isinstance(node, ast.ImportFrom):
                        for alias in node.names:
                            name = alias.asname or alias.name
                            imports.append((name, node.lineno))

                # 간단한 사용 여부 확인 (import 줄 제외하고 이름이 나타나는지)
                lines = source.split("\n")
                for name, lineno in imports:
                    if name == "*":
                        continue
                    used = False
                    for i, line in enumerate(lines, 1):
                        if i == lineno:
                            continue
                        if name in line:
                            used = True
                            break
                    if not used:
                        issues.append(ReviewIssue(
                            file=py_file.name,
                            line=lineno,
                            severity="warning",
                            message=f"미사용 import: '{name}'",
                        ))
            except Exception:
                pass

        return issues

    def run_all(self) -> ReviewResult:
        """전체 코드 리뷰 실행"""
        logger.info("=== Reviewer Agent: 코드 리뷰 ===")

        all_issues = []
        all_issues.extend(self.check_function_length())
        all_issues.extend(self.check_todo_fixme())
        all_issues.extend(self.check_unused_imports())

        error_count = sum(1 for i in all_issues if i.severity == "error")

        files_reviewed = len(list((self.project_root / "backend" / "app").rglob("*.py")))

        result = ReviewResult(
            passed=error_count == 0,
            issues=all_issues,
            files_reviewed=files_reviewed,
        )

        logger.info(f"리뷰 결과: {files_reviewed}개 파일, "
                     f"{error_count} errors, "
                     f"{sum(1 for i in all_issues if i.severity == 'warning')} warnings, "
                     f"{sum(1 for i in all_issues if i.severity == 'info')} info")

        return result
