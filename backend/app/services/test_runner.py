"""
Test Runner — Discovers and runs test files, parses results.
"""

import os
import sys
import subprocess
import re
import logging
from typing import Optional

from app.models import TestFailure

logger = logging.getLogger(__name__)


class TestRunner:
    """Discovers test files, runs test suites, and parses failures."""

    def discover_test_files(self, repo_path: str, languages: list[str]) -> list[str]:
        """
        Find all test files in the repository.
        """
        test_files = []
        patterns = []

        if "python" in languages:
            # Standard pytest patterns + bare test.py / tests.py
            patterns.extend(["test_*.py", "*_test.py", "test.py", "tests.py"])
        if "javascript" in languages or "typescript" in languages:
            patterns.extend(["*.test.js", "*.test.ts", "*.test.jsx", "*.test.tsx",
                             "*.spec.js", "*.spec.ts", "*.spec.jsx", "*.spec.tsx"])
        if "java" in languages:
            patterns.extend(["*Test.java", "*Tests.java"])
        if "go" in languages:
            patterns.extend(["*_test.go"])

        for root, dirs, files in os.walk(repo_path):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in
                       ["node_modules", "__pycache__", "venv", ".venv", "dist", "build", "target"]]
            for f in files:
                for pat in patterns:
                    if self._matches_pattern(f, pat):
                        test_files.append(os.path.join(root, f))
                        break

        return test_files

    def _matches_pattern(self, filename: str, pattern: str) -> bool:
        """Simple glob-like pattern matching."""
        if pattern.startswith("*"):
            return filename.endswith(pattern[1:])
        if pattern.endswith("*"):
            return filename.startswith(pattern[:-1])
        return filename == pattern

    def install_dependencies(self, repo_path: str, languages: list[str]) -> tuple[bool, str]:
        """
        Install project dependencies before running tests.
        Returns (success, output).
        """
        outputs = []
        python_exe = sys.executable  # Use the same Python running this server

        if "python" in languages:
            req_file = os.path.join(repo_path, "requirements.txt")
            if os.path.exists(req_file):
                result = self._run_cmd(
                    [python_exe, "-m", "pip", "install", "-r", "requirements.txt"],
                    cwd=repo_path
                )
                outputs.append(f"pip install: {result['output']}")
                if not result["success"]:
                    return False, "\n".join(outputs)

            # Also try pyproject.toml
            pyproject = os.path.join(repo_path, "pyproject.toml")
            if os.path.exists(pyproject):
                result = self._run_cmd(
                    [python_exe, "-m", "pip", "install", "-e", "."],
                    cwd=repo_path
                )
                outputs.append(f"pip install -e .: {result['output']}")

            # Ensure pytest is available
            check = self._run_cmd([python_exe, "-m", "pytest", "--version"], cwd=repo_path)
            if not check["success"]:
                logger.info("pytest not found, installing...")
                result = self._run_cmd(
                    [python_exe, "-m", "pip", "install", "pytest"],
                    cwd=repo_path
                )
                outputs.append(f"Auto-installed pytest: {result['output'][:200]}")

        if "javascript" in languages or "typescript" in languages:
            pkg_json = os.path.join(repo_path, "package.json")
            if os.path.exists(pkg_json):
                result = self._run_cmd(
                    ["npm", "install"],
                    cwd=repo_path
                )
                outputs.append(f"npm install: {result['output']}")
                if not result["success"]:
                    return False, "\n".join(outputs)

        return True, "\n".join(outputs) if outputs else "No dependencies to install."

    def run_tests(
        self,
        repo_path: str,
        languages: list[str],
        test_frameworks: list[str],
    ) -> dict:
        """
        Run the test suite and return structured results.
        Returns dict with keys: success, output, failures, return_code
        """
        # Determine the best test command
        cmd = self._build_test_command(repo_path, languages, test_frameworks)
        if not cmd:
            return {
                "success": False,
                "output": "Could not determine test command for this project.",
                "failures": [],
                "return_code": -1,
            }

        logger.info(f"Running tests: {' '.join(cmd)}")
        result = self._run_cmd(cmd, cwd=repo_path, timeout=300)

        if not result["success"]:
            # Optional: log a summary, but avoids dumping huge output
            pass

        # Parse failures from output
        failures = self._parse_failures(
            result["output"], repo_path, languages, test_frameworks
        )

        return {
            "success": result["success"],
            "output": result["output"],
            "failures": failures,
            "return_code": result["return_code"],
        }

    def _build_test_command(
        self,
        repo_path: str,
        languages: list[str],
        test_frameworks: list[str],
    ) -> Optional[list[str]]:
        """Build the appropriate test command."""

        # Python — always use sys.executable to ensure correct Python
        if "python" in languages:
            # Discover test files explicitly so pytest doesn't miss non-standard names
            test_files = self.discover_test_files(repo_path, languages)
            if test_files:
                # Pass files explicitly — handles test.py, tests.py, etc.
                rel_files = [os.path.relpath(f, repo_path) for f in test_files]
                logger.info(f"Discovered test files: {rel_files}")
                return [sys.executable, "-m", "pytest", "-v", "--tb=long"] + rel_files
            return [sys.executable, "-m", "pytest", "-v", "--tb=long"]

        # JavaScript / TypeScript
        if "javascript" in languages or "typescript" in languages:
            pkg_json_path = os.path.join(repo_path, "package.json")
            if os.path.exists(pkg_json_path):
                import json
                try:
                    with open(pkg_json_path) as f:
                        pkg = json.load(f)
                    scripts = pkg.get("scripts", {})
                    if "test" in scripts:
                        return ["npm", "test", "--", "--passWithNoTests"]
                except (json.JSONDecodeError, IOError):
                    pass

            if "jest" in test_frameworks:
                return ["npx", "jest", "--passWithNoTests", "--verbose"]
            if "vitest" in test_frameworks:
                return ["npx", "vitest", "run", "--reporter=verbose"]
            if "mocha" in test_frameworks:
                return ["npx", "mocha", "--recursive"]

        # Go
        if "go" in languages:
            return ["go", "test", "./...", "-v"]

        # Java
        if "java" in languages:
            if os.path.exists(os.path.join(repo_path, "pom.xml")):
                return ["mvn", "test"]
            if os.path.exists(os.path.join(repo_path, "build.gradle")):
                return ["./gradlew", "test"]

        return None

    def _run_cmd(
        self, cmd: list[str], cwd: str, timeout: int = 120
    ) -> dict:
        """Run a shell command and capture output."""
        try:
            result = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env={**os.environ, "CI": "true", "FORCE_COLOR": "0"},
            )
            combined_output = result.stdout + "\n" + result.stderr
            return {
                "success": result.returncode == 0,
                "output": combined_output.strip(),
                "return_code": result.returncode,
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "output": f"Command timed out after {timeout}s",
                "return_code": -1,
            }
        except FileNotFoundError as e:
            return {
                "success": False,
                "output": f"Command not found: {e}",
                "return_code": -1,
            }
        except Exception as e:
            return {
                "success": False,
                "output": f"Error running command: {e}",
                "return_code": -1,
            }

    def _parse_failures(
        self,
        output: str,
        repo_path: str,
        languages: list[str],
        test_frameworks: list[str],
    ) -> list[TestFailure]:
        """Parse test output to extract structured failures."""
        failures = []

        # Strip ANSI escape codes so regexes can match
        clean_output = re.sub(r'\x1b\[[0-9;]*m', '', output)

        if "python" in languages:
            failures.extend(self._parse_pytest_failures(clean_output, repo_path))

        if "javascript" in languages or "typescript" in languages:
            failures.extend(self._parse_jest_failures(clean_output, repo_path))

        # If no structured parsing worked, try generic parsing
        if not failures and ("FAILED" in clean_output or "FAIL" in clean_output or "Error" in clean_output or "error" in clean_output):
            failures.extend(self._parse_generic_failures(clean_output, repo_path))

        return failures

    def _parse_pytest_failures(self, output: str, repo_path: str) -> list[TestFailure]:
        """Parse pytest output for failures."""
        failures = []

        # Match pytest FAILED lines like:
        #   FAILED tests/test_math.py::test_add - AssertionError
        #   FAILED ../../../../../repo/test.py::test_add - AssertionError
        failed_pattern = re.compile(
            r"FAILED\s+([\w./\\-]+)::(\w+)(?:\s*-\s*(.+))?",
        )

        for match in failed_pattern.finditer(output):
            raw_path = match.group(1)
            test_name = match.group(2)
            error_msg = match.group(3) or ""

            # Normalize path: strip leading ../../../ to get a clean relative path
            file_path = re.sub(r'^(\.\./)+', '', raw_path)

            # Try to find line number in the traceback for this test
            # Search for "____ test_name ____" and then "file_path:line"
            line_no = None
            try:
                # Find the header section for this test
                header_match = re.search(r"_{3,}\s+" + re.escape(test_name) + r"\s+_{3,}", output)
                if header_match:
                    section_start = header_match.end()
                    # Look for file_path:line in the section following the header
                    # allow for relative path differences so search for basename
                    basename = os.path.basename(file_path)
                    line_match = re.search(re.escape(basename) + r":(\d+):", output[section_start:section_start+2000])
                    if line_match:
                        line_no = int(line_match.group(1))
            except Exception:
                pass

            failures.append(TestFailure(
                test_name=test_name,
                file_path=file_path,
                error_message=error_msg,
                error_type=error_msg.split(":")[0] if ":" in error_msg else error_msg,
                line_number=line_no,
                raw_output=output,
            ))

        # ── Collection errors (two formats) ──────────────────────────────
        # Format 1 (old pytest): ERROR path/test.py - SomeError: message
        collect_with_msg = re.compile(r"ERROR\s+([\w./\\-]+)\s+-\s+(.+)")
        # Format 2 (pytest 7+): bare "ERROR path/test.py" in short test summary
        collect_bare = re.compile(r"^ERROR\s+([\w./\\-]+)\s*$", re.MULTILINE)

        parsed_collect_files = set()

        for match in collect_with_msg.finditer(output):
            raw_path = match.group(1)
            file_path = re.sub(r'^(\.\./)+', '', raw_path)
            error_msg = match.group(2).strip()
            error_type = error_msg.split(":")[0] if ":" in error_msg else "CollectionError"
            parsed_collect_files.add(file_path)
            failures.append(TestFailure(
                test_name="(collection error)",
                file_path=file_path,
                error_message=error_msg,
                error_type=error_type,
                raw_output=output,
            ))

        for match in collect_bare.finditer(output):
            raw_path = match.group(1)
            file_path = re.sub(r'^(\.\./)+', '', raw_path)
            if file_path in parsed_collect_files:
                continue  # already handled above

            # Extract the real error info from the traceback body
            # Look for the last File "..." path mentioned in the traceback (the real buggy file)
            file_refs = re.findall(r'File "([^"]+)"', output)
            # Also look for error type: IndentationError, ImportError, etc.
            error_type_match = re.search(
                r'(IndentationError|SyntaxError|ImportError|ModuleNotFoundError|NameError|TypeError)[:\s]([^\n]*)',
                output
            )
            error_type = "CollectionError"
            error_msg = f"Collection error in {file_path}"
            actual_file = file_path  # default to the test file

            if error_type_match:
                error_type = error_type_match.group(1)
                error_msg = f"{error_type}: {error_type_match.group(2).strip()}"

            # Find the actual source file from traceback (last non-pytest/stdlib File reference in repo)
            # We want to capture line numbers too.
            # Strategy 1: File "...", line \d+
            matches_1 = re.findall(r'File "([^"]+)", line (\d+)', output)
            # Strategy 2: path:line: (often used in pytest tracebacks without File keyword)
            matches_2 = re.findall(r'\n([\w./\\-]+):(\d+):', output)
            
            traceback_locs = matches_1 + matches_2
            
            line_no = None

            for path, line in reversed(traceback_locs):
                # Skip pytest internals, stdlib
                if any(skip in path for skip in ['site-packages', '<frozen', 'lib/python']):
                    continue
                
                # Check if this file exists in our repo
                full_path_candidate = path
                if not os.path.isabs(path):
                    full_path_candidate = os.path.join(repo_path, path)
                
                if os.path.exists(full_path_candidate):
                     actual_file = os.path.relpath(full_path_candidate, repo_path)
                     line_no = int(line)
                     break
            
            failures.append(TestFailure(
                test_name="(collection error)",
                file_path=actual_file,
                error_message=error_msg,
                error_type=error_type,
                line_number=line_no,
                raw_output=output,
            ))

        return failures

    def _parse_jest_failures(self, output: str, repo_path: str) -> list[TestFailure]:
        """Parse Jest output for failures."""
        failures = []

        # Match Jest FAIL lines
        fail_pattern = re.compile(r"FAIL\s+([\w/\\.]+)")
        test_pattern = re.compile(r"✕\s+(.+?)(?:\s*\((\d+)\s*ms\))?$", re.MULTILINE)
        error_pattern = re.compile(r"●\s+(.+?)\n\n([\s\S]+?)(?=\n\s*●|\n\s*Test Suites:)", re.MULTILINE)

        for match in fail_pattern.finditer(output):
            file_path = match.group(1)
            failures.append(TestFailure(
                test_name="(file-level failure)",
                file_path=file_path,
                error_message="Test suite failed",
                error_type="TestSuiteFailure",
                raw_output=output,
            ))

        # Parse individual test failures
        for match in error_pattern.finditer(output):
            test_name = match.group(1).strip()
            error_detail = match.group(2).strip()
            failures.append(TestFailure(
                test_name=test_name,
                error_message=error_detail[:500],
                error_type="AssertionError",
                raw_output=output,
            ))

        return failures

    def _parse_generic_failures(self, output: str, repo_path: str) -> list[TestFailure]:
        """Generic failure parsing for unknown test frameworks."""
        failures = []
        error_lines = [
            line for line in output.split("\n")
            if any(kw in line.lower() for kw in ["error", "failed", "fail", "exception"])
        ]

        if error_lines:
            failures.append(TestFailure(
                test_name="(generic failure)",
                error_message="\n".join(error_lines[:10]),
                error_type="GenericError",
                raw_output=output,
            ))

        return failures
