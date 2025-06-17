# nl_to_sql_service/config_manager.py
import os
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, validator

class LLMConfig(BaseModel):
    """Configuration specific to the Language Model."""
    # In a real scenario, you might have different LLM types (OpenAI, Ollama, AzureOpenAI etc.)
    # For now, assuming Ollama-like setup but can be made more generic.
    model_provider: str = Field(default=os.getenv("NLSQL_LLM_PROVIDER", "ollama"), description="LLM provider (e.g., 'ollama', 'openai').")
    model_name: str = Field(default=os.getenv("NLSQL_LLM_MODEL_NAME", "mistral"), description="The specific model name.")
    base_url: Optional[str] = Field(default=os.getenv("NLSQL_LLM_BASE_URL", "http://localhost:11434"), description="Base URL for the LLM API (e.g., Ollama).")
    api_key: Optional[str] = Field(default=os.getenv("NLSQL_LLM_API_KEY"), description="API key for the LLM service, if required.")
    temperature: float = Field(default=float(os.getenv("NLSQL_LLM_TEMPERATURE", 0.0)), description="LLM temperature for generation.")
    # Add other LLM parameters like max_tokens, top_p if needed

class DBSchemaHandlerConfig(BaseModel):
    """Configuration for the DBSchemaHandler."""
    db_type: str = Field(default=os.getenv("NLSQL_DB_TYPE", "postgresql"), description="Database type (e.g., postgresql, mysql).")
    host: Optional[str] = Field(default=os.getenv("NLSQL_DB_HOST"), description="Database host.")
    port: Optional[int] = Field(default=None, description="Database port.") # Default to None, validator handles conversion
    username: Optional[str] = Field(default=os.getenv("NLSQL_DB_USER"), description="Database username.")
    password: Optional[str] = Field(default=os.getenv("NLSQL_DB_PASSWORD"), description="Database password.")
    database_name: Optional[str] = Field(default=os.getenv("NLSQL_DB_NAME"), description="Database name.")
    connection_string: Optional[str] = Field(default=os.getenv("NLSQL_DB_CONNECTION_STRING"), description="Full database connection string (overrides individual components if provided).")
    schema_cache_ttl_seconds: int = Field(default=int(os.getenv("NLSQL_DB_SCHEMA_CACHE_TTL_SECONDS", 3600)), description="TTL for schema cache in seconds.")

    @validator('port', pre=True, always=True)
    def _validate_port(cls, v: Any) -> Optional[int]:
        if v is None or v == '':
            # Fallback to default port based on db_type if specific logic is desired here,
            # or keep None if it should be explicitly provided or derived later.
            # For now, if not provided or empty, it remains None.
            # Pydantic v2 might handle int(None) differently, ensure compatibility or specific handling.
            # os.getenv("NLSQL_DB_PORT", 5432 if some_condition else None)
            # The default in Field was `int(os.getenv("NLSQL_DB_PORT", 5432)) if os.getenv("NLSQL_DB_PORT") else None`
            # This validator is more robust for various inputs.
            default_port_str = os.getenv("NLSQL_DB_PORT")
            if default_port_str is None or default_port_str == '': # If env var is not set or empty
                 # One could set a default based on db_type here, e.g.
                 # values = cls.model_fields # Pydantic v2 way to get other field values if needed
                 # db_type = values.get('db_type')
                 # if db_type == 'postgresql': return 5432
                 return None # Default to None if not set
            v = default_port_str

        try:
            return int(v)
        except ValueError:
            raise ValueError(f"Database port must be an integer or None. Received: {v}")

class NLToSQLConfig(BaseModel):
    """
    Main configuration model for the NL-to-SQL Service.
    Loads settings from environment variables with sensible defaults.
    """
    llm: LLMConfig = Field(default_factory=LLMConfig)

    few_shot_examples_path: str = Field(default=os.getenv("NLSQL_FEW_SHOT_PATH", "nl_to_sql_examples.json"), description="Path to the JSON file containing few-shot examples.")
    num_few_shot_examples_to_select: int = Field(default=int(os.getenv("NLSQL_NUM_FEW_SHOTS", 3)), description="Number of few-shot examples to select for the prompt.")
    few_shot_selection_strategy: str = Field(default=os.getenv("NLSQL_FEW_SHOT_STRATEGY", "hybrid"), description="Strategy for selecting few-shot examples (e.g., 'random', 'keyword', 'semantic', 'hybrid').")
    few_shot_embedding_model: Optional[str] = Field(default=os.getenv("NLSQL_FEW_SHOT_EMBEDDING_MODEL", "all-MiniLM-L6-v2"), description="Sentence transformer model for semantic selection of few-shot examples.")

    use_dynamic_schema_handling: bool = Field(default=os.getenv("NLSQL_USE_DYNAMIC_SCHEMA", "True").lower() == "true", description="Whether to use DBSchemaHandler for dynamic schema.")
    db_schema_handler: Optional[DBSchemaHandlerConfig] = Field(default_factory=DBSchemaHandlerConfig)

    schema_representation_mode: str = Field(default=os.getenv("NLSQL_SCHEMA_REPR_MODE", "create_table"), description="Mode for schema representation to LLM ('create_table', 'column_list', 'summarized_text').")
    base_prompt_template_path: str = Field(
        default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts", "base_nl_to_sql_prompt.txt"),
        description="Path to the base prompt template file, relative to this config file's directory if not absolute."
    )

    log_level: str = Field(default=os.getenv("NLSQL_LOG_LEVEL", "INFO").upper(), description="Logging level (e.g., DEBUG, INFO, WARNING, ERROR).")

    disallowed_sql_keywords: List[str] = Field(
        default_factory=lambda: [
            kw.strip().upper() for kw in os.getenv(
                "NLSQL_DISALLOWED_KEYWORDS",
                "INSERT,UPDATE,DELETE,DROP,TRUNCATE,ALTER,CREATE USER,GRANT,REVOKE"
            ).split(',') if kw.strip() # Ensure not empty string after strip
        ],
        description="SQL keywords that should be disallowed in generated queries."
    )

    class Config:
        # For Pydantic v1, env_prefix was for loading from env vars with a prefix.
        # For Pydantic v2 with pydantic-settings, behavior is slightly different.
        # The current Field(default=os.getenv(...)) pattern directly reads env vars.
        # If using pydantic-settings for .env file loading:
        # env_file = ".env"
        # env_file_encoding = 'utf-8'
        # extra = 'ignore' # Ignore extra fields from env vars or dicts
        # For Pydantic v1 'Config' inner class, these are standard options:
        env_prefix = 'NLSQL_' # This would make Pydantic try to load NLSQL_LLM_MODEL_NAME etc.
                             # but Field(default=os.getenv()) is more explicit.
                             # If we use env_prefix, then Field defaults should not include os.getenv.
                             # For clarity and direct control, os.getenv in Field is fine.
                             # If pydantic-settings is used, then env_prefix and env_file are more integrated.
                             # Let's remove env_prefix to rely on explicit os.getenv in Field defaults.
        validate_assignment = True # Ensure validation runs when fields are assigned after init
        extra = 'ignore'


    @classmethod
    def load(cls, config_path: Optional[str] = None, **kwargs: Any) -> "NLToSQLConfig":
        """
        Loads configuration.
        Priority: kwargs > environment variables > .env file (if setup in Pydantic model) > defaults.

        Note: For .env file loading with a dynamic path, `python-dotenv` package
        can be used explicitly before Pydantic model initialization, or if using
        `pydantic-settings`, the model can be configured to load a specific .env file.
        The current model primarily relies on direct os.getenv calls in Field defaults.

        Args:
            config_path: Path to a .env file to load. If provided, `python-dotenv`
                         would typically be used here to load it into the environment
                         before the Pydantic model is initialized. This example assumes
                         that if `config_path` is used, it points to a file that
                         `python-dotenv` can load, or that `pydantic-settings` is configured.
                         For simplicity with pure Pydantic, this method mostly serves as a
                         placeholder for more complex loading strategies if needed.
            **kwargs: Keyword arguments that will override any other loaded values.

        Returns:
            An instance of NLToSQLConfig.
        """
        if config_path:
            try:
                from dotenv import load_dotenv
                loaded = load_dotenv(config_path, override=True)
                if loaded:
                    print(f"Loaded .env file from: {config_path}")
                else:
                    print(f"No .env file found at: {config_path} or it was empty.")
            except ImportError:
                print("python-dotenv not installed, skipping .env file loading from path.")

        # Pydantic will automatically read environment variables that match field names
        # (if Config.env_prefix is set and matches, or if names are exact without prefix).
        # The explicit os.getenv in Field defaults already handles this.
        # Kwargs passed here will override anything loaded from env or defaults.
        return cls(**kwargs)

# Example Usage (for testing or direct script run):
if __name__ == "__main__":
    print("Loading NLToSQLConfig with defaults and environment variables...")
    # Create a dummy .env for testing if it doesn't exist
    if not os.path.exists(".test_nlsql_env"):
        with open(".test_nlsql_env", "w") as f:
            f.write("NLSQL_LLM_MODEL_NAME=test-mistral-from-env-file\n")
            f.write("NLSQL_DB_HOST=testhost.example.com\n")
            f.write("NLSQL_DISALLOWED_KEYWORDS=INSERT,UPDATE\n") # Test overriding list

    # Test loading from a specific .env file
    config_from_file = NLToSQLConfig.load(config_path=".test_nlsql_env")
    print("\n--- Config loaded from .test_nlsql_env ---")
    print(f"LLM Model: {config_from_file.llm.model_name}") # Should be test-mistral-from-env-file
    print(f"DB Host: {config_from_file.db_schema_handler.host if config_from_file.db_schema_handler else 'N/A'}") # Should be testhost.example.com
    print(f"Disallowed Keywords: {config_from_file.disallowed_sql_keywords}") # Should be ['INSERT', 'UPDATE']

    # Test loading with kwargs override
    config_with_kwargs = NLToSQLConfig.load(config_path=".test_nlsql_env", llm={"model_name": "override-model"})
    print("\n--- Config loaded with kwargs override ---")
    print(f"LLM Model: {config_with_kwargs.llm.model_name}") # Should be override-model

    # Test default loading (relies on env vars set in system or defaults)
    # Unset env vars for a cleaner test of defaults for some fields if possible,
    # or set specific ones for this test run.
    # For example, to test default LLM model if NLSQL_LLM_MODEL_NAME is not set:
    # if "NLSQL_LLM_MODEL_NAME" in os.environ: del os.environ["NLSQL_LLM_MODEL_NAME"]
    print("\n--- Config loaded with system environment variables / defaults ---")
    default_config = NLToSQLConfig.load()
    print(f"LLM Model: {default_config.llm.model_name}")
    print(f"Default Few-shot Path: {default_config.few_shot_examples_path}")
    print(f"Default Base Prompt Path: {default_config.base_prompt_template_path}")
    print(f"Default Disallowed Keywords: {default_config.disallowed_sql_keywords}")
    if default_config.db_schema_handler:
        print(f"Default DB Port: {default_config.db_schema_handler.port}") # Test validator

    # Clean up dummy .env file
    if os.path.exists(".test_nlsql_env"):
        os.remove(".test_nlsql_env")
