import json
import logging
import os
import subprocess
import base64
from typing import Annotated, cast
from pathlib import Path
from urllib.parse import unquote, urlparse

import io

from PIL import Image as PILImage
from mcp import types
from azure.identity import AzureDeveloperCliCredential, ManagedIdentityCredential
from azure.core.exceptions import ResourceNotFoundError
from azure.search.documents.aio import SearchClient
from azure.search.documents.models import VectorizableTextQuery
from azure.storage.blob.aio import BlobServiceClient
from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp.apps import AppConfig, ResourceCSP
from fastmcp.server.lifespan import lifespan
from fastmcp.tools.tool import ToolResult
from fastmcp.utilities.types import Image

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.WARNING)
logger.setLevel(logging.INFO)


@lifespan
async def app_lifespan(server):
    """Close Azure SDK clients on server shutdown."""
    try:
        yield {}
    finally:
        if _search_client is not None:
            await _search_client.close()
        if _blob_service_client is not None:
            await _blob_service_client.close()


mcp = FastMCP(
    name="ImageSearchServer",
    instructions="Search for images using natural language queries. Returns matching images from an Azure AI Search index.",
    lifespan=app_lifespan,
)

# Global search client (initialized on first use)
_search_client: SearchClient | None = None
_blob_service_client: BlobServiceClient | None = None
_credential: AzureDeveloperCliCredential | ManagedIdentityCredential | None = None
_loaded_azd_env = False

IMAGE_VIEW_URI = "ui://image-search/image-viewer.html"
IMAGE_CONTAINER_NAME = "image-embedding-sample-data"
ALLOWED_IMAGE_MIME_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}
_image_viewer_html_path = Path(__file__).with_name("image-viewer.html")


def load_image_viewer_html() -> str:
    """Load the MCP app HTML used to render blob images."""
    return _image_viewer_html_path.read_text(encoding="utf-8")


def load_azd_env():
    """Get path to current azd env file and load file using python-dotenv"""
    result = subprocess.run(
        ["azd", "env", "list", "-o", "json"], capture_output=True, text=True
    )
    if result.returncode != 0:
        raise Exception("Error loading azd env")
    env_json = json.loads(result.stdout)
    env_file_path = None
    for entry in env_json:
        if entry["IsDefault"]:
            env_file_path = entry["DotEnvPath"]
    if not env_file_path:
        raise Exception("No default azd env file found")
    logger.info(f"Loading azd env from {env_file_path}")
    load_dotenv(env_file_path, override=True)


def ensure_env_loaded() -> None:
    """Load local azd environment variables once when not in production."""
    global _loaded_azd_env
    if os.getenv("RUNNING_IN_PRODUCTION") or _loaded_azd_env:
        return
    load_azd_env()
    _loaded_azd_env = True


def get_credential() -> AzureDeveloperCliCredential | ManagedIdentityCredential:
    """Get or create the Azure credential used by service clients."""
    global _credential
    if _credential is None:
        ensure_env_loaded()
        if os.getenv("RUNNING_IN_PRODUCTION"):
            _credential = ManagedIdentityCredential(
                client_id=os.environ["AZURE_CLIENT_ID"]
            )
        else:
            _credential = AzureDeveloperCliCredential(
                tenant_id=os.environ["AZURE_TENANT_ID"]
            )
    return _credential


def get_search_client() -> SearchClient:
    """Get or create the Azure Search client."""
    global _search_client
    if _search_client is None:
        ensure_env_loaded()

        AZURE_SEARCH_SERVICE = os.environ["AZURE_SEARCH_SERVICE"]
        AZURE_SEARCH_INDEX = os.environ["AZURE_SEARCH_INDEX"]

        _search_client = SearchClient(
            endpoint=f"https://{AZURE_SEARCH_SERVICE}.search.windows.net",
            index_name=AZURE_SEARCH_INDEX,
            credential=get_credential(),
        )
    return _search_client


def get_blob_service_client() -> BlobServiceClient:
    """Get or create the Azure Blob service client."""
    global _blob_service_client
    if _blob_service_client is None:
        ensure_env_loaded()
        account_url = os.getenv("AZURE_STORAGE_ACCOUNT_BLOB_URL")
        if not account_url:
            storage_account = os.environ["AZURE_STORAGE_ACCOUNT"]
            account_url = f"https://{storage_account}.blob.core.windows.net"
        _blob_service_client = BlobServiceClient(
            account_url=account_url, credential=get_credential()
        )
    return _blob_service_client


def get_image_format(url: str) -> str:
    """Extract image format from URL/path as an IANA MIME subtype."""
    parsed_url = urlparse(url)
    extension = Path(unquote(parsed_url.path)).suffix.lower().lstrip(".")
    # "jpg" is a file extension, not a MIME subtype; image/jpg is not registered.
    if extension == "jpg":
        return "jpeg"
    if extension in {"jpeg", "png", "gif", "webp"}:
        return extension
    return "jpeg"  # Default when extension is missing/unsupported


def get_blob_reference_from_url(url: str) -> tuple[str, str]:
    """Extract container name and blob path from a blob URL."""
    parsed_url = urlparse(url)
    normalized_path = unquote(parsed_url.path.lstrip("/"))
    if not normalized_path:
        raise ValueError(f"URL has no blob path: {url}")

    path_parts = normalized_path.split("/", maxsplit=1)
    if len(path_parts) == 1:
        return IMAGE_CONTAINER_NAME, path_parts[0]
    return path_parts[0], path_parts[1]


def get_image_mime_type(filename: str) -> str:
    """Infer MIME type for supported image formats from blob filename."""
    mime_type = f"image/{get_image_format(filename)}"
    if mime_type in ALLOWED_IMAGE_MIME_TYPES:
        return mime_type
    return "image/jpeg"


THUMBNAIL_SIZE = (256, 256)


def resize_image_bytes(data: bytes, image_format: str) -> bytes:
    """Resize image to a thumbnail to reduce token usage when sending to LLM."""
    with PILImage.open(io.BytesIO(data)) as img:
        img.thumbnail(THUMBNAIL_SIZE)
        out = io.BytesIO()
        save_format = (
            "JPEG" if image_format in {"jpg", "jpeg"} else image_format.upper()
        )
        img.save(out, format=save_format)
        return out.getvalue()


@mcp.resource(
    IMAGE_VIEW_URI,
    app=AppConfig(csp=ResourceCSP(resource_domains=["https://unpkg.com"])),
)
def image_view() -> str:
    """Render images returned by display_image_files in an MCP App iframe."""
    return load_image_viewer_html()


@mcp.tool(
    app=AppConfig(resource_uri=IMAGE_VIEW_URI),
    annotations={"readOnlyHint": True},
)
async def display_image_files(
    filenames: Annotated[
        list[str], "List of blob filenames to retrieve and display in a carousel."
    ],
    descriptions: Annotated[
        list[str] | None,
        "Optional image descriptions from image_search, in the same order as filenames.",
    ] = None,
) -> ToolResult:
    """Fetch images by filename and render them in a carousel with descriptions and file details."""
    if len(filenames) < 1:
        raise ValueError("Provide at least one filename.")
    if descriptions is not None and len(descriptions) != len(filenames):
        raise ValueError(
            "Descriptions must have the same number of items as filenames."
        )

    blob_service_client = get_blob_service_client()

    image_blocks: list[types.ImageContent] = []
    image_results: list[dict[str, str | int]] = []
    for image_index, filename in enumerate(filenames):
        blob_client = blob_service_client.get_blob_client(
            container=IMAGE_CONTAINER_NAME, blob=filename
        )
        try:
            stream = await blob_client.download_blob()
            image_bytes = cast(bytes, await stream.readall())
        except ResourceNotFoundError as exc:
            raise ValueError(
                f"Blob '{filename}' was not found in container '{IMAGE_CONTAINER_NAME}'."
            ) from exc

        mime_type = get_image_mime_type(filename)
        with PILImage.open(io.BytesIO(image_bytes)) as image:
            width, height = image.size
            image_format = image.format or get_image_format(filename).upper()
        image_blocks.append(
            types.ImageContent(
                type="image",
                data=base64.b64encode(image_bytes).decode("utf-8"),
                mimeType=mime_type,
            )
        )
        image_results.append(
            {
                "filename": filename,
                "description": descriptions[image_index] if descriptions else "",
                "mimeType": mime_type,
                "width": width,
                "height": height,
                "format": image_format,
                "sizeBytes": len(image_bytes),
            }
        )

    return ToolResult(
        content=image_blocks,
        structured_content={
            "images": image_results,
        },
    )


@mcp.tool(annotations={"readOnlyHint": True})
async def image_search(
    query: Annotated[
        str, "Text description of images to find (e.g., 'sunlit mountain lake')"
    ],
    max_results: Annotated[int, "Maximum number of images to return (1-20)"] = 5,
) -> ToolResult:
    """
    Search for images matching a natural language query.

    Uses Azure AI Search with vector embeddings to find images that match
    the semantic meaning of your query. Returns the actual image data.
    """
    # Clamp max_results to reasonable bounds
    max_results = max(1, min(20, max_results))

    search_client = get_search_client()

    results = await search_client.search(
        search_text=query,
        top=max_results,
        vector_queries=[
            VectorizableTextQuery(
                k_nearest_neighbors=max_results, fields="embedding", text=query
            )
        ],
        select=["metadata_storage_path", "verbalized_image"],
    )

    blob_service_client = get_blob_service_client()

    images: list[Image] = []
    image_results: list[dict[str, str]] = []
    result_index = 0
    async for result in results:
        result_index += 1
        url = result["metadata_storage_path"]
        description = result.get("verbalized_image") or ""
        try:
            container_name, blob_name = get_blob_reference_from_url(url)
            blob_client = blob_service_client.get_blob_client(
                container=container_name, blob=blob_name
            )
            stream = await blob_client.download_blob()
            image_bytes = await stream.readall()
            image_format = get_image_format(url)
            display_name = os.path.basename(blob_name)
            if not display_name:
                display_name = f"image-{result_index}.{image_format}"
            thumbnail_bytes = resize_image_bytes(image_bytes, image_format)
            images.append(Image(data=thumbnail_bytes, format=image_format))
            image_results.append(
                {
                    "filename": blob_name,
                    "display_name": display_name,
                    "description": description,
                }
            )
            logger.info(
                f"Fetched image from {url} ({len(image_bytes)} bytes -> {len(thumbnail_bytes)} bytes thumbnail)"
            )
        except Exception as e:
            logger.error(f"Failed to fetch image from {url}: {e}")
            continue

    return ToolResult(
        content=images,
        structured_content={
            "query": query,
            "results": image_results,
        },
    )


if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8001)
