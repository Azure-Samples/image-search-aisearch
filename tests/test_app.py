import pytest


@pytest.mark.asyncio
async def test_index(client):
    """Test that the index route returns successfully"""
    response = await client.get("/")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_favicon(client):
    """Test that the favicon route returns successfully"""
    response = await client.get("/favicon.ico")
    assert response.status_code == 200
    assert response.content_type.startswith("image")


@pytest.mark.asyncio
async def test_search_request_must_be_json(client):
    """Test that search endpoint requires JSON"""
    response = await client.post("/search")
    assert response.status_code == 415
    result = await response.get_json()
    assert result["error"] == "request must be json"


@pytest.mark.asyncio
async def test_search_basic(client):
    """Test basic search functionality"""
    response = await client.post(
        "/search",
        json={
            "search": "nature images",
            "size": 10,
        },
    )
    assert response.status_code == 200
    result = await response.get_json()
    assert isinstance(result, list)
    assert len(result) > 0
    # Check that results have expected structure
    for item in result:
        assert "score" in item
        assert "url" in item
        assert item["url"].startswith("https://")


@pytest.mark.asyncio
async def test_search_default_size(client):
    """Test search with default size parameter"""
    response = await client.post(
        "/search",
        json={
            "search": "photos",
        },
    )
    assert response.status_code == 200
    result = await response.get_json()
    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_search_empty_query(client):
    """Test search with empty query defaults to match all"""
    response = await client.post(
        "/search",
        json={},
    )
    assert response.status_code == 200
    result = await response.get_json()
    assert isinstance(result, list)
