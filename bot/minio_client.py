from __future__ import annotations
import io
import os
import logging

logger = logging.getLogger(__name__)


class MinioClient:
    def __init__(self):
        self.enabled = os.getenv("ENABLE_MINIO", "false").lower() == "true"
        if self.enabled:
            self._connect()
        else:
            logger.info("MinIO disabled, using local file storage")

    def _connect(self):
        try:
            from minio import Minio
            self.endpoint = os.getenv("MINIO_ENDPOINT", "localhost:9000")
            self.access_key = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
            self.secret_key = os.getenv("MINIO_SECRET_KEY", "minioadmin")
            self.bucket = os.getenv("MINIO_BUCKET", "artconnect")
            self.client = Minio(
                self.endpoint,
                access_key=self.access_key,
                secret_key=self.secret_key,
                secure=False
            )
            if not self.client.bucket_exists(self.bucket):
                self.client.make_bucket(self.bucket)
            logger.info(f"Connected to MinIO")
        except Exception as e:
            logger.warning(f"MinIO not available: {e}")
            self.enabled = False
            self.client = None

    async def upload_photo(self, profile_id: int, photo_data: bytes, filename: str) -> str | None:
        if not self.enabled:
            return None
        try:
            object_name = f"profiles/{profile_id}/{filename}"
            self.client.put_object(
                self.bucket,
                object_name,
                io.BytesIO(photo_data),
                len(photo_data),
                content_type="image/jpeg"
            )
            return f"http://{self.endpoint}/{self.bucket}/{object_name}"
        except Exception as e:
            logger.error(f"Upload failed: {e}")
            return None

    async def delete_photo(self, profile_id: int, filename: str) -> bool:
        if not self.enabled:
            return False
        try:
            object_name = f"profiles/{profile_id}/{filename}"
            self.client.remove_object(self.bucket, object_name)
            return True
        except Exception as e:
            logger.error(f"Delete failed: {e}")
            return False


minio_client = MinioClient()
