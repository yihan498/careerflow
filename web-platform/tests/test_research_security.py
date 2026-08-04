import pytest

from api.research import validate_public_url
from api.schemas import DocumentCompleteRequest
from shared.errors import PlatformError


@pytest.mark.asyncio
@pytest.mark.parametrize("url", [
    "http://example.com",
    "https://127.0.0.1/source",
    "https://10.0.0.1/source",
    "https://169.254.169.254/latest/meta-data",
    "https://user:password@example.com/source",
    "https://example.com:444/source",
])
async def test_research_fetch_rejects_non_public_or_nonstandard_urls(url):
    with pytest.raises(PlatformError):
        await validate_public_url(url)


def test_internal_document_callback_rejects_extra_fields_and_oversized_outputs():
    with pytest.raises(Exception):
        DocumentCompleteRequest.model_validate({"files": [], "result": {}, "unexpected": True})
    with pytest.raises(Exception):
        DocumentCompleteRequest.model_validate({
            "files": [{
                "name": "result.pdf",
                "size": 20 * 1024 * 1024 + 1,
                "sha256": "a" * 64,
                "content_type": "application/pdf",
            }],
            "result": {},
        })
