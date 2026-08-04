from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass

import boto3
from botocore.config import Config

from .settings import Settings


@dataclass(frozen=True)
class StoredObject:
    key: str
    sha256: str
    size: int
    content_type: str


class ObjectStore:
    def __init__(self, settings: Settings):
        self.bucket = settings.r2_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.r2_endpoint_url or None,
            aws_access_key_id=settings.r2_access_key_id,
            aws_secret_access_key=settings.r2_secret_access_key,
            region_name=settings.r2_region,
            config=Config(signature_version="s3v4"),
        )

    async def put(self, key: str, data: bytes, content_type: str) -> StoredObject:
        digest = hashlib.sha256(data).hexdigest()
        await asyncio.to_thread(
            self.client.put_object,
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
            Metadata={"sha256": digest},
        )
        return StoredObject(key, digest, len(data), content_type)

    async def get(self, key: str) -> bytes:
        response = await asyncio.to_thread(self.client.get_object, Bucket=self.bucket, Key=key)
        return await asyncio.to_thread(response["Body"].read)

    async def delete_prefix(self, prefix: str) -> None:
        continuation: str | None = None
        while True:
            arguments = {"Bucket": self.bucket, "Prefix": prefix, "MaxKeys": 1000}
            if continuation:
                arguments["ContinuationToken"] = continuation
            response = await asyncio.to_thread(self.client.list_objects_v2, **arguments)
            keys = [{"Key": item["Key"]} for item in response.get("Contents", [])]
            if keys:
                deleted = await asyncio.to_thread(
                    self.client.delete_objects,
                    Bucket=self.bucket,
                    Delete={"Objects": keys, "Quiet": True},
                )
                if deleted.get("Errors"):
                    raise RuntimeError("object storage reported incomplete prefix deletion")
            if not response.get("IsTruncated"):
                break
            continuation = response.get("NextContinuationToken")
            if not continuation:
                raise RuntimeError("object storage pagination token was missing")

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self.client.delete_object, Bucket=self.bucket, Key=key)

    async def head(self, key: str) -> dict:
        return await asyncio.to_thread(self.client.head_object, Bucket=self.bucket, Key=key)

    def signed_get(self, key: str, expires: int = 300, filename: str | None = None) -> str:
        params = {"Bucket": self.bucket, "Key": key}
        if filename:
            safe_name = filename.replace('"', "").replace("\r", "").replace("\n", "")
            params["ResponseContentDisposition"] = f'attachment; filename="{safe_name}"'
        return self.client.generate_presigned_url(
            "get_object", Params=params, ExpiresIn=expires
        )

    def signed_put(self, key: str, content_type: str, expires: int = 300) -> str:
        return self.client.generate_presigned_url(
            "put_object",
            Params={"Bucket": self.bucket, "Key": key, "ContentType": content_type},
            ExpiresIn=expires,
        )
