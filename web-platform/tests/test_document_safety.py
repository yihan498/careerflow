import io

import pytest
from fastapi import UploadFile

from api.document_jobs import DocumentJobService
from shared.errors import PlatformError


def test_file_extension_cannot_override_magic_bytes():
    with pytest.raises(PlatformError) as error:
        DocumentJobService._check_magic(b"not a pdf", ".pdf")
    assert error.value.code == "file_type_mismatch"


def test_docx_requires_zip_signature():
    with pytest.raises(PlatformError):
        DocumentJobService._check_magic(b"plain text", ".docx")

