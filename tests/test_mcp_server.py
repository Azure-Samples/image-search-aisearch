from mcp_server import get_image_title


def test_get_image_title_formats_blob_filename():
    assert get_image_title("trips/warm-river_canyon.jpg") == "Warm River Canyon"


def test_get_image_title_decodes_url_escaped_filename():
    assert get_image_title("photos/alpine%20lake.png") == "Alpine Lake"