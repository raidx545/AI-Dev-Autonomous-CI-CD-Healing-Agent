"""
Clone Service — Clones a GitHub repository and analyzes its structure.
"""

import os
import shutil
import tempfile
import logging
from typing import Optional
from git import Repo

from app.config import settings

logger = logging.getLogger(__name__)


class CloneService:
    """Handles cloning GitHub repos and detecting project type."""

    # Framework/language detection mappings
    LANGUAGE_MARKERS = {
        "python": ["requirements.txt", "setup.py", "pyproject.toml", "Pipfile", "setup.cfg"],
        "javascript": ["package.json"],
        "typescript": ["tsconfig.json"],
        "java": ["pom.xml", "build.gradle", "build.gradle.kts"],
        "rust": ["Cargo.toml"],
        "go": ["go.mod"],
        "ruby": ["Gemfile"],
        "csharp": [".csproj"],
    }

    TEST_FRAMEWORK_MARKERS = {
        "pytest": ["pytest.ini", "conftest.py", "setup.cfg"],
        "unittest": [],  # detected by scanning for `import unittest`
        "jest": ["jest.config.js", "jest.config.ts", "jest.config.mjs"],
        "mocha": [".mocharc.yml", ".mocharc.json", ".mocharc.js"],
        "vitest": ["vitest.config.ts", "vitest.config.js"],
        "junit": ["pom.xml"],  # combined with java detection
        "go_test": ["go.mod"],
    }

    def __init__(self):
        os.makedirs(settings.clone_base_dir, exist_ok=True)

    def clone(self, repo_url: str, github_token: Optional[str] = None) -> str:
        """
        Clone a GitHub repository (or local path) to a local directory.
        Returns the local path to the cloned repository.
        """
        # Extract repo name from URL or path
        repo_name = repo_url.rstrip("/").split("/")[-1].replace(".git", "")
        clone_dir = os.path.join(settings.clone_base_dir, repo_name)

        # Clean up if it already exists
        if os.path.exists(clone_dir):
            shutil.rmtree(clone_dir)

        # Inject token into URL for private repos
        auth_url = repo_url
        if repo_url.startswith("http"):
            token = github_token or settings.github_token
            if token and "github.com" in repo_url:
                auth_url = repo_url.replace(
                    "https://github.com",
                    f"https://{token}@github.com"
                )

        logger.info(f"Cloning {auth_url} into {clone_dir}")
        Repo.clone_from(auth_url, clone_dir)
        logger.info(f"Successfully cloned to {clone_dir}")

        return clone_dir

    def detect_languages(self, repo_path: str) -> list[str]:
        """Detect programming languages used in the repository."""
        detected = []
        all_files = set()
        all_extensions = set()

        for root, dirs, files in os.walk(repo_path):
            # Skip hidden dirs and common non-source dirs
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in
                       ["node_modules", "__pycache__", "venv", ".venv", "dist", "build", "target"]]
            for f in files:
                all_files.add(f)
                ext = os.path.splitext(f)[1].lower()
                if ext:
                    all_extensions.add(ext)

        # Strategy 1: Check for config file markers
        for language, markers in self.LANGUAGE_MARKERS.items():
            for marker in markers:
                if marker in all_files:
                    detected.append(language)
                    break

        # Strategy 2: Fallback — detect by file extensions
        if not detected:
            EXT_MAP = {
                ".py": "python",
                ".js": "javascript",
                ".jsx": "javascript",
                ".ts": "typescript",
                ".tsx": "typescript",
                ".java": "java",
                ".rs": "rust",
                ".go": "go",
                ".rb": "ruby",
                ".cs": "csharp",
            }
            for ext in all_extensions:
                if ext in EXT_MAP:
                    detected.append(EXT_MAP[ext])

        return list(set(detected)) if detected else ["unknown"]

    def detect_test_frameworks(self, repo_path: str) -> list[str]:
        """Detect test frameworks used in the repository."""
        detected = []
        all_files = set()

        for root, dirs, files in os.walk(repo_path):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in
                       ["node_modules", "__pycache__", "venv", ".venv"]]
            for f in files:
                all_files.add(f)

        # Check for framework-specific config files
        for framework, markers in self.TEST_FRAMEWORK_MARKERS.items():
            for marker in markers:
                if marker in all_files:
                    detected.append(framework)
                    break

        # Check package.json for test script and Jest/Mocha/Vitest
        pkg_json_path = os.path.join(repo_path, "package.json")
        if os.path.exists(pkg_json_path):
            import json
            try:
                with open(pkg_json_path) as f:
                    pkg = json.load(f)
                deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                if "jest" in deps:
                    detected.append("jest")
                if "mocha" in deps:
                    detected.append("mocha")
                if "vitest" in deps:
                    detected.append("vitest")
            except (json.JSONDecodeError, IOError):
                pass

        # Check for pytest markers
        if any(f in all_files for f in ["pytest.ini", "conftest.py"]):
            detected.append("pytest")
            
        # Fallback: if there are ANY python files, assume pytest as the default test runner
        if "pytest" not in detected and any(f.endswith(".py") for f in all_files):
            detected.append("pytest")
            
        # Fallback: if there are ANY js/ts files, assume vitest as the default test runner
        if not any(fw in detected for fw in ["jest", "mocha", "vitest"]):
            if any(f.endswith(ext) for f in all_files for ext in [".js", ".jsx", ".ts", ".tsx"]):
                detected.append("vitest")

        return list(set(detected)) if detected else ["unknown"]

    def analyze(self, repo_path: str) -> dict:
        """
        Analyze repository structure — returns a summary dict.
        """
        languages = self.detect_languages(repo_path)
        test_frameworks = self.detect_test_frameworks(repo_path)

        # Count files by extension
        file_counts = {}
        total_files = 0
        for root, dirs, files in os.walk(repo_path):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in
                       ["node_modules", "__pycache__", "venv", ".venv", "dist", "build"]]
            for f in files:
                ext = os.path.splitext(f)[1]
                file_counts[ext] = file_counts.get(ext, 0) + 1
                total_files += 1

        return {
            "repo_path": repo_path,
            "languages": languages,
            "test_frameworks": test_frameworks,
            "total_files": total_files,
            "file_breakdown": file_counts,
        }
