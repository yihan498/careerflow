from unittest.mock import Mock

import pytest

from api.storage import ObjectStore


def test_download_url_forces_attachment_disposition():
    store = object.__new__(ObjectStore)
    store.bucket = "private"
    store.client = Mock()
    store.client.generate_presigned_url.return_value = "signed"
    assert store.signed_get("object", filename="resume.pdf") == "signed"
    params = store.client.generate_presigned_url.call_args.kwargs["Params"]
    assert params["ResponseContentDisposition"] == 'attachment; filename="resume.pdf"'


@pytest.mark.asyncio
async def test_prefix_deletion_paginates_until_every_object_is_removed():
    store = object.__new__(ObjectStore)
    store.bucket = "private"
    store.client = Mock()
    store.client.list_objects_v2.side_effect = [
        {
            "Contents": [{"Key": f"users/u/{index}"} for index in range(1000)],
            "IsTruncated": True,
            "NextContinuationToken": "page-2",
        },
        {"Contents": [{"Key": "users/u/1000"}], "IsTruncated": False},
    ]
    store.client.delete_objects.return_value = {}
    await store.delete_prefix("users/u/")
    assert store.client.list_objects_v2.call_count == 2
    assert store.client.delete_objects.call_count == 2
    assert store.client.list_objects_v2.call_args_list[1].kwargs["ContinuationToken"] == "page-2"
