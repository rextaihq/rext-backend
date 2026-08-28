from unittest.mock import Mock

from src.utils.storage import StorageService


def _storage_without_startup() -> StorageService:
    storage = StorageService.__new__(StorageService)
    storage.bucket_name = "rext-media"
    storage.available = False
    storage.last_error = "startup connection failed"
    storage.s3_client = Mock()
    return storage


def test_upload_reconnects_after_minio_becomes_available(monkeypatch):
    storage = _storage_without_startup()
    check_connection = Mock(return_value=True)
    monkeypatch.setattr(storage, "check_connection", check_connection)
    monkeypatch.setattr(
        storage,
        "get_file_url",
        Mock(return_value="http://localhost:9000/rext-media/blog/image.png"),
    )

    result = storage.upload_file(
        b"image-bytes",
        "blog/image.png",
        "image/png",
    )

    check_connection.assert_called_once_with()
    storage.s3_client.upload_fileobj.assert_called_once()
    assert result == "http://localhost:9000/rext-media/blog/image.png"
    assert storage.last_error is None


def test_connection_check_reinitializes_bucket_after_startup_failure(
    monkeypatch,
):
    storage = _storage_without_startup()
    ensure_bucket_exists = Mock()
    monkeypatch.setattr(storage, "_ensure_bucket_exists", ensure_bucket_exists)

    assert storage.check_connection() is True

    ensure_bucket_exists.assert_called_once_with()
    storage.s3_client.head_bucket.assert_called_once_with(Bucket="rext-media")
    assert storage.available is True
    assert storage.last_error is None
