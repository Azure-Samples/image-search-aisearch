import os
import logging
from pathlib import Path
import subprocess
import json

from azure.identity import AzureDeveloperCliCredential, ManagedIdentityCredential
from quart import (
    Blueprint,
    Quart,
    current_app,
    jsonify,
    request,
    send_from_directory,
)
import mimetypes
from azure.search.documents.aio import SearchClient
from azure.search.documents.models import VectorizableTextQuery
from dotenv import load_dotenv

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

CONFIG_SEARCH_CLIENT = "search_client"

bp = Blueprint("routes", __name__, static_folder="static")
# Fix Windows registry issue with mimetypes
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")

@bp.route("/")
async def index():
    return await bp.send_static_file("index.html")

@bp.route("/favicon.ico")
async def favicon():
    return await bp.send_static_file("favicon.ico")

@bp.route("/assets/<path:path>")
async def assets(path):
    return await send_from_directory(Path(__file__).resolve().parent / "static" / "assets", path)

@bp.route("/search", methods=["POST"])
async def search():
    if not request.is_json:
        return jsonify({"error": "request must be json"}), 415
    request_json = await request.get_json()
    search_text = request_json.get("search", "*")
    size = request_json.get("size", 10)
    search_client: SearchClient = current_app.config[CONFIG_SEARCH_CLIENT]
    results = await search_client.search(
        search_text=None,
        top=size,
        vector_queries=[
            VectorizableTextQuery(
                k=size,
                fields="vector",
                text=search_text
            )
        ],
        select="url"
    )
    response_results = []
    async for result in results:
        response_results.append({
            "score": result["@search.score"],
            "url": result["url"]
        })
    return jsonify(response_results)

@bp.before_app_serving
def setup_clients():
    AZURE_SEARCH_SERVICE = os.environ["AZURE_SEARCH_SERVICE"]
    AZURE_SEARCH_INDEX = os.environ["AZURE_SEARCH_INDEX"]
    if os.getenv("WEBSITE_HOSTNAME"):
        credential = ManagedIdentityCredential()
    else:
        credential = AzureDeveloperCliCredential(tenant_id=os.environ["AZURE_TENANT_ID"])
    search_client = SearchClient(
        endpoint=f"https://{AZURE_SEARCH_SERVICE}.search.windows.net",
        index_name=AZURE_SEARCH_INDEX,
        credential=credential
    )
    current_app.config[CONFIG_SEARCH_CLIENT] = search_client

def load_azd_env():
    """Get path to current azd env file and load file using python-dotenv"""
    result = subprocess.run("azd env list -o json", shell=True, capture_output=True, text=True)
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

def create_app():
    app = Quart(__name__)
    app.register_blueprint(bp)

    # Level should be one of https://docs.python.org/3/library/logging.html#logging-levels
    default_level = "INFO"  # In development, log more verbosely
    if os.getenv("WEBSITE_HOSTNAME"):  # In production, don't log as heavily
        default_level = "WARNING"
    logging.basicConfig(level=os.getenv("APP_LOG_LEVEL", default_level))

    if not os.getenv("WEBSITE_HOSTNAME"):
        load_azd_env()
        
    return app