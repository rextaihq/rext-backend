from io import BytesIO
from unittest.mock import Mock

import pytest
from fastapi import UploadFile
from PIL import Image

from src.utils.file_upload_utils import validate_and_store_file
from src.utils.storage import storage_service


def _png_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (16, 16), color="blue").save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.mark.asyncio
async def test_blog_image_uses_dedicated_minio_prefix(monkeypatch):
    upload_file = Mock(
        return_value=(
            "https://minio.example.com/rext-media/workspaces/workspace-1/"
            "blog-images/user-1/image.png"
        ),
    )
    monkeypatch.setattr(storage_service, "upload_file", upload_file)

    result = await validate_and_store_file(
        file=UploadFile(filename="article-image.png", file=BytesIO(_png_bytes())),
        workspace_id="workspace-1",
        allowed_types=["image/png"],
        max_size_mb=20,
        object_prefix="workspaces/workspace-1/blog-images/user-1",
    )

    object_name = upload_file.call_args.args[1]
    assert object_name.startswith(
        "workspaces/workspace-1/blog-images/user-1/",
    )
    assert result["secure_path"] == object_name
    assert result["mime_type"] == "image/png"
    assert result["url"].startswith("https://minio.example.com/")
