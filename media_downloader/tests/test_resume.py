"""
Unit tests for ResumeStateStore (Component 5 — Resume State Store).

Tests cover:
  - get() returns None when no state file exists
  - get() returns None on corrupt/invalid JSON
  - get() reconstructs a valid ResumeState from a persisted file
  - update() creates the cache directory if absent
  - update() writes a JSON file keyed by URL hash
  - update() preserves etag / last_modified / temp_path on subsequent calls
  - clear() removes the state file
  - clear() is a no-op when no file exists
  - _key() produces the correct SHA-256 hex digest
  - round-trip: update then get returns a consistent ResumeState
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from media_downloader.models import ResumeState
from media_downloader.resume import ResumeStateStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


URL = "https://example.com/video.mp4"
URL2 = "https://other.example.com/audio.m4a"


def _sha256(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()


# ---------------------------------------------------------------------------
# _key()
# ---------------------------------------------------------------------------


class TestKey:
    def test_key_is_sha256_hex_digest(self, tmp_path: Path) -> None:
        store = ResumeStateStore(cache_dir=tmp_path / ".cache")
        assert store._key(URL) == _sha256(URL)

    def test_key_is_deterministic(self, tmp_path: Path) -> None:
        store = ResumeStateStore(cache_dir=tmp_path / ".cache")
        assert store._key(URL) == store._key(URL)

    def test_different_urls_produce_different_keys(self, tmp_path: Path) -> None:
        store = ResumeStateStore(cache_dir=tmp_path / ".cache")
        assert store._key(URL) != store._key(URL2)


# ---------------------------------------------------------------------------
# get()
# ---------------------------------------------------------------------------


class TestGet:
    def test_get_returns_none_when_no_file(self, tmp_path: Path) -> None:
        store = ResumeStateStore(cache_dir=tmp_path / ".cache")
        assert store.get(URL) is None

    def test_get_returns_none_for_corrupt_json(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / ".cache"
        cache_dir.mkdir(parents=True)
        key = _sha256(URL)
        (cache_dir / f"{key}.json").write_text("not json!!!", encoding="utf-8")

        store = ResumeStateStore(cache_dir=cache_dir)
        assert store.get(URL) is None

    def test_get_returns_none_for_missing_required_fields(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / ".cache"
        cache_dir.mkdir(parents=True)
        key = _sha256(URL)
        # Missing 'bytes_written' required field
        (cache_dir / f"{key}.json").write_text(
            json.dumps({"url": URL, "temp_path": "/tmp/foo.part"}),
            encoding="utf-8",
        )
        store = ResumeStateStore(cache_dir=cache_dir)
        assert store.get(URL) is None

    def test_get_returns_resume_state_for_valid_file(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / ".cache"
        cache_dir.mkdir(parents=True)
        key = _sha256(URL)
        data = {
            "url": URL,
            "temp_path": "/tmp/video.mp4.part",
            "bytes_written": 1024,
            "total_size": 4096,
            "etag": '"abc123"',
            "last_modified": "Wed, 21 Oct 2023 07:28:00 GMT",
        }
        (cache_dir / f"{key}.json").write_text(json.dumps(data), encoding="utf-8")

        store = ResumeStateStore(cache_dir=cache_dir)
        state = store.get(URL)

        assert state is not None
        assert state.url == URL
        assert state.temp_path == Path("/tmp/video.mp4.part")
        assert state.bytes_written == 1024
        assert state.total_size == 4096
        assert state.etag == '"abc123"'
        assert state.last_modified == "Wed, 21 Oct 2023 07:28:00 GMT"

    def test_get_handles_none_optional_fields(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / ".cache"
        cache_dir.mkdir(parents=True)
        key = _sha256(URL)
        data = {
            "url": URL,
            "temp_path": "/tmp/video.mp4.part",
            "bytes_written": 0,
            "total_size": None,
            "etag": None,
            "last_modified": None,
        }
        (cache_dir / f"{key}.json").write_text(json.dumps(data), encoding="utf-8")

        store = ResumeStateStore(cache_dir=cache_dir)
        state = store.get(URL)

        assert state is not None
        assert state.total_size is None
        assert state.etag is None
        assert state.last_modified is None

    def test_get_only_returns_state_for_matching_url(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / ".cache"
        store = ResumeStateStore(cache_dir=cache_dir)
        store.update(URL, bytes_written=512)

        assert store.get(URL2) is None


# ---------------------------------------------------------------------------
# update()
# ---------------------------------------------------------------------------


class TestUpdate:
    def test_update_creates_cache_directory(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "new_dir" / ".cache"
        assert not cache_dir.exists()

        store = ResumeStateStore(cache_dir=cache_dir)
        store.update(URL, bytes_written=0)

        assert cache_dir.is_dir()

    def test_update_writes_json_file(self, tmp_path: Path) -> None:
        store = ResumeStateStore(cache_dir=tmp_path / ".cache")
        store.update(URL, bytes_written=2048)

        key = _sha256(URL)
        state_file = tmp_path / ".cache" / f"{key}.json"
        assert state_file.exists()

        data = json.loads(state_file.read_text(encoding="utf-8"))
        assert data["url"] == URL
        assert data["bytes_written"] == 2048

    def test_update_sets_bytes_written(self, tmp_path: Path) -> None:
        store = ResumeStateStore(cache_dir=tmp_path / ".cache")
        store.update(URL, bytes_written=999)

        state = store.get(URL)
        assert state is not None
        assert state.bytes_written == 999

    def test_update_with_total_size(self, tmp_path: Path) -> None:
        store = ResumeStateStore(cache_dir=tmp_path / ".cache")
        store.update(URL, bytes_written=100, total_size=10000)

        state = store.get(URL)
        assert state is not None
        assert state.total_size == 10000

    def test_update_preserves_etag_on_subsequent_call(self, tmp_path: Path) -> None:
        """Calling update again must not clobber etag written by the first call."""
        cache_dir = tmp_path / ".cache"
        cache_dir.mkdir(parents=True)
        key = _sha256(URL)
        initial = {
            "url": URL,
            "temp_path": "/tmp/video.mp4.part",
            "bytes_written": 0,
            "total_size": 8192,
            "etag": '"deadbeef"',
            "last_modified": "Mon, 01 Jan 2024 00:00:00 GMT",
        }
        (cache_dir / f"{key}.json").write_text(json.dumps(initial), encoding="utf-8")

        store = ResumeStateStore(cache_dir=cache_dir)
        store.update(URL, bytes_written=4096)

        state = store.get(URL)
        assert state is not None
        assert state.etag == '"deadbeef"'
        assert state.last_modified == "Mon, 01 Jan 2024 00:00:00 GMT"
        assert state.bytes_written == 4096

    def test_update_preserves_temp_path_on_subsequent_call(self, tmp_path: Path) -> None:
        """Subsequent update calls must not overwrite the original temp_path."""
        cache_dir = tmp_path / ".cache"
        cache_dir.mkdir(parents=True)
        key = _sha256(URL)
        original_temp = "/downloads/video.mp4.part"
        initial = {
            "url": URL,
            "temp_path": original_temp,
            "bytes_written": 0,
            "total_size": None,
            "etag": None,
            "last_modified": None,
        }
        (cache_dir / f"{key}.json").write_text(json.dumps(initial), encoding="utf-8")

        store = ResumeStateStore(cache_dir=cache_dir)
        store.update(URL, bytes_written=1000)

        state = store.get(URL)
        assert state is not None
        assert state.temp_path == Path(original_temp)

    def test_update_different_urls_write_different_files(self, tmp_path: Path) -> None:
        store = ResumeStateStore(cache_dir=tmp_path / ".cache")
        store.update(URL, bytes_written=100)
        store.update(URL2, bytes_written=200)

        state1 = store.get(URL)
        state2 = store.get(URL2)

        assert state1 is not None
        assert state2 is not None
        assert state1.bytes_written == 100
        assert state2.bytes_written == 200


# ---------------------------------------------------------------------------
# clear()
# ---------------------------------------------------------------------------


class TestClear:
    def test_clear_removes_state_file(self, tmp_path: Path) -> None:
        store = ResumeStateStore(cache_dir=tmp_path / ".cache")
        store.update(URL, bytes_written=512)

        assert store.get(URL) is not None
        store.clear(URL)
        assert store.get(URL) is None

    def test_clear_is_noop_when_no_file(self, tmp_path: Path) -> None:
        store = ResumeStateStore(cache_dir=tmp_path / ".cache")
        # Should not raise
        store.clear(URL)

    def test_clear_only_removes_matching_url(self, tmp_path: Path) -> None:
        store = ResumeStateStore(cache_dir=tmp_path / ".cache")
        store.update(URL, bytes_written=100)
        store.update(URL2, bytes_written=200)

        store.clear(URL)

        assert store.get(URL) is None
        assert store.get(URL2) is not None


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------


class TestRoundTrip:
    def test_update_then_get_is_consistent(self, tmp_path: Path) -> None:
        store = ResumeStateStore(cache_dir=tmp_path / ".cache")
        store.update(URL, bytes_written=8192, total_size=65536)

        state = store.get(URL)
        assert state is not None
        assert state.url == URL
        assert state.bytes_written == 8192
        assert state.total_size == 65536

    def test_multiple_updates_reflect_latest_bytes_written(self, tmp_path: Path) -> None:
        store = ResumeStateStore(cache_dir=tmp_path / ".cache")
        for chunk in [1024, 2048, 4096]:
            store.update(URL, bytes_written=chunk)

        state = store.get(URL)
        assert state is not None
        assert state.bytes_written == 4096

    def test_clear_after_update_removes_state(self, tmp_path: Path) -> None:
        store = ResumeStateStore(cache_dir=tmp_path / ".cache")
        store.update(URL, bytes_written=1)
        store.clear(URL)
        assert store.get(URL) is None
