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
                    cwd=repo_path,
                    timeout=600
                )
                outputs.append(f"pip install: {result['output']}")
                if not result["success"]:
                    return False, "\n".join(outputs)

            # Also try pyproject.toml
            pyproject = os.path.join(repo_path, "pyproject.toml")
            if os.path.exists(pyproject):
                result = self._run_cmd(
                    [python_exe, "-m", "pip", "install", "-e", "."],
                    cwd=repo_path,
                    timeout=600
                )
                outputs.append(f"pip install -e .: {result['output']}")

            # Always ensure pytest is available for Python repos
            check = self._run_cmd([python_exe, "-m", "pytest", "--version"], cwd=repo_path)
            if not check["success"]:
                logger.info("pytest not found, installing...")
                result = self._run_cmd(
                    [python_exe, "-m", "pip", "install", "pytest"],
                    cwd=repo_path,
                    timeout=120
                )
                outputs.append(f"Auto-installed pytest: {result['output'][:200]}")

        if "javascript" in languages or "typescript" in languages:
            pkg_json = os.path.join(repo_path, "package.json")
            if os.path.exists(pkg_json):
                result = self._run_cmd(
                    ["npm", "install"],
                    cwd=repo_path,
                    timeout=600
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
            
            # If our strict string matching failed, let pytest try to find them itself
            logger.info("No test files found via strict matching. Falling back to native pytest discovery.")
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
                except (json.JSONDecodeError, IOError) as e:
                    logger.error(f"Error reading package.json: {e}")

            # If npm test is not available or failed, try specific frameworks
            if "vitest" in test_frameworks:
                logger.info("Falling back to vitest.")
                return ["npx", "vitest", "run", "--passWithNoTests"]
            
            if "jest" in test_frameworks:
                logger.info("Falling back to jest.")
                return ["npx", "jest", "--passWithNoTests"]

            # Default fallback for JS/TS if no package.json or specific framework found
            logger.info("No explicit JS test framework found. Falling back to vitest.")
            return ["npx", "vitest", "run", "--passWithNoTests"]

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
        """Parse Jest/Vitest output for failures."""
        failures = []

        # State machine to track the current file being executed
        current_file = None
        
        lines = output.split("\n")
        
        for i, line in enumerate(lines):
            # Track the current file from "FAIL path/to/file.js"
            fail_match = re.search(r"FAIL\s+([\w/\\._-]+)", line)
            if fail_match:
                current_file = fail_match.group(1)

            # Look for individual test failure blocks: "  ● Test describe › test name"
            if line.strip().startswith("●"):
                test_name = line.strip()[2:].strip() # remove '● '
                
                # capture the block of text until the next test or error boundary
                error_block = []
                for j in range(i + 1, min(i + 50, len(lines))):
                    if lines[j].strip().startswith("●") or lines[j].strip().startswith("Test Suites:"):
                        break
                    error_block.append(lines[j])
                    
                error_detail = "\n".join(error_block).strip()
                
                # Try to extract exact line number and specific file from the stack trace
                # e.g. "    at Object.<anonymous> (src/math.js:15:7)"
                # e.g. "    at src/math.js:15:7"
                line_no = None
                actual_file = current_file
                
                stack_traces = re.findall(r"at\s+.*?\s*\(?([\w/\\._-]+):(\d+):(\d+)\)?", error_detail)
                for trace_file, trace_line, _ in stack_traces:
                    # Skip jest/node internals
                    if not any(skip in trace_file for skip in ["node_modules", "internal/", "jest-circus"]):
                        actual_file = trace_file
                        line_no = int(trace_line)
                        break
                
                # Try to infer ReferenceError, TypeError, SyntaxError from the detail
                error_type = "AssertionError"
                if "ReferenceError:" in error_detail:
                    error_type = "ReferenceError"
                elif "TypeError:" in error_detail:
                    error_type = "TypeError"
                elif "SyntaxError:" in error_detail:
                    error_type = "SyntaxError"
                elif "Cannot find module" in error_detail:
                    error_type = "ModuleNotFoundError"
                
                failures.append(TestFailure(
                    test_name=test_name,
                    file_path=actual_file if actual_file else "(unknown)",
                    error_message=error_detail[:500],
                    error_type=error_type,
                    line_number=line_no,
                    raw_output=error_detail,
                ))

        # Vitest specific bare error parsing
        if not failures and "Error:" in output:
            for match in re.finditer(r"Error: (.*?)\n\s*at .*? \(([\w/\\._-]+):(\d+):(\d+)\)", output):
                failures.append(TestFailure(
                    test_name="(vitest error)",
                    file_path=match.group(2),
                    error_message=match.group(1),
                    error_type=match.group(1).split(":")[0] if ":" in match.group(1) else "Error",
                    line_number=int(match.group(3)),
                    raw_output=match.group(0),
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
