# nl_to_sql_service/config_manager.py
"""Configuration management for the NL-to-SQL service.

This module defines Pydantic models for managing all configurations required
by the NL-to-SQL service. It allows loading settings from environment
variables, with sensible defaults, and supports nested configuration structures
for better organization (e.g., LLM settings, Database schema handler settings).
"""
import os
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, validator

class LLMConfig(BaseModel):
    """Configuration specific to the Language Model used by the NL-to-SQL service.

    Attributes:
        model_provider: The provider of the LLM (e.g., 'ollama', 'openai').
                        Loaded from `NLSQL_LLM_PROVIDER` env var, defaults to 'ollama'.
        model_name: The specific model name to be used (e.g., 'mistral', 'gpt-3.5-turbo').
                    Loaded from `NLSQL_LLM_MODEL_NAME` env var, defaults to 'mistral'.
        base_url: The base URL for the LLM API. Relevant for self-hosted models like Ollama.
                  Loaded from `NLSQL_LLM_BASE_URL` env var, defaults to 'http://localhost:11434'.
        api_key: API key for the LLM service, if required (e.g., for OpenAI).
                 Loaded from `NLSQL_LLM_API_KEY` env var, defaults to None.
        temperature: The temperature setting for LLM generation, controlling randomness.
                     Loaded from `NLSQL_LLM_TEMPERATURE` env var, defaults to 0.0.
    """
    model_provider: str = Field(
        default=os.getenv("NLSQL_LLM_PROVIDER", "ollama"),
        description="LLM provider (e.g., 'ollama', 'openai'). Loaded from `NLSQL_LLM_PROVIDER` env var."
    )
    model_name: str = Field(
        default=os.getenv("NLSQL_LLM_MODEL_NAME", "mistral"),
        description="The specific model name. Loaded from `NLSQL_LLM_MODEL_NAME` env var."
    )
    base_url: Optional[str] = Field(
        default=os.getenv("NLSQL_LLM_BASE_URL", "http://localhost:11434"),
        description="Base URL for the LLM API (e.g., Ollama). Loaded from `NLSQL_LLM_BASE_URL` env var."
    )
    api_key: Optional[str] = Field(
        default=os.getenv("NLSQL_LLM_API_KEY"),
        description="API key for the LLM service, if required. Loaded from `NLSQL_LLM_API_KEY` env var."
    )
    temperature: float = Field(
        default=float(os.getenv("NLSQL_LLM_TEMPERATURE", 0.0)),
        description="LLM temperature for generation. Loaded from `NLSQL_LLM_TEMPERATURE` env var."
    )

class DBSchemaHandlerConfig(BaseModel):
    """Configuration for the DBSchemaHandler, managing database connection and schema retrieval.

    Attributes:
        db_type: Database type (e.g., 'postgresql', 'mysql'). From `NLSQL_DB_TYPE`.
        host: Database host. From `NLSQL_DB_HOST`.
        port: Database port. From `NLSQL_DB_PORT`.
        username: Database username. From `NLSQL_DB_USER`.
        password: Database password. From `NLSQL_DB_PASSWORD`.
        database_name: Database name. From `NLSQL_DB_NAME`.
        default_schema_name: Default schema to inspect if not specified. From `NLSQL_DB_DEFAULT_SCHEMA`.
        connection_string: Full DB connection string (overrides parts if provided). From `NLSQL_DB_CONNECTION_STRING`.
        schema_cache_ttl_seconds: TTL for schema cache. From `NLSQL_DB_SCHEMA_CACHE_TTL_SECONDS`.
    """
    db_type: str = Field(
        default=os.getenv("NLSQL_DB_TYPE", "postgresql"),
        description="Database type (e.g., postgresql, mysql). Loaded from `NLSQL_DB_TYPE` env var."
    )
    host: Optional[str] = Field(
        default=os.getenv("NLSQL_DB_HOST"),
        description="Database host. Loaded from `NLSQL_DB_HOST` env var."
    )
    port: Optional[int] = Field(
        default=None,
        description="Database port. Loaded from `NLSQL_DB_PORT` env var."
    )
    username: Optional[str] = Field(
        default=os.getenv("NLSQL_DB_USER"),
        description="Database username. Loaded from `NLSQL_DB_USER` env var."
    )
    password: Optional[str] = Field(
        default=os.getenv("NLSQL_DB_PASSWORD"),
        description="Database password. Loaded from `NLSQL_DB_PASSWORD` env var."
    )
    database_name: Optional[str] = Field( # This is the database name itself
        default=os.getenv("NLSQL_DB_NAME"),
        description="Database name. Loaded from `NLSQL_DB_NAME` env var."
    )
    default_schema_name: str = Field( # This is for schema within the database, e.g. 'public'
        default=os.getenv("NLSQL_DB_DEFAULT_SCHEMA", "public"),
        description="Default database schema to inspect (e.g., 'public'). Loaded from `NLSQL_DB_DEFAULT_SCHEMA` env var."
    )
    connection_string: Optional[str] = Field(
        default=os.getenv("NLSQL_DB_CONNECTION_STRING"),
        description="Full database connection string (overrides individual components if provided). Loaded from `NLSQL_DB_CONNECTION_STRING` env var."
    )
    schema_cache_ttl_seconds: int = Field(
        default=int(os.getenv("NLSQL_DB_SCHEMA_CACHE_TTL_SECONDS", 3600)),
        description="TTL for schema cache in seconds. Loaded from `NLSQL_DB_SCHEMA_CACHE_TTL_SECONDS` env var."
    )

    @validator('port', pre=True, always=True)
    def _validate_port(cls, v: Any, values: Dict[str, Any]) -> Optional[int]:
        """Validator for the database port."""
        env_port = os.getenv("NLSQL_DB_PORT")
        effective_value = v if v is not None else env_port
        if effective_value is None or str(effective_value).strip() == '':
            return None
        try:
            return int(effective_value)
        except ValueError:
            raise ValueError(f"Database port must be an integer or None. Received: '{effective_value}'")

class NLToSQLConfig(BaseModel):
    """Main configuration model for the NL-to-SQL Service."""
    llm: LLMConfig = Field(default_factory=LLMConfig, description="LLM configuration.")

    few_shot_examples_path: str = Field(
        default=os.getenv("NLSQL_FEW_SHOT_PATH", "nl_to_sql_examples.json"),
        description="Path to few-shot examples JSON file. From `NLSQL_FEW_SHOT_PATH`."
    )
    num_few_shot_examples_to_select: int = Field(
        default=int(os.getenv("NLSQL_NUM_FEW_SHOTS", 3)),
        description="Number of few-shot examples for prompts. From `NLSQL_NUM_FEW_SHOTS`."
    )
    few_shot_selection_strategy: str = Field(
        default=os.getenv("NLSQL_FEW_SHOT_STRATEGY", "hybrid"),
        description="Few-shot selection strategy. From `NLSQL_FEW_SHOT_STRATEGY`."
    )
    few_shot_embedding_model: Optional[str] = Field(
        default=os.getenv("NLSQL_FEW_SHOT_EMBEDDING_MODEL", "all-MiniLM-L6-v2"),
        description="Embedding model for few-shot semantic selection. From `NLSQL_FEW_SHOT_EMBEDDING_MODEL`."
    )

    use_dynamic_schema_handling: bool = Field(
        default=os.getenv("NLSQL_USE_DYNAMIC_SCHEMA", "True").lower() == "true",
        description="Use DBSchemaHandler for dynamic schema. From `NLSQL_USE_DYNAMIC_SCHEMA`."
    )
    db_schema_handler: Optional[DBSchemaHandlerConfig] = Field(
        default_factory=DBSchemaHandlerConfig,
        description="DBSchemaHandler configuration."
    )

    schema_representation_mode: str = Field(
        default=os.getenv("NLSQL_SCHEMA_REPR_MODE", "create_table"),
        description="Schema representation mode for LLM. From `NLSQL_SCHEMA_REPR_MODE`."
    )
    base_prompt_template_path: str = Field(
        default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts", "base_nl_to_sql_prompt.txt"),
        description="Path to base prompt template. From `NLSQL_PROMPT_TEMPLATE_PATH`."
    )

    log_level: str = Field(
        default=os.getenv("NLSQL_LOG_LEVEL", "INFO").upper(),
        description="Logging level. From `NLSQL_LOG_LEVEL`."
    )

    disallowed_sql_keywords: List[str] = Field(
        default_factory=lambda: [
            kw.strip().upper() for kw in os.getenv(
                "NLSQL_DISALLOWED_KEYWORDS",
                "INSERT,UPDATE,DELETE,DROP,TRUNCATE,ALTER,CREATE USER,GRANT,REVOKE"
            ).split(',') if kw.strip()
        ],
        description="Disallowed SQL keywords (uppercase, comma-separated). From `NLSQL_DISALLOWED_KEYWORDS`."
    )

    error_string_for_no_conversion: str = Field(
        default=os.getenv("NLSQL_ERROR_STRING_NO_CONVERSION", "ERROR: Cannot convert query due to ambiguity or missing schema information."),
        description="LLM's expected error string for non-conversion. From `NLSQL_ERROR_STRING_NO_CONVERSION`."
    )

    remove_trailing_semicolon: bool = Field(
        default=os.getenv("NLSQL_REMOVE_TRAILING_SEMICOLON", "True").lower() == "true",
        description="Remove trailing semicolon from generated SQL. From `NLSQL_REMOVE_TRAILING_SEMICOLON`."
    )

    # RAG specific configurations
    chroma_persist_path: str = Field(
        default=os.getenv("NLSQL_CHROMA_PATH", "./chroma_db_store_nlsql"),
        description="Path for ChromaDB persistent storage for schema embeddings. From `NLSQL_CHROMA_PATH`."
    )
    chroma_collection_name: str = Field(
        default=os.getenv("NLSQL_CHROMA_COLLECTION", "nlsql_schema_embeddings"),
        description="ChromaDB collection name for schema embeddings. From `NLSQL_CHROMA_COLLECTION`."
    )
    schema_embedding_model_name: str = Field(
        default=os.getenv("NLSQL_SCHEMA_EMBEDDING_MODEL", "all-MiniLM-L6-v2"),
        description="Sentence transformer model for embedding schema chunks. From `NLSQL_SCHEMA_EMBEDDING_MODEL`."
    )
    include_sample_values_in_chunks: bool = Field(
        default=os.getenv("NLSQL_INCLUDE_SAMPLE_VALUES_IN_CHUNKS", "False").lower() == "true",
        description="Whether to include sample data values in schema text chunks for RAG. From `NLSQL_INCLUDE_SAMPLE_VALUES_IN_CHUNKS`."
    )
    num_schema_chunks_for_prompt: int = Field(
        default=int(os.getenv("NLSQL_NUM_SCHEMA_CHUNKS", 3)),
        description="Number of schema chunks to retrieve from vector store for prompt context. From `NLSQL_NUM_SCHEMA_CHUNKS`."
    )


    class Config:
        """Pydantic model configuration."""
        validate_assignment = True
        extra = 'ignore'

    @classmethod
    def load(cls, config_path: Optional[str] = None, **kwargs: Any) -> "NLToSQLConfig":
        """Loads the NL-to-SQL service configuration."""
        if config_path:
            try:
                from dotenv import load_dotenv
                loaded = load_dotenv(config_path, override=True)
                if loaded:
                    print(f"[NLToSQLConfig] Loaded .env file from: {config_path}")
            except ImportError:
                print("[NLToSQLConfig] python-dotenv not installed, skipping .env file loading from custom path.")
            except Exception as e:
                 print(f"[NLToSQLConfig] Error loading .env file from {config_path}: {e}")

        return cls(**kwargs)

if __name__ == "__main__":
    print("Demonstrating NLToSQLConfig loading with RAG fields...")
    test_env_file_path = ".test_nlsql_env_rag_configmanager"
    with open(test_env_file_path, "w") as f:
        f.write("NLSQL_LLM_MODEL_NAME=rag_model_from_file\n")
        f.write("NLSQL_CHROMA_PATH=./test_chroma_rag\n")
        f.write("NLSQL_CHROMA_COLLECTION=test_rag_collection\n")
        f.write("NLSQL_SCHEMA_EMBEDDING_MODEL=test-embed-model\n")
        f.write("NLSQL_INCLUDE_SAMPLE_VALUES_IN_CHUNKS=True\n")
        f.write("NLSQL_DB_DEFAULT_SCHEMA=test_public\n")
        f.write("NLSQL_NUM_SCHEMA_CHUNKS=4\n") # Test new field


    print(f"\n--- Loading config with .env file: {test_env_file_path} ---")
    config_from_file = NLToSQLConfig.load(config_path=test_env_file_path)
    print(f"LLM Model: {config_from_file.llm.model_name}")
    assert config_from_file.llm.model_name == "rag_model_from_file"
    print(f"Chroma Path: {config_from_file.chroma_persist_path}")
    assert config_from_file.chroma_persist_path == "./test_chroma_rag"
    print(f"Chroma Collection: {config_from_file.chroma_collection_name}")
    assert config_from_file.chroma_collection_name == "test_rag_collection"
    print(f"Schema Embedding Model: {config_from_file.schema_embedding_model_name}")
    assert config_from_file.schema_embedding_model_name == "test-embed-model"
    print(f"Include Sample Values: {config_from_file.include_sample_values_in_chunks}")
    assert config_from_file.include_sample_values_in_chunks is True
    print(f"Num Schema Chunks for Prompt: {config_from_file.num_schema_chunks_for_prompt}")
    assert config_from_file.num_schema_chunks_for_prompt == 4
    if config_from_file.db_schema_handler:
        print(f"Default DB Schema Name: {config_from_file.db_schema_handler.default_schema_name}")
        assert config_from_file.db_schema_handler.default_schema_name == "test_public"

    # Clean up test env vars set by dotenv
    env_vars_to_clean = [
        "NLSQL_LLM_MODEL_NAME", "NLSQL_CHROMA_PATH", "NLSQL_CHROMA_COLLECTION",
        "NLSQL_SCHEMA_EMBEDDING_MODEL", "NLSQL_INCLUDE_SAMPLE_VALUES_IN_CHUNKS",
        "NLSQL_DB_DEFAULT_SCHEMA", "NLSQL_NUM_SCHEMA_CHUNKS"
    ]
    for var in env_vars_to_clean:
        if var in os.environ:
            del os.environ[var]

    if os.path.exists(test_env_file_path):
        os.remove(test_env_file_path)
    print(f"\nCleaned up dummy env file: {test_env_file_path}")
    print("\nConfig manager RAG fields demonstration finished.")
