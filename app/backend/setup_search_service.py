import subprocess
import json
from dotenv import load_dotenv
import os
import logging

from azure.identity import AzureDeveloperCliCredential
from azure.mgmt.storage import StorageManagementClient
from azure.storage.blob import BlobServiceClient
from azure.search.documents.indexes import SearchIndexClient, SearchIndexerClient
from azure.search.documents.indexes.models import (
    AIServicesVisionVectorizer,
    AIServicesVisionParameters,
    SearchField,
    AIServicesAccountIdentity,
    SearchFieldDataType,
    HnswAlgorithmConfiguration,
    VectorSearch,
    VectorSearchProfile,
    SearchIndex,
    SearchIndexerDataSourceConnection,
    SearchIndexerDataContainer,
    SearchIndexer,
    VisionVectorizeSkill,
    ChatCompletionSkill,
    InputFieldMappingEntry,
    OutputFieldMappingEntry,
    SearchableField,
    SimpleField,
    LexicalAnalyzerName,
    # Projection & indexing parameter related
    SearchIndexerIndexProjection,
    SearchIndexerIndexProjectionSelector,
    SearchIndexerIndexProjectionsParameters,
    IndexProjectionMode,
    IndexingParameters,
    IndexingParametersConfiguration,
    BlobIndexerImageAction,
)

# (Removed unused Input/OutputFieldMappingEntry imports; using raw field mappings only)
# Some preview constructs (skillset) still require generated models import
from azure.search.documents.indexes._generated.models import SearchIndexerSkillset

logger = logging.getLogger(__name__)

sample_container_name = "image-embedding-sample-data"
sample_datasource_name = "image-embedding-datasource"
sample_indexer_name = "image-embedding-indexer"
sample_skillset_name = "image-vision-vectorize-skillset"


def get_optional_env(var_name: str) -> str | None:
    """Return a stripped environment variable value, or None when missing/empty."""
    value = os.environ.get(var_name)
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def main():
    load_azd_env()
    credential = AzureDeveloperCliCredential(tenant_id=os.environ["AZURE_TENANT_ID"])
    search_service_name = os.environ["AZURE_SEARCH_SERVICE"]
    search_index_name = os.environ["AZURE_SEARCH_INDEX"]
    vision_endpoint = os.environ["AZURE_COMPUTERVISION_ACCOUNT_URL"]
    chat_completion_uri = get_optional_env("AZURE_OPENAI_CHAT_COMPLETION_URI")

    search_url = f"https://{search_service_name}.search.windows.net"
    search_index_client = SearchIndexClient(endpoint=search_url, credential=credential)
    search_indexer_client = SearchIndexerClient(
        endpoint=search_url, credential=credential
    )

    print("Uploading sample data...")
    upload_sample_data(credential)

    print(f"Create or update sample index {search_index_name}...")
    create_or_update_sample_index(
        search_index_client, search_index_name, vision_endpoint
    )

    print(f"Create or update sample data source {sample_datasource_name}...")
    create_or_update_datasource(search_indexer_client, credential)

    print(f"Create or update vision skillset {sample_skillset_name}...")
    create_or_update_skillset(
        search_indexer_client, vision_endpoint, chat_completion_uri
    )

    print(f"Create or update sample indexer {sample_indexer_name}")
    create_or_update_indexer(search_indexer_client, search_index_name)


def load_azd_env():
    """Get path to current azd env file and load file using python-dotenv"""
    result = subprocess.run(
        "azd env list -o json", shell=True, capture_output=True, text=True
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


def get_blob_connection_string(credential) -> str:
    subscription_id = os.environ["AZURE_SUBSCRIPTION_ID"]
    client = StorageManagementClient(
        credential=credential, subscription_id=subscription_id
    )

    resource_group = os.environ["AZURE_STORAGE_ACCOUNT_RESOURCE_GROUP"]
    storage_account_name = os.environ["AZURE_STORAGE_ACCOUNT"]
    storage_account_keys = client.storage_accounts.list_keys(
        resource_group, storage_account_name
    )
    return f"DefaultEndpointsProtocol=https;AccountName={storage_account_name};AccountKey={storage_account_keys.keys[0].value};EndpointSuffix=core.windows.net"


def upload_sample_data(credential):
    # Connect to Blob Storage
    account_url = os.environ["AZURE_STORAGE_ACCOUNT_BLOB_URL"]
    blob_service_client = BlobServiceClient(
        account_url=account_url, credential=credential
    )
    container_client = blob_service_client.get_container_client(sample_container_name)
    if not container_client.exists():
        container_client.create_container(public_access="blob")

    sample_data_directory_name = os.path.join("pictures", "clothes")
    sample_data_directory = os.path.join(os.getcwd(), sample_data_directory_name)
    for filename in os.listdir(sample_data_directory):
        with open(os.path.join(sample_data_directory, filename), "rb") as f:
            blob_client = container_client.get_blob_client(filename)
            if not blob_client.exists():
                print(f"Uploading {filename}...")
                blob_client.upload_blob(data=f)


def create_or_update_sample_index(
    search_index_client: SearchIndexClient, search_index_name: str, vision_endpoint: str
):
    """Create or update the Azure AI Search index using built-in AI Vision vectorizer with projections.

    This version mirrors the multimodal sample approach:
      * Normalized image generation (via indexer parameters)
      * VisionVectorizeSkill runs over /document/normalized_images/*
      * Skill output 'vector' is projected/mapped to index field 'embedding'
      * Parent (original blob) document is skipped; only projected image docs are indexed
    """
    fields = [
        SearchableField(
            name="id",
            type=SearchFieldDataType.String,
            key=True,
            filterable=True,
            analyzer_name=LexicalAnalyzerName.KEYWORD,
        ),
        SearchableField(
            name="document_id",
            type=SearchFieldDataType.String,
            key=False,
            filterable=True,
            analyzer_name=LexicalAnalyzerName.KEYWORD,
        ),
        SearchField(
            name="embedding",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            stored=False,
            vector_search_dimensions=1024,
            vector_search_profile_name="images_search_profile",
        ),
        SimpleField(
            name="metadata_storage_path",
            type=SearchFieldDataType.String,
            filterable=True,
        ),
        SearchableField(
            name="verbalized_image",
            type=SearchFieldDataType.String,
            searchable=True,
        ),
    ]

    # Configure vector search with built-in AI Vision vectorizer
    vector_search = VectorSearch(
        algorithms=[HnswAlgorithmConfiguration(name="images_hnsw_config")],
        profiles=[
            VectorSearchProfile(
                name="images_search_profile",
                algorithm_configuration_name="images_hnsw_config",
                vectorizer_name="images-vision-vectorizer",
            )
        ],
        vectorizers=[
            AIServicesVisionVectorizer(
                vectorizer_name="images-vision-vectorizer",
                ai_services_vision_parameters=AIServicesVisionParameters(
                    resource_uri=vision_endpoint,
                    model_version="2023-04-15",
                ),
            )
        ],
    )

    index = SearchIndex(
        name=search_index_name, fields=fields, vector_search=vector_search
    )
    search_index_client.create_or_update_index(index)


def create_or_update_datasource(search_indexer_client: SearchIndexerClient, credential):
    connection_string = get_blob_connection_string(credential)
    data_source = SearchIndexerDataSourceConnection(
        name=sample_datasource_name,
        type="azureblob",
        connection_string=connection_string,
        container=SearchIndexerDataContainer(name=sample_container_name),
    )
    search_indexer_client.create_or_update_data_source_connection(data_source)


def create_or_update_indexer(
    search_indexer_client: SearchIndexerClient, search_index_name: str
):
    # Enable normalized image generation so the skill can vectorize consistent sized inputs.
    indexing_parameters = IndexingParameters(
        configuration=IndexingParametersConfiguration(
            image_action=BlobIndexerImageAction.GENERATE_NORMALIZED_IMAGES,
            query_timeout=None,
        )
    )
    indexer = SearchIndexer(
        name=sample_indexer_name,
        description="Indexer to index normalized images and generate embeddings",
        skillset_name=sample_skillset_name,
        target_index_name=search_index_name,
        data_source_name=sample_datasource_name,
        parameters=indexing_parameters,
    )
    search_indexer_client.create_or_update_indexer(indexer)
    search_indexer_client.run_indexer(sample_indexer_name)


# Prompt for image verbalization skill
IMAGE_VERBALIZATION_SYSTEM_PROMPT = """You are tasked with generating concise, accurate descriptions of images, figures, diagrams, or charts in documents. The goal is to capture the key information and meaning conveyed by the image without including extraneous details like style, colors, visual aesthetics, or size.

Instructions:
Content Focus: Describe the core content and relationships depicted in the image.

For diagrams, specify the main elements and how they are connected or interact.
For charts, highlight key data points, trends, comparisons, or conclusions.
For figures or technical illustrations, identify the components and their significance.
Clarity & Precision: Use concise language to ensure clarity and technical accuracy. Avoid subjective or interpretive statements.

Avoid Visual Descriptors: Exclude details about:

Colors, shading, and visual styles.
Image size, layout, or decorative elements.
Fonts, borders, and stylistic embellishments.
Context: If relevant, relate the image to the broader content of the technical document or the topic it supports."""


def create_or_update_skillset(
    search_indexer_client: SearchIndexerClient,
    vision_endpoint: str,
    chat_completion_uri: str | None = None,
):
    """Create or update VisionVectorizeSkill with index projections.

    Skill runs over each normalized image produced by the blob indexer. The projection selector maps the
    skill output (vector) to the index field 'embedding' and copies down metadata_storage_path.
    Optionally includes a ChatCompletionSkill for image verbalization if chat_completion_uri is provided.
    Parent documents are skipped (only normalized image docs indexed).
    """
    skills = []

    vision_skill = VisionVectorizeSkill(
        name="visionvectorizer",
        context="/document/normalized_images/*",
        # Use 'image' input so the skill gets the actual generated normalized image content.
        inputs=[
            InputFieldMappingEntry(name="image", source="/document/normalized_images/*")
        ],
        outputs=[OutputFieldMappingEntry(name="vector")],
        model_version="2023-04-15",
    )
    skills.append(vision_skill)

    # Add image verbalization skill if chat completion URI is provided
    if chat_completion_uri:
        print(
            "Chat completion URI provided; adding image verbalization skill to skillset"
        )
        logger.info(
            "Chat completion URI provided; adding image verbalization skill to skillset"
        )
        verbalization_skill = ChatCompletionSkill(
            name="image-verbalization",
            description="GenAI Prompt skill for image verbalization",
            context="/document/normalized_images/*",
            uri=chat_completion_uri,
            inputs=[
                InputFieldMappingEntry(
                    name="systemMessage",
                    source=f"='{IMAGE_VERBALIZATION_SYSTEM_PROMPT}'",
                ),
                InputFieldMappingEntry(
                    name="userMessage",
                    source="='Please describe this image.'",
                ),
                InputFieldMappingEntry(
                    name="image",
                    source="/document/normalized_images/*/data",
                ),
            ],
            outputs=[
                OutputFieldMappingEntry(name="response", target_name="verbalizedImage")
            ],
        )
        skills.append(verbalization_skill)
    else:
        print(
            "AZURE_OPENAI_CHAT_COMPLETION_URI not set; skipping image verbalization skill"
        )
        logger.warning(
            "AZURE_OPENAI_CHAT_COMPLETION_URI not set; skipping image verbalization skill"
        )

    projection = SearchIndexerIndexProjection(
        selectors=[
            SearchIndexerIndexProjectionSelector(
                target_index_name=os.environ["AZURE_SEARCH_INDEX"],
                parent_key_field_name="document_id",
                source_context="/document/normalized_images/*",
                # Map skill output vector to embedding field & copy metadata_storage_path
                mappings=[
                    InputFieldMappingEntry(
                        name="embedding", source="/document/normalized_images/*/vector"
                    ),
                    InputFieldMappingEntry(
                        name="metadata_storage_path",
                        source="/document/metadata_storage_path",
                    ),
                    InputFieldMappingEntry(
                        name="verbalized_image",
                        source="/document/normalized_images/*/verbalizedImage",
                    ),
                ],
            )
        ],
        parameters=SearchIndexerIndexProjectionsParameters(
            projection_mode=IndexProjectionMode.SKIP_INDEXING_PARENT_DOCUMENTS
        ),
    )

    skillset = SearchIndexerSkillset(
        name=sample_skillset_name,
        skills=skills,
        index_projection=projection,
        cognitive_services_account=AIServicesAccountIdentity(
            subdomain_url=vision_endpoint, description="AI Services Vision Vectorizer"
        ),
    )
    search_indexer_client.create_or_update_skillset(skillset)


if __name__ == "__main__":
    main()
