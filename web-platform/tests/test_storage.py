from unittest.mock import Mock

from api.storage import ObjectStore


def test_download_url_forces_attachment_disposition():
    store = object.__new__(ObjectStore)
    store.bucket = "private"
    store.client = Mock()
    store.client.generate_presigned_url.return_value = "signed"
    assert store.signed_get("object", filename="resume.pdf") == "signed"
    params = store.client.generate_presigned_url.call_args.kwargs["Params"]
    assert params["ResponseContentDisposition"] == 'attachment; filename="resume.pdf"'

