import subprocess
import json
from dotenv import load_dotenv
import os
import logging

from azure.core.pipeline.policies import HTTPPolicy
from azure.identity import AzureDeveloperCliCredential
from azure.mgmt.web import WebSiteManagementClient
from azure.mgmt.storage import StorageManagementClient
from azure.storage.blob import BlobServiceClient
from azure.search.documents.indexes import SearchIndexClient, SearchIndexerClient
from azure.search.documents.indexes.models import (
    CustomVectorizerParameters,  
    CustomVectorizer,
    SearchField,
    SearchFieldDataType,
    HnswVectorSearchAlgorithmConfiguration,
    VectorSearchAlgorithmKind,
    VectorSearch,
    VectorSearchProfile,
    SearchIndex,
    SearchIndexerDataSourceConnection,
    SearchIndexerDataContainer,
    SearchIndexer,
    WebApiSkill,
    InputFieldMappingEntry,
    OutputFieldMappingEntry,
    FieldMapping,
    FieldMappingFunction
)
# Workaround to use the preview SDK
from azure.search.documents.indexes._generated.models import (
    SearchIndexerSkillset
)

logger = logging.getLogger(__name__)

function_name = "GetImageEmbedding"
sample_container_name = "image-embedding-sample-data"
sample_datasource_name = "image-embedding-datasource"
sample_skillset_name = "image-embedding-skillset"
sample_indexer_name = "image-embedding-indexer"




def main():
    load_azd_env()
    credential = AzureDeveloperCliCredential(tenant_id=os.environ["AZURE_TENANT_ID"])
    search_service_name = os.environ["AZURE_SEARCH_SERVICE"]
    search_index_name = os.environ["AZURE_SEARCH_INDEX"]
    search_url = f"https://{search_service_name}.search.windows.net"
    search_index_client = SearchIndexClient(endpoint=search_url, credential=credential, per_call_policies=[CustomVectorizerRewritePolicy()])
    search_indexer_client = SearchIndexerClient(endpoint=search_url, credential=credential)

    print("Uploading sample data...")
    upload_sample_data(credential)

    print("Getting function URL...")
    function_url = get_function_url(credential)

    print(f"Create or update sample index {search_index_name}...")
    create_or_update_sample_index(search_index_client, search_index_name, function_url)

    print(f"Create or update sample data source {sample_datasource_name}...")
    create_or_update_datasource(search_indexer_client, credential)

    print(f"Create or update sample skillset {sample_skillset_name}")
    create_or_update_skillset(search_indexer_client, function_url)

    print(f"Create or update sample indexer {sample_indexer_name}")
    create_or_update_indexer(search_indexer_client, search_index_name)

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

def get_function_url(credential) -> str:
    subscription_id = os.environ["AZURE_SUBSCRIPTION_ID"]
    client = WebSiteManagementClient(credential=credential, subscription_id=subscription_id)

    resource_group = os.environ["AZURE_API_SERVICE_RESOURCE_GROUP"]
    function_app_name = os.environ["AZURE_API_SERVICE"]
    embedding_function = client.web_apps.get_function(resource_group_name=resource_group, name=function_app_name, function_name=function_name)
    embedding_function_keys = client.web_apps.list_function_keys(resource_group_name=resource_group, name=function_app_name, function_name=function_name)
    function_url_template = embedding_function.invoke_url_template
    function_key = embedding_function_keys.additional_properties["default"]
    return f"{function_url_template}?code={function_key}"

def get_blob_connection_string(credential) -> str:
    subscription_id = os.environ["AZURE_SUBSCRIPTION_ID"]
    client = StorageManagementClient(credential=credential, subscription_id=subscription_id)

    resource_group = os.environ["AZURE_STORAGE_ACCOUNT_RESOURCE_GROUP"]
    storage_account_name = os.environ["AZURE_STORAGE_ACCOUNT"]
    storage_account_keys = client.storage_accounts.list_keys(resource_group, storage_account_name)
    return f"DefaultEndpointsProtocol=https;AccountName={storage_account_name};AccountKey={storage_account_keys.keys[0].value};EndpointSuffix=core.windows.net"

def upload_sample_data(credential):
    # Connect to Blob Storage
    account_url = os.environ["AZURE_STORAGE_ACCOUNT_BLOB_URL"]
    blob_service_client = BlobServiceClient(account_url=account_url, credential=credential)
    container_client = blob_service_client.get_container_client(sample_container_name)
    if not container_client.exists():
        container_client.create_container(public_access='blob')

    sample_data_directory_name = os.path.join("pictures", "nature")
    sample_data_directory = os.path.join(os.getcwd(), sample_data_directory_name)
    for filename in os.listdir(sample_data_directory):
        with open(os.path.join(sample_data_directory, filename), "rb") as f:
            blob_client = container_client.get_blob_client(filename)
            if not blob_client.exists():
                print(f"Uploading {filename}...")
                blob_client.upload_blob(data=f)

def create_or_update_sample_index(search_index_client: SearchIndexClient, search_index_name: str, custom_vectorizer_url: str):
    # Create a search index  
    # Image vectors have 1024 dimensions
    fields = [  
        SearchField(name="id", type=SearchFieldDataType.String, hidden=False, sortable=True, filterable=True, facetable=False, key=True),  
        SearchField(name="url", type=SearchFieldDataType.String, hidden=False, sortable=False, filterable=False, facetable=False),  
        SearchField(name="vector", type=SearchFieldDataType.Collection(SearchFieldDataType.Single), searchable=True, hidden=False, vector_search_dimensions=1024, vector_search_profile="hnswProfile"),  
    ]  
    
    # Configure the vector search configuration  
    vector_search = VectorSearch(  
        algorithms=[  
            HnswVectorSearchAlgorithmConfiguration(  
                name="hnsw",
                kind=VectorSearchAlgorithmKind.HNSW
            )
        ],  
        profiles=[  
            VectorSearchProfile(  
                name="hnswProfile",  
                algorithm="hnsw",  
                vectorizer="customVectorizer",  
            )
        ],  
        vectorizers=[  
            CustomVectorizer(name="customVectorizer", custom_vectorizer_parameters=CustomVectorizerParameters(uri=custom_vectorizer_url))
        ],  
    )

    # Create the search index with the semantic settings  
    index = SearchIndex(name=search_index_name, fields=fields, vector_search=vector_search)  
    search_index_client.create_or_update_index(index)

def create_or_update_datasource(search_indexer_client: SearchIndexerClient, credential):
    connection_string = get_blob_connection_string(credential)
    data_source = SearchIndexerDataSourceConnection(
        name=sample_datasource_name,
        type="azureblob",
        connection_string=connection_string,
        container=SearchIndexerDataContainer(name=sample_container_name))
    search_indexer_client.create_or_update_data_source_connection(data_source)

def create_or_update_skillset(search_indexer_client: SearchIndexerClient, custom_vectorizer_url: str):
    embedding_skill = WebApiSkill(  
        description="Skill to generate image embeddings via a custom endpoint",  
        context="/document",
        http_method="POST",
        batch_size=10, # Controls how many images are sent to the custom skill at a time
        uri=custom_vectorizer_url, 
        inputs=[
            InputFieldMappingEntry(name="imageUrl", source="/document/metadata_storage_path"),
            InputFieldMappingEntry(name="sasToken", source="/document/metadata_storage_sas_token"),  
        ],  
        outputs=[  
            OutputFieldMappingEntry(name="vector", target_name="vector")
        ],
    )
    
    skillset = SearchIndexerSkillset(  
        name=sample_skillset_name,  
        description="Skillset to generate embeddings for input images",  
        skills=[embedding_skill]
    )
    search_indexer_client.create_or_update_skillset(skillset)

def create_or_update_indexer(search_indexer_client: SearchIndexerClient, search_index_name: str):
    indexer = SearchIndexer(  
        name=sample_indexer_name,  
        description="Indexer to index documents and generate embeddings",
        skillset_name=sample_skillset_name,
        target_index_name=search_index_name,
        data_source_name=sample_datasource_name,
        # Setup field mappings so the URL of the image is both the key and in a URL field
        # https://learn.microsoft.com/azure/search/search-indexer-field-mappings?tabs=rest#example-make-a-base-encoded-field-searchable
        field_mappings=[
            FieldMapping(source_field_name="metadata_storage_path", target_field_name="url"),
            FieldMapping(source_field_name="metadata_storage_path", target_field_name="id", mapping_function=FieldMappingFunction(name="base64Encode")),
        ],
        output_field_mappings=[
            FieldMapping(source_field_name="/document/vector", target_field_name="vector")
        ]
    )

    search_indexer_client.create_or_update_indexer(indexer)

    search_indexer_client.run_indexer(sample_indexer_name)  

# Workaround required to use the preview SDK
class CustomVectorizerRewritePolicy(HTTPPolicy):
    def send(self, request):
        request.http_request.body = request.http_request.body.replace('customVectorizerParameters', 'customWebApiParameters')
        return self.next.send(request)

if __name__ == "__main__":
    main()