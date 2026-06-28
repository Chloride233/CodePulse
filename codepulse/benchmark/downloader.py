"""Benchmark dataset downloader.

Handles downloading and caching benchmark datasets from known URLs.
Supports HTTP downloads, HuggingFace Hub, and GitHub repositories.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.error import URLError

if TYPE_CHECKING:
    from collections.abc import Callable

    from codepulse.benchmark.registry import BenchmarkDef

logger = logging.getLogger(__name__)

DEFAULT_CACHE_DIR = "datasets"


class DownloadError(Exception):
    """Raised when a benchmark dataset download fails."""


class BenchmarkDownloader:
    """Downloads and caches benchmark datasets.

    Args:
        cache_dir: Root directory for dataset storage (default: ``"datasets"``).
    """

    def __init__(self, cache_dir: str = DEFAULT_CACHE_DIR) -> None:
        self.cache_dir = Path(cache_dir)

    def download(
        self,
        defn: BenchmarkDef,
        *,
        force: bool = False,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> Path:
        """Download a benchmark dataset to the local cache."""
        target = self.cache_dir / defn.expected_path

        if target.exists() and not force:
            logger.info("Already cached: %s", target)
            return target

        if not defn.download_url:
            raise DownloadError(
                f"Benchmark '{defn.name}' has no download URL. "
                f"Place the data file at: {target}"
            )

        target.parent.mkdir(parents=True, exist_ok=True)

        url = defn.download_url
        if self._is_huggingface_url(url):
            self._download_huggingface(defn, target, force)
        elif self._is_github_repo_url(url):
            self._download_github_repo(defn, target, force)
        else:
            self._download_http(url, target, progress_callback)

        if not target.exists():
            raise DownloadError(f"Download completed but file not found: {target}")

        logger.info("Downloaded %s -> %s", defn.name, target)
        return target

    def remove(self, defn: BenchmarkDef) -> bool:
        """Remove a cached benchmark dataset."""
        target = self.cache_dir / defn.expected_path
        if target.exists():
            target.unlink()
            logger.info("Removed cached: %s", target)
            return True
        return False

    def get_cached_path(self, defn: BenchmarkDef) -> Path:
        """Get the expected cache path without downloading."""
        return self.cache_dir / defn.expected_path

    @staticmethod
    def _is_huggingface_url(url: str) -> bool:
        return "huggingface.co/datasets/" in url

    @staticmethod
    def _is_github_repo_url(url: str) -> bool:
        return "github.com" in url and "raw.githubusercontent.com" not in url

    @staticmethod
    def _huggingface_raw_url(url: str) -> str:
        base = url.rstrip("/")
        return f"{base}/resolve/main/data/train.jsonl"

    def _download_huggingface(
        self, defn: BenchmarkDef, target: Path, force: bool
    ) -> None:
        url = defn.download_url
        if url is None:
            raise DownloadError(f"Benchmark '{defn.name}' has no download URL.")
        raw_url = self._huggingface_raw_url(url)
        logger.info("Downloading %s from HuggingFace: %s", defn.name, raw_url)
        self._download_http(raw_url, target)

    def _download_github_repo(
        self, defn: BenchmarkDef, target: Path, force: bool
    ) -> None:
        url = defn.download_url
        if url is None:
            raise DownloadError(f"Benchmark '{defn.name}' has no download URL.")
        logger.info("Cloning %s from %s ...", defn.name, url)
        clone_dir = self.cache_dir / f".clone-{defn.name}"
        if clone_dir.exists():
            shutil.rmtree(clone_dir)

        try:
            subprocess.run(
                ["git", "clone", "--depth", "1", url, str(clone_dir)],
                capture_output=True,
                text=True,
                timeout=300,
                check=True,
            )
        except subprocess.CalledProcessError as exc:
            raise DownloadError(
                f"Git clone failed for {defn.name}: {exc.stderr}"
            ) from exc

        if not target.exists():
            found = list(clone_dir.rglob("*.jsonl")) + list(clone_dir.rglob("*.jsonl.gz"))
            if not found:
                raise DownloadError(
                    f"No JSONL files found after cloning {defn.name} "
                    f"from {defn.download_url}. "
                    f"Place the data file manually at: {target}"
                )
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(found[0], target)

        shutil.rmtree(clone_dir)

    @staticmethod
    def _download_http(
        url: str,
        target: Path,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> None:
        temp_path = target.with_suffix(".tmp")
        try:
            urllib.request.urlretrieve(url, temp_path)  # noqa: S310
        except URLError as exc:
            if temp_path.exists():
                temp_path.unlink()
            raise DownloadError(str(exc)) from exc

        shutil.move(str(temp_path), str(target))
