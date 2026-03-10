from pathlib import Path

import setup_search_service


class FakeBlobClient:
    def __init__(self, blob_name: str, uploaded_blobs: list[str]):
        self.blob_name = blob_name
        self.uploaded_blobs = uploaded_blobs

    def exists(self) -> bool:
        return False

    def upload_blob(self, data) -> None:
        data.read()
        self.uploaded_blobs.append(self.blob_name)


class FakeContainerClient:
    def __init__(self) -> None:
        self.created_public_access: str | None = None
        self.uploaded_blobs: list[str] = []

    def exists(self) -> bool:
        return False

    def create_container(self, public_access: str) -> None:
        self.created_public_access = public_access

    def get_blob_client(self, blob_name: str) -> FakeBlobClient:
        return FakeBlobClient(blob_name, self.uploaded_blobs)


class FakeBlobServiceClient:
    def __init__(self, *, account_url: str, credential) -> None:
        self.account_url = account_url
        self.credential = credential

    def get_container_client(self, name: str) -> FakeContainerClient:
        assert name == setup_search_service.sample_container_name
        return fake_container_client


fake_container_client = FakeContainerClient()


def test_upload_sample_data_reads_only_top_level_pictures(
    monkeypatch, tmp_path: Path
) -> None:
    pictures_dir = tmp_path / "pictures"
    nested_dir = pictures_dir / "nested"
    nested_dir.mkdir(parents=True)
    (pictures_dir / "image1.jpg").write_bytes(b"root")
    (nested_dir / "image2.jpg").write_bytes(b"nested")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(
        "AZURE_STORAGE_ACCOUNT_BLOB_URL", "https://example.blob.core.windows.net"
    )
    monkeypatch.setattr(
        setup_search_service, "BlobServiceClient", FakeBlobServiceClient
    )

    fake_container_client.uploaded_blobs.clear()
    fake_container_client.created_public_access = None

    setup_search_service.upload_sample_data(credential=object())

    assert fake_container_client.created_public_access == "blob"
    assert fake_container_client.uploaded_blobs == ["image1.jpg"]
