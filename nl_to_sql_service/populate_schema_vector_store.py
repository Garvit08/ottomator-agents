# nl_to_sql_service/populate_schema_vector_store.py
"""Script to populate the ChromaDB vector store with database schema information.

This script initializes the necessary handlers (database schema, schema processor,
vector store), fetches detailed schema information from the target database,
processes it into embeddable chunks, and then populates a ChromaDB vector
store with these chunks and their embeddings.

It is intended to be run as a standalone script for initial schema population
or for updates when the database schema changes significantly.
"""
import logging
import os
import sys

# Ensure the package root is in sys.path for direct script execution
PACKAGE_PARENT = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, os.path.normpath(PACKAGE_PARENT))

try:
    from nl_to_sql_service.config_manager import NLToSQLConfig
    from nl_to_sql_service.db_schema_handler import DBSchemaHandler
    from nl_to_sql_service.schema_processor import SchemaProcessor
    from nl_to_sql_service.vector_store_handler import VectorStoreHandler
except ImportError as e:
    print(f"Error: Failed to import necessary modules. Ensure the package is structured correctly and all dependencies are installed: {e}")
    sys.exit(1)

# Setup basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def populate_vector_store():
    """
    Main function to orchestrate the schema population process.
    """
    logger.info("Starting schema vector store population process...")

    # 1. Load Configuration
    try:
        # Load configuration using the .load() classmethod which can also handle .env files
        # if python-dotenv is installed and a path is provided.
        # For this script, it will primarily load from environment variables or defaults.
        config = NLToSQLConfig.load()
        logger.info("Configuration loaded successfully.")
        # Override log level for this script if needed, or rely on NLSQL_LOG_LEVEL
        logger.setLevel(config.log_level.upper())


    except Exception as e:
        logger.error(f"Failed to load NLToSQLConfig: {e}", exc_info=True)
        return

    # Verify necessary configurations
    if not config.use_dynamic_schema_handling or not config.db_schema_handler:
        logger.error("Dynamic schema handling is disabled or DB schema handler config is missing. Cannot proceed.")
        return

    db_config_dict = config.db_schema_handler.model_dump()
    if not (db_config_dict.get("host") or db_config_dict.get("connection_string")):
        logger.error("DBSchemaHandler configuration is missing 'host' or 'connection_string'. Cannot proceed.")
        return

    # 2. Initialize Handlers
    logger.info("Initializing handlers...")
    try:
        db_handler = DBSchemaHandler(
            db_config=db_config_dict,
            logger=logging.getLogger("DBSchemaHandler"), # Pass specific logger
            cache_ttl_seconds=config.db_schema_handler.schema_cache_ttl_seconds
        )
        schema_processor = SchemaProcessor(logger=logging.getLogger("SchemaProcessor"))

        # Pass vector store specific config to VectorStoreHandler
        # This assumes NLToSQLConfig has these fields directly or via a nested model.
        # Based on previous step, they are flat on NLToSQLConfig.
        vector_store_handler = VectorStoreHandler(
            config=config, # Pass the whole config for now, VectorStoreHandler will pick relevant fields
                           # Alternatively, create a specific config object for it.
            logger=logging.getLogger("VectorStoreHandler")
        )
        logger.info("All handlers initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize one or more handlers: {e}", exc_info=True)
        return

    # 3. Fetch Detailed Schema
    logger.info("Fetching detailed schema information from the database...")
    try:
        # Use the default schema name from the DB handler config
        schema_to_fetch = config.db_schema_handler.default_schema_name
        detailed_schema_info = db_handler.get_schema_representation(
            schema_name=schema_to_fetch,
            mode="structured_dict" # Fetch the rich structured data
        )
        if not detailed_schema_info or not isinstance(detailed_schema_info, dict):
            logger.error(f"Failed to fetch schema information or received empty/invalid data for schema '{schema_to_fetch}'. Cannot proceed.")
            return
        logger.info(f"Successfully fetched schema for {len(detailed_schema_info)} tables/views from schema '{schema_to_fetch}'.")
    except Exception as e:
        logger.error(f"An error occurred during schema fetching: {e}", exc_info=True)
        return

    # 4. Process Schema into Chunks
    logger.info("Processing schema into embeddable chunks...")
    try:
        schema_chunks = schema_processor.create_schema_chunks(
            detailed_schema_info,
            include_sample_values=config.include_sample_values_in_chunks
        )
        if not schema_chunks:
            logger.warning("No schema chunks were created. Check schema details or processor logic.")
            # Depending on whether this is an error or acceptable, either return or proceed.
            # For now, assume it's okay if some schemas might yield no chunks.
        logger.info(f"Successfully processed schema into {len(schema_chunks)} chunks.")
    except Exception as e:
        logger.error(f"An error occurred during schema processing: {e}", exc_info=True)
        return

    # 5. Populate Vector Store
    if not schema_chunks:
        logger.info("No schema chunks to populate into the vector store. Exiting.")
        return

    logger.info(f"Populating vector store with {len(schema_chunks)} schema chunks...")
    try:
        vector_store_handler.populate_vector_store(schema_chunks)
        logger.info("Vector store population completed successfully.")
    except Exception as e:
        logger.error(f"An error occurred during vector store population: {e}", exc_info=True)
        return

    logger.info("Schema vector store population process finished.")

if __name__ == "__main__":
    # This allows the script to be run directly.
    # Ensure that environment variables for NLToSQLConfig are set,
    # especially for database connection details (NLSQL_DB_HOST, etc.)
    # and ChromaDB paths (NLSQL_CHROMA_PATH, etc.).

    # Example: You might set these in your shell before running, or use a .env file
    # export NLSQL_DB_HOST=localhost
    # export NLSQL_DB_USER=youruser
    # export NLSQL_DB_PASSWORD=yourpass
    # export NLSQL_DB_NAME=yourdb
    # export NLSQL_CHROMA_PATH="./my_chroma_store"
    # export NLSQL_CHROMA_COLLECTION="my_schema_collection"
    # export NLSQL_LOG_LEVEL=DEBUG

    print("Executing populate_schema_vector_store.py as script.")
    print("Ensure required environment variables for database and ChromaDB are set.")
    populate_vector_store()

```
