"""
AI Fix Generator — Uses Sarvam AI LLM to generate targeted code fixes.
"""

import os
import re
import logging
import httpx
from typing import Optional

from app.config import settings
from app.models import TestFailure, FileChange

logger = logging.getLogger(__name__)

SARVAM_API_URL = "https://api.sarvam.ai/v1/chat/completions"
SARVAM_MODEL = "sarvam-m"


class FixGenerator:
    """Generates AI-powered code fixes using Sarvam AI LLM."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.sarvam_api_key

    def generate_fix(
        self,
        failure: TestFailure,
        repo_path: str,
    ) -> Optional[FileChange]:
        """
        Given a test failure, read the source file, build a prompt,
        call the AI, and return a FileChange with the fix.
        """
        # Determine which source file to fix
        source_file = self._locate_source_file(failure, repo_path)
        if not source_file:
            logger.warning(f"Could not locate source file for failure: {failure.test_name}")
            return None

        # ── Programmatic fix: ModuleNotFoundError import rename ────────
        # If the source_file is a test file and the error is an import mismatch,
        # directly fix the wrong import name instead of calling the AI.
        all_err = (failure.error_message + " " + failure.error_type + " " + failure.raw_output).lower()
        if "modulenotfounderror" in all_err or ("importerror" in all_err and "no module" in all_err):
            missing_match = re.search(r"no module named ['\"]?([\w.]+)['\"]?", all_err)
            if missing_match and os.path.basename(source_file).startswith("test"):
                missing_name = missing_match.group(1)  # e.g. "math_util"
                # Find the real module name from the source files in the repo
                real_module = None
                for root, dirs, files in os.walk(repo_path):
                    dirs[:] = [d for d in dirs if not d.startswith(".") and d not in
                               ["node_modules", "__pycache__", "venv", ".venv"]]
                    for f in files:
                        if not f.endswith(".py") or f.startswith("test") or "test" in f:
                            continue
                        stem = f[:-3]
                        mn_base = missing_name.split(".")[-1]
                        if stem.startswith(mn_base) or mn_base.startswith(stem):
                            real_module = stem
                            break
                    if real_module:
                        break

                if real_module and real_module != missing_name.split(".")[-1]:
                    try:
                        with open(source_file, "r") as f:
                            original_content = f.read()
                        # Replace import references: "from math_util import" → "from math_utils import"
                        fixed = re.sub(
                            r'\b' + re.escape(missing_name.split(".")[-1]) + r'\b',
                            real_module,
                            original_content
                        )
                        if fixed != original_content:
                            with open(source_file, "w") as f:
                                f.write(fixed)
                            rel_path = os.path.relpath(source_file, repo_path)
                            diff = self._generate_diff(original_content, fixed, source_file)
                            logger.info(f"Programmatic import fix: '{missing_name}' → '{real_module}' in {rel_path}")
                            from app.models import BugType
                            return FileChange(
                                file_path=rel_path,
                                original_content=original_content,
                                fixed_content=fixed,
                                diff=diff,
                                description=f"Fixed import: '{missing_name}' → '{real_module}'",
                                bug_type=BugType.IMPORT,
                                commit_message=f"[AI-AGENT] Fix IMPORT in {rel_path}: wrong module name '{missing_name}'",
                                line_number=failure.line_number,
                                status="fixed",
                            )
                    except Exception as e:
                        logger.warning(f"Programmatic import fix failed: {e}")


        # Read the source file
        try:
            with open(source_file, "r") as f:
                original_content = f.read()
        except IOError as e:
            logger.error(f"Could not read {source_file}: {e}")
            return None

        # Read the test file if it exists
        test_content = ""
        test_file_path = self._resolve_path(failure.file_path, repo_path)
        if test_file_path and os.path.exists(test_file_path):
            try:
                with open(test_file_path, "r") as f:
                    test_content = f.read()
            except IOError:
                pass

        # Build prompt
        prompt = self._build_prompt(
            source_code=original_content,
            source_path=source_file,
            test_code=test_content,
            test_path=failure.file_path,
            test_name=failure.test_name,
            error_message=failure.error_message,
            error_type=failure.error_type,
            raw_output=failure.raw_output[:3000] if failure.raw_output else "",
        )

        # Call Sarvam AI
        try:
            logger.info(f"Calling Sarvam AI ({SARVAM_MODEL}) for fix generation...")
            ai_response = self._call_sarvam(prompt)

            if not ai_response:
                logger.error("Sarvam AI returned empty response")
                return None

            fixed_content = self._extract_code(ai_response, original_content)

            if fixed_content and fixed_content != original_content:
                # Apply the fix
                with open(source_file, "w") as f:
                    f.write(fixed_content)

                # Generate diff
                diff = self._generate_diff(original_content, fixed_content, source_file)
                rel_path = os.path.relpath(source_file, repo_path)
                bug_type = self._classify_bug_type(failure)
                commit_msg = f"[AI-AGENT] Fix {bug_type.value} in {rel_path}: {failure.error_type}"

                logger.info(f"Fix applied successfully to {rel_path} (bug_type={bug_type.value})")
                return FileChange(
                    file_path=rel_path,
                    original_content=original_content,
                    fixed_content=fixed_content,
                    diff=diff,
                    description=f"Fix for {failure.test_name}: {failure.error_type}",
                    bug_type=bug_type,
                    commit_message=commit_msg,
                    line_number=failure.line_number,
                    status="fixed",
                )
            else:
                logger.warning("AI did not produce a different fix.")
                return None

        except Exception as e:
            logger.error(f"AI fix generation failed: {e}")
            return None

    def _classify_bug_type(self, failure: TestFailure) -> "BugType":
        """Classify the bug type based on error message and type."""
        from app.models import BugType

        err = (failure.error_message + " " + failure.error_type).lower()

        if any(k in err for k in ["import", "modulenotfounderror", "no module named"]):
            return BugType.IMPORT
        if any(k in err for k in ["syntaxerror", "syntax error", "missing colon", "unexpected eof", "invalid syntax"]):
            return BugType.SYNTAX
        if any(k in err for k in ["indentationerror", "indentation", "unexpected indent", "unindent"]):
            return BugType.INDENTATION
        if any(k in err for k in ["typeerror", "type error", "not callable", "unsupported operand"]):
            return BugType.TYPE_ERROR
        if any(k in err for k in ["unused", "lint", "flake8", "pylint", "undefined variable", "undefined name"]):
            return BugType.LINTING
        if any(k in err for k in ["assert", "assertEqual", "expected", "actual", "!=", "=="]):
            return BugType.LOGIC

        return BugType.LOGIC  # default to LOGIC for assertion failures

    def _call_sarvam(self, prompt: str) -> Optional[str]:
        """Call Sarvam AI chat completions API."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": SARVAM_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are an expert software engineer. "
                        "When given a failing test and its source code, you fix the SOURCE code "
                        "(never the test) to make the test pass. "
                        "Return ONLY the complete fixed source file inside a single code block. "
                        "No explanations."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        }

        try:
            with httpx.Client(timeout=60.0) as client:
                resp = client.post(SARVAM_API_URL, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()

                # Extract content from OpenAI-compatible response
                choices = data.get("choices", [])
                if choices:
                    return choices[0].get("message", {}).get("content", "")
                return None

        except httpx.HTTPStatusError as e:
            logger.error(f"Sarvam API HTTP error {e.response.status_code}: {e.response.text[:500]}")
            raise
        except Exception as e:
            logger.error(f"Sarvam API call failed: {e}")
            raise

    def generate_fix_for_file(
        self,
        failures: list,
        source_file: str,
        repo_path: str,
    ) -> Optional["FileChange"]:
        """
        Fix ALL failures in a single source file with ONE AI call.
        This handles multiple simultaneous errors (e.g., NameError + IndentationError).
        """
        from app.models import FileChange, BugType

        if not failures:
            return None

        try:
            with open(source_file, "r") as f:
                original_content = f.read()
        except IOError as e:
            logger.error(f"Could not read {source_file}: {e}")
            return None

        # Read test file from the first failure for context
        test_content = ""
        first_failure = failures[0]
        test_file_path = self._resolve_path(first_failure.file_path, repo_path)
        if test_file_path and os.path.exists(test_file_path):
            try:
                with open(test_file_path, "r") as f:
                    test_content = f.read()
            except IOError:
                pass

        # Build combined error summary
        error_lines = []
        for i, failure in enumerate(failures, 1):
            error_lines.append(
                f"**Error {i}** — Test: `{failure.test_name}` | "
                f"Type: `{failure.error_type}` | Message: {failure.error_message}"
            )
        errors_summary = "\n".join(error_lines)

        # Combined raw output (truncated)
        combined_output = "\n---\n".join(
            f.raw_output[:1000] for f in failures if f.raw_output
        )[:3000]

        # Build multi-error prompt
        prompt = self._build_multi_prompt(
            source_code=original_content,
            source_path=source_file,
            test_code=test_content,
            test_path=first_failure.file_path,
            errors_summary=errors_summary,
            raw_output=combined_output,
            num_errors=len(failures),
        )

        try:
            logger.info(f"Calling Sarvam AI for multi-error fix ({len(failures)} errors in {os.path.basename(source_file)})...")
            ai_response = self._call_sarvam(prompt)

            if not ai_response:
                logger.error("Sarvam AI returned empty response for multi-error fix")
                return None

            fixed_content = self._extract_code(ai_response, original_content)

            if fixed_content and fixed_content != original_content:
                with open(source_file, "w") as f:
                    f.write(fixed_content)

                diff = self._generate_diff(original_content, fixed_content, source_file)
                rel_path = os.path.relpath(source_file, repo_path)

                # Use the most severe bug type among all failures
                bug_types = [self._classify_bug_type(f) for f in failures]
                # Priority: SYNTAX > INDENTATION > TYPE_ERROR > IMPORT > LOGIC
                priority = [BugType.SYNTAX, BugType.INDENTATION, BugType.TYPE_ERROR,
                           BugType.IMPORT, BugType.LOGIC, BugType.LINTING, BugType.UNKNOWN]
                bug_type = next((b for b in priority if b in bug_types), BugType.LOGIC)

                error_types_str = ", ".join(set(f.error_type for f in failures if f.error_type))
                commit_msg = f"[AI-AGENT] Fix {bug_type.value} ({len(failures)} errors) in {rel_path}"

                logger.info(f"Multi-error fix applied to {rel_path} ({len(failures)} errors fixed)")
                return FileChange(
                    file_path=rel_path,
                    original_content=original_content,
                    fixed_content=fixed_content,
                    diff=diff,
                    description=f"Fixed {len(failures)} error(s): {error_types_str}",
                    bug_type=bug_type,
                    commit_message=commit_msg,
                    line_number=failures[0].line_number if failures else None,
                    status="fixed",
                )
            else:
                logger.warning("AI did not produce a different multi-error fix.")
                return None

        except Exception as e:
            logger.error(f"Multi-error fix generation failed: {e}")
            return None

    def _build_multi_prompt(
        self,
        source_code: str,
        source_path: str,
        test_code: str,
        test_path: str,
        errors_summary: str,
        raw_output: str,
        num_errors: int,
    ) -> str:
        """Build a prompt that asks the AI to fix multiple errors at once."""
        return f"""A source file has {num_errors} error(s) that need to be fixed ALL AT ONCE.

## All Errors Found
{errors_summary}

## Test Code (for context)
```
{test_code[:2000]}
```

## Source Code to Fix ({source_path})
```
{source_code}
```

## Test Output
```
{raw_output}
```

## Instructions
1. Identify ALL {num_errors} error(s) listed above in the source code
2. Fix EVERY error in one go — return the complete corrected file
3. Do NOT change function signatures or test logic
4. Keep fixes minimal and targeted to the errors listed
5. Return ONLY the complete fixed source code in a single code block

## Fixed Source Code (all {num_errors} errors corrected)
"""

    def _build_prompt(
        self,
        source_code: str,
        source_path: str,
        test_code: str,
        test_path: str,
        test_name: str,
        error_message: str,
        error_type: str,
        raw_output: str,
    ) -> str:
        """Build the prompt for the AI model."""
        prompt = f"""A test is failing and you need to fix the SOURCE code (not the test) to make the test pass.

## Failing Test
- **Test name**: {test_name}
- **Test file**: {test_path}
- **Error type**: {error_type}
- **Error message**: {error_message}

## Test Code
```
{test_code[:3000]}
```

## Source Code ({source_path})
```
{source_code}
```

## Test Output
```
{raw_output[:2000]}
```

## Instructions
1. Analyze WHY the test is failing
2. Fix ONLY the source code (not the test) to make the test pass
3. Return the COMPLETE fixed source file
4. Do NOT change the function signatures unless absolutely necessary
5. Keep the fix minimal and targeted
6. Return ONLY the fixed code inside a single code block — no explanation

## Fixed Source Code
"""
        return prompt

    def _extract_code(self, ai_response: str, original: str) -> Optional[str]:
        """Extract code from AI response, handling code blocks."""
        # Match ```python ... ``` or ``` ... ```
        code_blocks = re.findall(
            r"```(?:\w+)?\n(.*?)```",
            ai_response,
            re.DOTALL,
        )

        if code_blocks:
            # Return the largest code block (most likely the full file)
            return max(code_blocks, key=len).strip() + "\n"

        # If no code block, check if the response looks like code
        lines = ai_response.strip().split("\n")
        code_lines = [l for l in lines if not l.startswith("#") or l.startswith("#!/")]

        if len(code_lines) > 3:
            return "\n".join(code_lines).strip() + "\n"

        return None

    def _locate_source_file(self, failure: TestFailure, repo_path: str) -> Optional[str]:
        """
        Given a test failure, try to locate the source file that needs fixing.
        Uses multiple strategies: import parsing, naming conventions, error message parsing.
        """
        test_file = failure.file_path
        test_file_abs = self._resolve_path(test_file, repo_path)

        # ── Strategy -1: Syntax/Indentation errors are always in the file itself ──
        # If the file has a syntax error, we must fix IT, not its imports.
        # Check error_type and error_message for syntax/indentation markers.
        err_lower = (failure.error_message + " " + failure.error_type).lower()
        if any(k in err_lower for k in ["indentationerror", "syntaxerror", "taberror", "unexpected indent", "unindent", "invalid syntax"]):
            if test_file_abs and os.path.exists(test_file_abs):
                logger.info(f"Syntax/Indentation error detected in {test_file}. Targeting file itself.")
                return test_file_abs

        # ── Strategy 0: ModuleNotFoundError — fix the test file's import ─
        # Search error_message, error_type AND raw_output for "No module named 'xxx'"
        all_error_text = (failure.error_message + " " + failure.error_type + " " + failure.raw_output).lower()
        if "modulenotfounderror" in all_error_text or ("importerror" in all_error_text and "no module" in all_error_text):
            missing = re.search(r"no module named ['\"]?([\w.]+)['\"]?", all_error_text)
            if missing:
                missing_name = missing.group(1).split(".")[-1]
                for root, dirs, files in os.walk(repo_path):
                    dirs[:] = [d for d in dirs if not d.startswith(".") and d not in
                               ["node_modules", "__pycache__", "venv", ".venv"]]
                    for f in files:
                        if not f.endswith(".py") or f.startswith("test") or "test" in f:
                            continue
                        stem = f[:-3]
                        if stem.startswith(missing_name) or missing_name.startswith(stem):
                            # The import is wrong in the test file — fix test.py
                            test_py = os.path.join(repo_path, "test.py")
                            if os.path.exists(test_py):
                                logger.info(f"ModuleNotFoundError: '{missing_name}' fuzzy-matches '{f}' → fixing test.py import")
                                return test_py
                            for r2, d2, files2 in os.walk(repo_path):
                                for tf in files2:
                                    if tf.startswith("test") and tf.endswith(".py"):
                                        return os.path.join(r2, tf)

        # ── Strategy 0b: NameError in test file (missing import) ──────────
        # If test.py says "name 'add' is not defined", check if "add" is in the source file.
        # If yes, we need to fix test.py (add import), not the source file.
        if "nameerror" in err_lower and "name" in err_lower and "is not defined" in err_lower:
            missing_name_match = re.search(r"name ['\"]?([\w]+)['\"]? is not defined", err_lower)
            if missing_name_match:
                missing_name = missing_name_match.group(1)
                # We need to find the source file first (using regular strategies)
                # to check if it contains the definition.
                # Strategy 1: check imports in test file (handles 'test imports ad' -> 'math_util.py')
                source_candidate = None
                if test_file_abs and os.path.exists(test_file_abs):
                    try:
                        with open(test_file_abs, "r") as f:
                            content = f.read()
                        # Simple regex to find imports
                        imports = re.findall(r"from\s+([\w.]+)\s+import", content)
                        imports += re.findall(r"import\s+([\w.]+)", content)
                        
                        for imp in imports:
                            base = imp.split(".")[0]
                            # Look for file matching this import
                            for root, dirs, files in os.walk(repo_path):
                                for f in files:
                                    if f == f"{base}.py" or f == f"{base}s.py": # naive match
                                        source_candidate = os.path.join(root, f)
                                        break
                                if source_candidate: break
                    except:
                        pass
                
                # If we found a source candidate and it has the missing name, fix test.py
                if source_candidate and os.path.exists(source_candidate):
                    try:
                        with open(source_candidate, "r") as f:
                            src_content = f.read()
                        if f"def {missing_name}" in src_content or f"class {missing_name}" in src_content:
                            logger.info(f"NameError '{missing_name}' in test.py found in {os.path.basename(source_candidate)}. Targeting test.py to fix import.")
                            return test_file_abs
                    except:
                        pass

        # Strategy 1: Parse imports from the test file to find source modules
        if test_file_abs and os.path.exists(test_file_abs):
            try:
                with open(test_file_abs, "r") as f:
                    test_content = f.read()

                import_patterns = [
                    re.compile(r"from\s+([\w.]+)\s+import"),
                    re.compile(r"^import\s+([\w.]+)", re.MULTILINE),
                ]

                for pattern in import_patterns:
                    for match in pattern.finditer(test_content):
                        module_name = match.group(1)
                        if module_name in ("os", "sys", "re", "json", "math", "pytest",
                                          "unittest", "mock", "datetime", "collections",
                                          "typing", "pathlib", "io", "abc"):
                            continue

                        module_path = module_name.replace(".", "/") + ".py"
                        all_py_files = []
                        for root, dirs, files in os.walk(repo_path):
                            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in
                                       ["node_modules", "__pycache__", "venv", ".venv"]]
                            for f in files:
                                if not f.endswith(".py"):
                                    continue
                                full_path = os.path.join(root, f)
                                rel_path = os.path.relpath(full_path, repo_path)
                                all_py_files.append((f, full_path, rel_path))
                                if rel_path == module_path or f == module_name + ".py":
                                    logger.info(f"Found source via import (exact): {full_path}")
                                    return full_path

                        # Strategy 1b: Fuzzy match module name to filename
                        base_module = module_name.split(".")[-1]
                        for f, full_path, rel_path in all_py_files:
                            stem = f[:-3]
                            if stem.startswith(base_module) or base_module.startswith(stem):
                                if not f.startswith("test") and "test" not in f:
                                    logger.info(f"Found source via fuzzy match: {full_path} (module={module_name})")
                                    return full_path

            except (IOError, Exception) as e:
                logger.warning(f"Failed to parse imports: {e}")

        # Strategy 2: Naming convention (test_foo.py → foo.py)
        basename = os.path.basename(test_file)
        candidates = []

        if basename.startswith("test_"):
            candidates.append(basename[5:])
        if basename.endswith("_test.py"):
            candidates.append(basename.replace("_test.py", ".py"))
        if ".test." in basename:
            candidates.append(basename.replace(".test.", "."))
        if ".spec." in basename:
            candidates.append(basename.replace(".spec.", "."))
        if basename.endswith("Test.java"):
            candidates.append(basename.replace("Test.java", ".java"))

        for root, dirs, files in os.walk(repo_path):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in
                       ["node_modules", "__pycache__", "venv", ".venv", "test", "tests",
                        "__tests__", "dist", "build"]]
            for f in files:
                if f in candidates:
                    return os.path.join(root, f)

        # Strategy 3: Parse error message for file references
        if failure.error_message:
            file_refs = self._extract_file_refs(failure.error_message, repo_path)
            if file_refs:
                return file_refs[0]

        # Strategy 4: Find any non-test Python file in the repo
        for root, dirs, files in os.walk(repo_path):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in
                       ["node_modules", "__pycache__", "venv", ".venv"]]
            for f in files:
                if f.endswith(".py") and not f.startswith("test_") and not f.endswith("_test.py") and f != "conftest.py" and f != "setup.py":
                    return os.path.join(root, f)

        # Strategy 5: If all else fails, fix the test file itself
        if test_file_abs and os.path.exists(test_file_abs):
            return test_file_abs

        return None

    def _extract_file_refs(self, text: str, repo_path: str) -> list[str]:
        """Extract file references from error text."""
        patterns = re.findall(r'[\w/\\]+\.\w+', text)
        results = []
        for p in patterns:
            full = os.path.join(repo_path, p)
            if os.path.exists(full):
                results.append(full)
        return results

    def _resolve_path(self, file_path: str, repo_path: str) -> Optional[str]:
        """Resolve a relative file path against the repo root."""
        full = os.path.join(repo_path, file_path)
        if os.path.exists(full):
            return full
        return None

    def _generate_diff(self, original: str, fixed: str, filepath: str) -> str:
        """Generate a unified diff string."""
        import difflib

        original_lines = original.splitlines(keepends=True)
        fixed_lines = fixed.splitlines(keepends=True)

        diff = difflib.unified_diff(
            original_lines,
            fixed_lines,
            fromfile=f"a/{os.path.basename(filepath)}",
            tofile=f"b/{os.path.basename(filepath)}",
        )
        return "".join(diff)
