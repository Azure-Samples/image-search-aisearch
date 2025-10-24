import os
import sys
from pathlib import Path
from unittest import mock

import pytest
import pytest_asyncio
from azure.search.documents.aio import SearchClient

# Add backend directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "app" / "backend"))

import app


class MockAzureCredential:
    """Mock credential for testing"""

    async def get_token(self, *scopes, **kwargs):
        return mock.Mock(token="mock-token", expires_on=9999999999)


class MockAsyncSearchResultsIterator:
    """Mock search results iterator for Azure AI Search"""

    def __init__(self, search_text):
        self.search_text = search_text
        # Simulate search results
        self.data = [
            [
                {
                    "metadata_storage_path": "https://test.blob.core.windows.net/pictures/nature/image1.jpg",
                    "@search.score": 0.95,
                },
                {
                    "metadata_storage_path": "https://test.blob.core.windows.net/pictures/nature/image2.jpg",
                    "@search.score": 0.85,
                },
            ]
        ]

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self.data:
            raise StopAsyncIteration
        results = self.data.pop(0)
        for result in results:
            return result
        raise StopAsyncIteration


async def mock_search(self, *args, **kwargs):
    """Mock search method for SearchClient"""
    return MockAsyncSearchResultsIterator(kwargs.get("search_text"))


@pytest.fixture
def mock_env(monkeypatch):
    """Set up mock environment variables"""
    with mock.patch.dict(os.environ, clear=True):
        monkeypatch.setenv("AZURE_SEARCH_SERVICE", "test-search-service")
        monkeypatch.setenv("AZURE_SEARCH_INDEX", "test-search-index")
        monkeypatch.setenv("AZURE_TENANT_ID", "test-tenant-id")
        monkeypatch.setenv("AZURE_CLIENT_ID", "test-client-id")
        # Set RUNNING_IN_PRODUCTION to skip azd env loading
        monkeypatch.setenv("RUNNING_IN_PRODUCTION", "1")

        # Mock both credential classes that might be used
        with mock.patch("app.AzureDeveloperCliCredential") as mock_azd_cred:
            with mock.patch("app.ManagedIdentityCredential") as mock_mi_cred:
                mock_azd_cred.return_value = MockAzureCredential()
                mock_mi_cred.return_value = MockAzureCredential()
                yield


@pytest.fixture
def mock_search_client(monkeypatch):
    """Mock Azure AI Search client"""
    monkeypatch.setattr(SearchClient, "search", mock_search)


@pytest_asyncio.fixture
async def client(mock_env, mock_search_client):
    """Create test client for Quart app"""
    quart_app = app.create_app()

    async with quart_app.test_app() as test_app:
        test_app.app.config.update({"TESTING": True})
        yield test_app.test_client()
