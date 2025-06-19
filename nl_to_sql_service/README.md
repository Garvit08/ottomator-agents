# NL-to-SQL Service

## Overview

The NL-to-SQL Service is a Python-based component designed to convert natural language questions into SQL queries, primarily targeting TimescaleDB (and PostgreSQL) databases. It leverages a Retrieval Augmented Generation (RAG) approach, utilizing a Large Language Model (LLM) enhanced with dynamic, contextually relevant database schema information. The service aims to be a production-grade, configurable, and extensible module for enabling natural language interaction with complex time-series databases.

## Features

*   **Natural Language to SQL Conversion:** Utilizes LLMs (e.g., via Ollama) to translate user questions into SQL queries.
*   **Retrieval Augmented Generation (RAG):**
    *   Dynamically injects relevant database schema information (table structures, column descriptions, comments, primary/foreign keys, TimescaleDB specifics) into the LLM prompt.
    *   Uses a local ChromaDB vector store for efficient retrieval of schema chunks.
*   **TimescaleDB-Aware Schema Processing:**
    *   `DBSchemaHandler` can identify and extract information about TimescaleDB hypertables and continuous aggregates (though full interpretation in prompts is an ongoing refinement).
*   **Advanced Few-Shot Learning:**
    *   `FewShotManager` supports multiple strategies for selecting relevant examples:
        *   `basic`: Random selection.
        *   `keyword`: Based on keyword overlap between query and example.
        *   `semantic`: Based on embedding similarity (using `sentence-transformers`).
        *   `hybrid`: Combines keyword and semantic scores.
*   **Multi-step SQL Validation:**
    *   **Syntax Validation:** Uses the `sqlglot` library to parse and validate the syntax of the generated SQL.
    *   **Semantic Validation:** Executes an `EXPLAIN` statement against the target database to check for semantic correctness (e.g., table/column existence, type compatibility).
*   **Iterative SQL Correction Loop:** If initial SQL validation fails, the service re-prompts the LLM with the original query, schema context, few-shot examples, the erroneous SQL, and the error message, attempting to correct the query up to a configurable number of times.
*   **Data Retrieval:** For validated `SELECT` queries, it can directly execute the SQL against the database and return results with pagination.
*   **Heuristic Confidence Scoring:** Assigns a confidence score (0.0 to 1.0) to the generated SQL based on the success of LLM extraction, validation steps, and correction attempts.
*   **Configuration:** Highly configurable using Pydantic models (`NLToSQLConfig` in `config_manager.py`) which are primarily populated via environment variables.
*   **Modular Design:**
    *   `NLToSQLProcessor`: Core orchestrator.
    *   `DBSchemaHandler`: Interacts with the target database for schema information and query execution.
    *   `SchemaProcessor`: Processes raw schema into structured chunks for embedding.
    *   `VectorStoreHandler`: Manages the ChromaDB vector store for schema embeddings.
    *   `FewShotManager`: Manages loading and selection of few-shot examples.
    *   `ConfigManager`: Handles service configuration.

## Architecture Overview

The service primarily follows a Retrieval Augmented Generation (RAG) pattern for NL-to-SQL conversion.

**1. Offline/Startup Phase: Schema Population**
   This phase typically runs once or periodically to populate/update the schema information in the vector store.
   1.  `DBSchemaHandler` connects to the target database and fetches detailed schema information (tables, columns, types, comments, PKs, FKs, TimescaleDB specifics).
   2.  `SchemaProcessor` takes this raw schema and transforms it into smaller, meaningful text chunks suitable for embedding (e.g., individual table DDLs with column details).
   3.  `VectorStoreHandler` takes these chunks, generates embeddings using a sentence-transformer model, and stores them in a persistent ChromaDB collection. The script `populate_schema_vector_store.py` orchestrates this.

**2. Online/Query Time Phase: NL-to-SQL Conversion**
   This phase occurs when a user submits a natural language query.
   1.  The `NLToSQLProcessor` receives the natural language query.
   2.  `FewShotManager` selects relevant few-shot examples based on the configured strategy (e.g., semantic similarity to the input query).
   3.  `VectorStoreHandler` embeds the natural language query and retrieves the most relevant schema chunks from ChromaDB.
   4.  The `NLToSQLProcessor` constructs a detailed prompt for the LLM, including:
        *   The user's natural language query.
        *   The retrieved schema chunks (providing context about relevant tables).
        *   The selected few-shot examples (guiding the LLM on desired SQL style).
        *   The target SQL dialect.
   5.  The LLM (e.g., `ChatOllama`) generates an SQL query based on the prompt.
   6.  The `NLToSQLProcessor` then:
        *   Extracts the SQL from the LLM's response.
        *   Performs syntax validation using `sqlglot`.
        *   Performs semantic validation by sending an `EXPLAIN` command to the database via `DBSchemaHandler`.
   7.  **Correction Loop:** If either validation fails, the processor re-constructs the prompt, this time including the previously generated (erroneous) SQL and the error message received. This new prompt is sent back to the LLM to attempt a correction. This loop can run for a configurable number of attempts.
   8.  A heuristic confidence score is calculated.
   9.  If a valid `SELECT` SQL query is generated and data retrieval is requested, `DBSchemaHandler` executes the query with pagination.
   10. The `NLToSQLProcessor` returns a dictionary containing the final SQL (if any), confidence score, error messages, prompt used, and query results.

**Key Modules/Classes:**
*   `nl_to_sql_processor.py`: `NLToSQLProcessor` (main orchestrator)
*   `config_manager.py`: `NLToSQLConfig` (Pydantic configuration models)
*   `db_schema_handler.py`: `DBSchemaHandler` (database interaction)
*   `schema_processor.py`: `SchemaProcessor` (schema chunking)
*   `vector_store_handler.py`: `VectorStoreHandler` (ChromaDB interaction)
*   `few_shot_manager.py`: `FewShotManager` (few-shot example handling)
*   `prompts/base_nl_to_sql_prompt.txt`: Default base prompt template.
*   `examples/nl_to_sql_examples.json`: Default few-shot examples.

## Setup and Installation

**Prerequisites:**
*   Python 3.9+

**Dependencies:**
It is recommended to use a virtual environment. Key dependencies include:
*   `langchain-community` (for `ChatOllama` and other LangChain components)
*   `psycopg2-binary` (for PostgreSQL/TimescaleDB connectivity)
*   `sqlglot` (for SQL parsing and syntax validation)
*   `sentence-transformers` (for generating embeddings for RAG and semantic search)
*   `chromadb` (for the local vector store)
*   `pydantic` (for configuration management)
*   `pydantic-settings` (for loading Pydantic models from environment variables)
*   `ollama` (Python client for Ollama, if direct interaction is needed, though `ChatOllama` is primary)
*   `cachetools` (used by `DBSchemaHandler` for caching schema)

You would typically install these from a `requirements.txt` file:
```bash
pip install -r requirements.txt
# (Assuming a requirements.txt is created for the service or project)
# Key packages:
# pip install langchain-community psycopg2-binary sqlglot sentence-transformers chromadb pydantic pydantic-settings ollama cachetools
```

**Environment Variables:**
Configuration is managed by `config_manager.py` through the `NLToSQLConfig` Pydantic model, primarily loaded from environment variables. Refer to `NLToSQLConfig` for all possible settings and their defaults.

**Required or Commonly Set Variables:**

*   **Database Connection (for `DBSchemaHandler` and schema population):**
    *   `NLSQL_DB_HOST`: Hostname of the database server.
    *   `NLSQL_DB_PORT`: Port of the database server.
    *   `NLSQL_DB_USER`: Database username.
    *   `NLSQL_DB_PASSWORD`: Database password.
    *   `NLSQL_DB_NAME`: Name of the database.
    *   _Alternatively, provide a full connection string:_
    *   `NLSQL_DB_CONNECTION_STRING`: e.g., `postgresql://user:password@host:port/dbname`

*   **LLM Configuration:**
    *   `NLSQL_LLM_MODEL_NAME`: Name of the LLM model to use with Ollama (e.g., "mistral", "llama2").
    *   `NLSQL_LLM_BASE_URL`: Base URL for the Ollama server (e.g., "http://localhost:11434").
    *   _(Other LLM provider settings like `NLSQL_LLM_PROVIDER`, `NLSQL_LLM_API_KEY` might be relevant if extending beyond Ollama via Langchain)._

*   **Vector Store (ChromaDB for RAG):**
    *   `NLSQL_CHROMA_PATH`: Filesystem path where ChromaDB should persist its data (e.g., `./nl_to_sql_service/chroma_db_store`).
    *   `NLSQL_CHROMA_COLLECTION`: Name for the ChromaDB collection storing schema embeddings (e.g., "schema_embeddings_v1").
    *   `NLSQL_SCHEMA_EMBEDDING_MODEL`: Name of the sentence-transformer model used for embedding schema chunks (e.g., "all-MiniLM-L6-v2").

*   **Paths for Prompts & Examples:**
    *   `NLSQL_FEW_SHOT_PATH`: Path to the JSON file containing few-shot examples (e.g., `nl_to_sql_service/examples/nl_to_sql_examples.json`).
    *   `NLSQL_PROMPT_TEMPLATE_PATH`: Path to the text file for the base LLM prompt template (e.g., `nl_to_sql_service/prompts/base_nl_to_sql_prompt.txt`).

*   **Logging & Behavior:**
    *   `NLSQL_LOG_LEVEL`: Logging level (e.g., "DEBUG", "INFO", "WARNING").
    *   `NLSQL_MAX_CORRECTION_ATTEMPTS`: Number of times to re-prompt LLM on validation failure.

Many settings have sensible defaults defined in `NLToSQLConfig`.

## Initial Schema Population

Before the service can effectively use RAG for schema context, the vector store needs to be populated with embeddings of your database schema. The `populate_schema_vector_store.py` script is provided for this purpose.

1.  **Ensure Environment Variables are Set:** Crucially, the database connection variables (`NLSQL_DB_HOST`, etc., or `NLSQL_DB_CONNECTION_STRING`) and ChromaDB path (`NLSQL_CHROMA_PATH`) must be correctly set in your environment for this script to access your database and save the embeddings.
2.  **Run the script:** From the root directory of the project (the directory containing `nl_to_sql_service`):
    ```bash
    python -m nl_to_sql_service.populate_schema_vector_store
    ```
    This will:
    *   Connect to your database using `DBSchemaHandler`.
    *   Fetch detailed schema information.
    *   Process it into chunks using `SchemaProcessor`.
    *   Embed these chunks and store them in ChromaDB using `VectorStoreHandler`.

Run this script whenever your database schema changes significantly.

## How to Use (API for `NLToSQLProcessor`)

Here's a basic Python code snippet demonstrating how to use the `NLToSQLProcessor`:

```python
from nl_to_sql_service.config_manager import NLToSQLConfig
from nl_to_sql_service.nl_to_sql_processor import NLToSQLProcessor
import logging # Optional: for seeing logs if not configured elsewhere

# Optional: Configure basic logging if you want to see detailed output
# logging.basicConfig(level=logging.INFO)
# logging.getLogger("nl_to_sql_service").setLevel(logging.DEBUG)


# 1. Load configuration (primarily from environment variables)
# Ensure your environment variables (NLSQL_DB_HOST, etc.) are set.
try:
    config = NLToSQLConfig.load()
except Exception as e:
    print(f"Error loading configuration: {e}")
    # Handle error appropriately, e.g., exit or use default config if applicable
    raise

# 2. Instantiate the processor
# This will initialize the LLM, DBSchemaHandler (if configured for dynamic schema),
# VectorStoreHandler, and FewShotManager based on the loaded config.
try:
    processor = NLToSQLProcessor(config=config)
except Exception as e:
    print(f"Error initializing NLToSQLProcessor: {e}")
    # Handle error appropriately
    raise

# 3. Define your natural language query
natural_language_query = "Show me the total number of alerts for equipment ID 'EQ-001' yesterday."
# Or, for example: "List all active maintenance orders created in the last week."

# 4. Call the main conversion method
# You can specify pagination for data retrieval if the query is a SELECT.
try:
    result = processor.convert_nl_to_sql(
        natural_language_query=natural_language_query,
        page_number=1,  # Optional: for paginated results
        page_size=10    # Optional: for paginated results
    )
except Exception as e:
    print(f"Error during NL-to-SQL conversion: {e}")
    result = {} # Or handle error as appropriate
    raise

# 5. Inspect the result dictionary
print("\n--- NL-to-SQL Conversion Result ---")
print(f"Natural Language Query: {natural_language_query}")
print(f"Generated SQL Query: {result.get('sql_query')}")
print(f"Confidence Score: {result.get('confidence_score')}")
print(f"Tables Used (tentative): {result.get('tables_used')}")
print(f"Error Message (Generation/Validation): {result.get('error_message')}")
print(f"Execution Error Message: {result.get('execution_error_message')}")
# print(f"LLM Reasoning (placeholder): {result.get('llm_reasoning')}")
# print(f"Prompt Sent to LLM: \n{result.get('prompt_used')}") # Can be very long

query_results = result.get('query_results')
if query_results:
    print("\n--- Query Execution Results ---")
    if query_results.get('error'):
        print(f"Execution Error: {query_results.get('error')}")
    else:
        print(f"Data Rows ({query_results.get('row_count')} returned):")
        for row in query_results.get('data', []):
            print(row)
        print(f"Page Number: {query_results.get('page_number')}")
        print(f"Page Size: {query_results.get('page_size')}")
        # print(f"Total Pages (if available): {query_results.get('total_pages')}")
else:
    print("\nNo query execution results.")

```

**Structure of the `result` dictionary from `convert_nl_to_sql`:**

*   `sql_query: Optional[str]`: The generated SQL query. `None` if conversion failed critically.
*   `confidence_score: Optional[float]`: A heuristic score (0.0-1.0) indicating confidence in the generated SQL.
*   `llm_reasoning: Optional[str]`: Currently a placeholder, intended for future use where the LLM might provide its thought process. Usually `None`.
*   `tables_used: List[str]`: A list of table names tentatively identified as relevant by the RAG process or SQL parsing (best-effort).
*   `error_message: Optional[str]`: Contains error messages if the SQL generation, syntax validation, or semantic validation failed.
*   `execution_error_message: Optional[str]`: Contains error messages if the execution of the validated SQL failed.
*   `prompt_used: Optional[str]`: The actual final prompt string that was sent to the LLM. Can be very long and is useful for debugging.
*   `query_results: Optional[Dict[str, Any]]`: Dictionary containing data if a `SELECT` query was successfully executed.
    *   `data: Optional[List[Dict[str, Any]]]`: The actual rows returned by the query.
    *   `row_count: int`: Number of rows in the `data` list for the current page.
    *   `page_number: int`: The page number of the returned data.
    *   `page_size: int`: The page size used for pagination.
    *   `error: Optional[str]`: Error message specifically from the data execution phase.
    *   `total_pages: int` (Conceptual): Total pages calculation is not yet implemented in `_execute_final_sql`.

## Configuration Details

All configurable aspects of the service are defined in `nl_to_sql_service/config_manager.py` within the `NLToSQLConfig` Pydantic model and its nested models (e.g., `LLMConfig`, `DBSchemaHandlerConfig`, `RAGConfig`). These models define default values for many settings.

The primary way to override these defaults is by setting environment variables. The environment variable names generally correspond to the Pydantic field names, prefixed with `NLSQL_` (e.g., `NLSQL_LLM_MODEL_NAME` for `llm.model_name`). Refer to the Pydantic models in `config_manager.py` for the exact field names and their corresponding environment variables.

## Running Tests

Unit tests are located in the `nl_to_sql_service/tests/` directory. To run them, navigate to the project's root directory (the one containing the `nl_to_sql_service` folder) and execute:

```bash
python -m unittest discover nl_to_sql_service/tests
```
Or, more generally:
```bash
python -m unittest discover -s nl_to_sql_service/tests -p "test_*.py"
```

Ensure that any necessary environment variables for test configurations are set, although many tests use mocking to avoid dependencies on external services like live databases or LLMs.

## TODO / Future Enhancements

*   **Advanced Confidence Scoring:** Implement a more robust mechanism for confidence scoring, potentially training a small model or using more sophisticated heuristics.
*   **Query Caching:** Introduce caching for successfully converted NLQ-SQL pairs and for query results to improve performance and reduce redundant LLM calls/DB queries.
*   **Dynamic Date/Time Filters:** More explicitly handle relative date/time expressions (e.g., "yesterday", "last week") by converting them to absolute timestamps before or during prompt construction.
*   **Support for Other Databases:** While designed with TimescaleDB/PostgreSQL in mind, extend `DBSchemaHandler` and SQL dialect considerations for other SQL databases.
*   **TimescaleDB Features Refinement:** Improve how TimescaleDB-specific features like continuous aggregates are presented in the schema context for better LLM understanding.
*   **LLM Reasoning Extraction:** If the LLM provides a structured thought process or reasoning, parse and include it in the `llm_reasoning` field of the result.
*   **Streaming Support:** For LLM responses and data retrieval, consider implementing streaming capabilities.
*   **Total Pages for Pagination:** Implement logic to calculate `total_pages` in `_execute_final_sql` if feasible (e.g., by running a `COUNT(*)` query).
*   **Batch NLQ Processing:** Add capability to process multiple natural language queries in a batch.
```
