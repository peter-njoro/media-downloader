from __future__ import annotations

from media_downloader.extractors.generic import GenericHTTPExtractor


class _FakeResponse:
    def __init__(self, headers: dict[str, str]) -> None:
        self.headers = headers

    def raise_for_status(self) -> None:
        return None


class _FakeClient:
    def __init__(self, *args, **kwargs) -> None:
        pass

    def __enter__(self) -> "_FakeClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def head(self, url: str, follow_redirects: bool = True) -> _FakeResponse:
        return _FakeResponse({"content-type": "image/jpeg", "content-length": "1234"})


def test_can_handle_common_image_extensions() -> None:
    extractor = GenericHTTPExtractor()

    assert extractor.can_handle("https://example.com/video.mp4") is True
    assert extractor.can_handle("https://example.com/photo.jpeg") is True
    assert extractor.can_handle("https://example.com/photo.jpg") is True
    assert extractor.can_handle("https://example.com/not-a-media-file.txt") is False


def test_can_handle_path_segment_media_urls() -> None:
    extractor = GenericHTTPExtractor()

    assert extractor.can_handle("https://httpbin.org/image/png") is True
    assert extractor.can_handle("https://example.com/media/jpeg") is True


def test_extract_builds_manifest_from_head_response(monkeypatch) -> None:
    monkeypatch.setattr("media_downloader.extractors.generic.httpx.Client", _FakeClient)

    extractor = GenericHTTPExtractor()
    manifest = extractor.extract("https://example.com/photo.jpg")

    assert manifest.id == "https://example.com/photo.jpg"
    assert len(manifest.formats) == 1
    assert manifest.formats[0].container == "jpeg"
