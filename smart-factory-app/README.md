# Smart Factory RAG Application

## Overview

This project is an LLM-driven application designed to analyze and provide insights from factory machine data. It integrates various data sources to offer a comprehensive understanding of operations. The system utilizes PostgreSQL for storing time-series and operational data, Neo4j for representing a knowledge graph of equipment relationships and fault dependencies (currently schema-only, not populated with data), and a Vector Database (ChromaDB) for semantic search over text summaries derived from the SQL data.

The primary goal is to enable automated adaptation to user queries, facilitate SQL and KG-driven root-cause analysis for issues like machine downtime, and provide both real-time and historical insights into factory performance through natural language interaction.

## Features

*   **RAG (Retrieval Augmented Generation) Architecture:** Combines structured data from PostgreSQL, relational context from Neo4j (conceptual), and semantic context from a Vector DB (ChromaDB) to generate comprehensive answers.
*   **Natural Language Querying:** Allows users to ask complex questions about factory operations in natural language via a FastAPI endpoint.
*   **Dynamic SQL Generation:** Leverages LangChain's SQL Agent to dynamically generate and execute SQL queries against the PostgreSQL database based on user queries and few-shot examples.
*   **Knowledge Graph Integration (Conceptual):** Designed to use Neo4j to understand relationships between equipment, faults, and potential causes (e.g., Fault-caused_by->Sensor). Currently, the KG is schema-only.
*   **Semantic Search via Vector DB:** An ETL pipeline processes data from PostgreSQL, generates text summaries, and stores their embeddings in ChromaDB for semantic search.
*   **Hybrid Search:** The Vector Agent combines keyword-based and semantic search capabilities against the ChromaDB collection.
*   **Advanced SQL with Few-Shot Learning:** Improves the LLM's SQL generation for specific, complex queries by providing it with relevant examples of natural language questions mapped to SQL queries.
*   **Conversation Memory:** Remembers the last few turns of the conversation to understand context and answer follow-up questions more effectively.
*   **Modular Agent-Based System:** Features separate, specialized agents for handling SQL database interactions (`SQLAgent`), knowledge graph queries (`KGAgent`), vector database searches (`VectorAgent`), and orchestrating LLM interactions (`LLMInterface`).
*   **Centralized Configuration:** Application settings, including database connections, LLM parameters, and file paths, are managed via `smart_factory_app/config/config.py` and environment variables.
*   **FastAPI for Interaction:** Exposes a `/process-query/` endpoint for users or other systems to interact with the application.
*   **ETL Pipeline:** Includes a script (`etl_to_vector_db.py`) to extract data from specified SQL tables, transform it into textual summaries, and load these into the Vector DB.

## Folder Structure

The project is organized as follows:

*   **`/agents`**: Contains the core logic for different types of agents (SQL, Knowledge Graph, Vector Database, LLM interface) responsible for specific tasks.
*   **`/api`**: Includes the FastAPI application that exposes endpoints for interacting with the RAG system.
*   **`/config`**: Holds configuration files, primarily `config.py` for managing settings and credentials.
*   **`/data_pipelines`**: Contains scripts for data processing, such as the ETL job to convert SQL data to text summaries for the Vector DB.
*   **`/prompts`**: Stores text files with prompt templates used by the LLM for various tasks like query parsing and response generation.
*   **`/tests`**: Includes all unit and integration tests for the different components of the application.
*   **`README.md`**: This file, providing documentation for the project.

## Core Components and Their Roles

The application is composed of several core components, each residing in a dedicated directory:

### `/agents`
Responsible for all intelligent operations and interactions with data sources or LLMs.
*   `llm_interface.py`: Handles all direct interactions with the Large Language Model (e.g., Mistral-7B via Ollama), including query parsing and final response synthesis. It loads prompts from the `/prompts` directory.
*   `sql_agent.py`: Manages interactions with the PostgreSQL database. It uses LangChain's SQL Agent to dynamically generate and execute SQL queries based on natural language questions, enhanced with few-shot learning.
*   `sql_agent_utils.py`: Provides utility functions for the SQL agent, such as selecting relevant few-shot examples.
*   `sql_query_examples.py`: Stores a predefined list of SQL query examples used for few-shot prompting to improve SQL generation for specific tasks.
*   `kg_agent.py`: Handles connections and queries to the Neo4j Knowledge Graph, typically for fetching schema relationships or contextual data.
*   `vector_agent.py`: Manages the Vector Database (ChromaDB). It's responsible for creating text embeddings, storing them, and performing semantic/hybrid searches.

### `/api`
Exposes the application's functionality via a web interface.
*   `main.py`: Contains the FastAPI application, defining endpoints (e.g., `/process-query/`) that orchestrate the various agents and LLM calls to respond to user queries. It also manages conversation memory.

### `/config`
Centralizes application settings.
*   `config.py`: Defines configurations for database connections (PostgreSQL, Neo4j), Vector DB settings, LLM parameters (model name, API endpoint), ETL settings, and paths to prompt files. It loads values from environment variables where appropriate.

### `/data_pipelines`
Contains scripts for data preparation and processing.
*   `etl_to_vector_db.py`: Implements the Extract, Transform, Load (ETL) process to fetch data from the SQL database, convert it into textual summaries, and store these summaries (as embeddings) in the Vector Database.

### `/prompts`
Stores all prompt templates used by the LLM.
*   `parse_query_prompt.txt`: Template used by `llm_interface.py` to instruct the LLM on how to parse a user's query into structured intent and entities, considering conversation history.
*   `generate_response_prompt.txt`: Template used by `llm_interface.py` to guide the LLM in synthesizing a final answer based on gathered context from SQL, KG, Vector DB, and conversation history.

### `/tests`
Houses all automated tests.
*   Contains various `test_*.py` files (e.g., `test_api.py`, `test_sql_agent.py`) for unit and integration testing of different application components, ensuring reliability and correctness.

## Code Flow / Request Lifecycle

The typical flow of a user query through the system is as follows:
1.  A user sends a query (e.g., "What was the OEE for machine CNC-001 yesterday?") to the `/process-query/` endpoint in `smart_factory_app/api/main.py`.
2.  `main.py` retrieves the conversation history for the user.
3.  `main.py` calls `llm_interface.parse_query()`, passing the user's query and conversation history.
    *   `llm_interface.py` uses `parse_query_prompt.txt` to instruct the LLM to extract intent, entities (like `machine_id`, `timestamp`), and parameters.
4.  Based on the parsed intent and entities, `main.py` orchestrates calls to relevant agents:
    *   **SQL Agent (`sql_agent.run_sql_query`)**:
        *   A natural language question is formulated for the SQL agent, incorporating parsed entities.
        *   `sql_agent_utils.get_relevant_sql_examples()` is called with the parsed query to find relevant few-shot examples and suggested tables from `sql_query_examples.py`.
        *   These examples and table hints are prepended to the natural language question and passed to the LangChain SQL Agent, which generates and executes a SQL query.
        *   The SQL result is returned.
    *   **KG Agent (`kg_agent.query`)** (Conditional):
        *   If the intent or data from the SQL agent (e.g., a `fault_code`) suggests a need for graph traversal, a Cypher query is formulated.
        *   The KG agent executes this query against Neo4j.
    *   **Vector Agent (`vector_agent.hybrid_search`)**:
        *   The original user query, potentially augmented with context from SQL/KG results, is used for semantic search.
        *   Keywords are extracted from the parsed query for the keyword search component.
        *   The Vector Agent performs a hybrid search in ChromaDB.
5.  All retrieved information (SQL data, KG context, Vector DB documents) and the conversation history are passed to `llm_interface.generate_response()`.
    *   `llm_interface.py` uses `generate_response_prompt.txt` to instruct the LLM to synthesize a coherent, human-readable answer.
6.  The final answer from the LLM is saved to the conversation memory by `main.py`.
7.  `main.py` returns the answer along with debug information in a `QueryResponse` object to the user.

## Setup and Installation
### Dependencies
The primary dependencies include:
*   FastAPI: For the web API.
*   Uvicorn: For serving the FastAPI application.
*   LangChain: Core framework for LLM interactions, agents, and memory.
    *   `langchain_community` for components like Ollama, SQLDatabase.
    *   `langchain_openai` for the (currently placeholder) SQL Agent LLM.
*   SQLAlchemy: For database interaction (used by LangChain's SQL Agent).
*   psycopg2-binary: PostgreSQL driver.
*   neo4j: Neo4j driver for Python.
*   chromadb: Client for ChromaDB vector store.
*   sentence-transformers: For generating text embeddings.
*   pandas: Used in the ETL pipeline and potentially by agents for data handling.
*   Python 3.8+

Install dependencies using:
```bash
pip install -r requirements.txt 
# (Assuming a requirements.txt file would be created based on these)
# For now, manual installation of the listed libraries is needed.
```

### Environment Configuration
The application relies on environment variables for configuration, which are loaded by `smart_factory_app/config/config.py`. Key variables include:

*   **PostgreSQL:** `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, `DB_NAME`
*   **Neo4j:** `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`
*   **ChromaDB:** `CHROMA_PERSIST_PATH` (set to a file path for persistence, otherwise defaults to in-memory)
*   **Sentence Transformer:** `SENTENCE_TRANSFORMER_MODEL` (e.g., `all-MiniLM-L6-v2`)
*   **Ollama (LLM):** `OLLAMA_BASE_URL`, `OLLAMA_MODEL` (e.g., `mistral`)
*   **OpenAI (SQL Agent LLM Placeholder):** `OPENAI_API_KEY` (required if the SQL Agent's LLM is not replaced/mocked)
*   **ETL/API Behavior:** `ETL_USE_MOCK_DB`, `API_USE_MOCK_AGENTS` (set to `"true"` or `"false"`)

Create a `.env` file in the project root (e.g., alongside the `smart-factory-app` directory) or set these variables in your environment. Example `.env` content:
```env
DB_USER=postgres
DB_PASSWORD=your_db_password
DB_HOST=localhost
DB_PORT=5432
DB_NAME=smart_factory_db

NEO4J_URI=neo4j://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_neo4j_password

# For persistent ChromaDB, uncomment and set path:
# CHROMA_PERSIST_PATH=./chroma_data 

SENTENCE_TRANSFORMER_MODEL=all-MiniLM-L6-v2
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=mistral

# Set to your OpenAI API key if using the default SQL Agent LLM
# OPENAI_API_KEY=your_openai_api_key 

ETL_USE_MOCK_DB="true" 
API_USE_MOCK_AGENTS="true" 
```

## Running the Application
Ensure all external services (PostgreSQL, Neo4j, Ollama with the specified model) are running.

### Starting the FastAPI Server
Navigate to the `smart-factory-app/api/` directory and run:
```bash
python main.py
```
Or, for development with auto-reload (from the `smart-factory-app/api/` directory):
```bash
uvicorn main:app --reload
```
The API will typically be available at `http://localhost:8000`.

### Running the ETL Pipeline
To populate the Vector DB with summaries from your SQL database:
Navigate to the `smart-factory-app/data_pipelines/` directory and run:
```bash
python etl_to_vector_db.py
```
Set the `ETL_USE_MOCK_DB` environment variable to `"false"` in your `.env` or environment to use the actual database configured in `config.py`.

## Running Tests
Navigate to the project root directory (the one containing the `smart-factory-app` folder) and run:
```bash
python -m unittest discover smart_factory_app/tests
```

## Key Files and Functionality

### `smart_factory_app/api/main.py`
This file defines the main FastAPI application, exposing an API endpoint for users to interact with the Smart Factory RAG system. It handles incoming queries, orchestrates calls to various agents, manages conversation memory, and returns the final synthesized response.

*   **`app = FastAPI()`**: The FastAPI application instance.
*   **`conversation_memory_store = {}`**: A dictionary to store `ConversationBufferWindowMemory` instances per user, keyed by `user_id`.
*   **`get_user_memory(user_id: str) -> ConversationBufferWindowMemory`**: Retrieves or creates a conversation memory instance for a given `user_id`.
    *   `user_id`: The unique identifier for the user.
    *   Returns: A `ConversationBufferWindowMemory` object (configured with `k=3` interactions).
*   **`UserQuery(BaseModel)`**: Pydantic model defining the structure of the incoming user query.
    *   `query: str`: The natural language query from the user.
    *   `user_id: str`: Identifier for the user, used for session management and conversation history.
*   **`QueryResponse(BaseModel)`**: Pydantic model defining the structure of the API response.
    *   `answer: str`: The final, synthesized answer from the LLM.
    *   `parsed_intent: dict`: The structured output from the query parsing step (intent, entities, parameters).
    *   `debug_info: dict`: Additional information about the request processing, including intermediate data, agent inputs/outputs (snippets), and status flags.
*   **`root()` (GET `/`)**: A simple endpoint to confirm the API is running. Returns a welcome message.
*   **`process_query_endpoint(user_query: UserQuery)` (POST `/process-query/`)**: The main endpoint for handling user queries.
    *   `user_query`: An instance of `UserQuery` containing the user's query and ID.
    *   **Responsibilities**:
        1.  Loads user-specific conversation history using `get_user_memory`.
        2.  Calls `llm_interface.parse_query()`, providing the current query and loaded chat history, to extract intent and entities.
        3.  Based on the parsed data, it formulates questions or queries for the SQL, KG, and Vector agents. This includes:
            *   Constructing natural language questions for the SQL agent, enriched by parsed entities.
            *   Conditionally forming Cypher queries for the KG agent if specific conditions (e.g., `find_error_cause` intent, presence of a `fault_code`) are met.
            *   Creating a refined search query and keywords for the Vector agent, potentially augmenting the original query with context from prior agent steps.
        4.  Invokes the agents:
            *   `sql_agent.run_sql_query()`: Called with the natural language question and the parsed query dictionary (for few-shot example selection and table hinting).
            *   `kg_agent.query()`: Called if a Cypher query was formulated.
            *   `vector_agent.hybrid_search()`: Called with the refined query and keywords.
        5.  Collects results (or error/default messages) from each agent.
        6.  Calls `llm_interface.generate_response()` with all gathered context (SQL, KG, Vector data), the original user query, and the chat history to synthesize the final answer.
        7.  Saves the current user query and the AI's final response into the user's conversation memory.
        8.  Returns a `QueryResponse` object containing the final answer, parsed intent, and detailed `debug_info`.

### `smart_factory_app/agents/llm_interface.py`
This module is responsible for all direct interactions with the Large Language Model (LLM), such as Ollama. It loads prompt templates, formats them with runtime data, sends requests to the LLM, and processes the LLM's responses.

*   **`LLMInterface` Class**: Manages LLM interactions.
    *   **`__init__(self, model_name, base_url, use_mock)`**: Initializes the LLM client (either a real `Ollama` client or a `MockOllama` for testing). It loads prompt templates from files specified in `config.py`.
        *   `model_name`: Name of the Ollama model to use (e.g., "mistral").
        *   `base_url`: The base URL for the Ollama API.
        *   `use_mock`: Boolean to force usage of `MockOllama`.
    *   **`parse_query(self, user_query: str, chat_history: str = "") -> Dict[str, Any]`**: Parses the user's query using the LLM to extract structured information.
        *   `user_query`: The raw natural language query from the user.
        *   `chat_history`: Formatted string of previous conversation turns.
        *   Formats `parse_query_prompt.txt` with the query and history.
        *   Sends the formatted prompt to the LLM and expects a JSON string as output.
        *   Parses the JSON into a Python dictionary containing `intent`, `machine_id`, `timestamp`/`timestamp_range`, and `parameters`.
        *   Returns: A dictionary with the parsed query components.
    *   **`generate_response(self, sql_data, kg_context, vector_context, user_query, chat_history: str = "") -> str`**: Generates a final, synthesized natural language response based on all gathered context.
        *   `sql_data`, `kg_context`, `vector_context`: Strings or lists of strings containing information retrieved by other agents.
        *   `user_query`: The original user query.
        *   `chat_history`: Formatted string of previous conversation turns.
        *   Formats `generate_response_prompt.txt` with all provided context.
        *   Sends the formatted prompt to the LLM.
        *   Returns: The LLM's textual response.
*   **`MockOllama` Class**: A mock LLM class for testing, simulating LLM responses based on keywords in the prompt.
*   **`load_prompt_template(file_path: str) -> Optional[str]`**: Utility function to load prompt text from a file.

### `smart_factory_app/agents/sql_agent.py`
This module handles interactions with the PostgreSQL database using LangChain's SQL Agent capabilities. It's responsible for taking a natural language question, optionally using few-shot examples and table hints, and then leveraging an LLM to generate and execute SQL queries.

*   **Global Variables**: `llm` (OpenAI placeholder), `db` (SQLDatabase instance), `agent_executor` (LangChain SQL Agent). These are initialized at module load.
*   **`run_sql_query(natural_language_query: str, parsed_query_dict: Optional[Dict[str, Any]] = None) -> tuple[str, list[str]]`**: The primary function to interact with the SQL agent.
    *   `natural_language_query`: The question to be answered by querying the SQL database.
    *   `parsed_query_dict`: Optional dictionary from `LLMInterface.parse_query()`, used to retrieve relevant few-shot examples and table hints.
    *   **Responsibilities**:
        1.  If `parsed_query_dict` is provided, calls `get_relevant_sql_examples()` (from `sql_agent_utils.py`) to fetch relevant SQL examples and suggested table names.
        2.  Formats these examples and table hints into a prefix for the main query.
        3.  Constructs an `augmented_query` by prepending the few-shot examples and table hints to the `natural_language_query`.
        4.  Invokes `agent_executor.run(augmented_query)` to get the SQL query result.
    *   Returns: A tuple containing the SQL agent's textual result and a list of IDs/names of the few-shot examples used.

### `smart_factory_app/agents/sql_agent_utils.py`
This file contains utility functions to support the SQL agent, primarily for selecting relevant few-shot examples.

*   **`_extract_keywords_from_parsed_query(parsed_query: Dict[str, Any]) -> Set[str]`**:
    *   `parsed_query`: The output from `LLMInterface.parse_query()`.
    *   Extracts keywords from the `intent`, `machine_id`, and string values within `parameters` of the parsed query.
    *   Returns: A set of lowercased keywords.
*   **`get_relevant_sql_examples(parsed_query: Dict[str, Any], max_examples: int = 2) -> tuple[List[Dict[str, Any]], Set[str]]`**:
    *   `parsed_query`: The output from `LLMInterface.parse_query()`.
    *   `max_examples`: The maximum number of examples to return.
    *   Scores each example in `SQL_QUERY_EXAMPLES` based on matching `intent`, keyword overlap (with example keywords and description), and parameter overlap with the `parsed_query`.
    *   Gives a bonus to examples that match dynamic template parameters (like `table_name`) if these are present in the `parsed_query`'s parameters.
    *   Returns: A tuple containing a list of the most relevant example dictionaries and a set of unique table names mentioned in the `tables_involved` field of these selected examples.

### `smart_factory_app/agents/sql_query_examples.py`
This file defines a list named `SQL_QUERY_EXAMPLES`. Each item in the list is a dictionary representing a few-shot example for the SQL agent.

*   **`SQL_QUERY_EXAMPLES: List[Dict[str, Any]]`**: A list of dictionaries, where each dictionary has the following keys:
    *   `id` (str): A unique identifier for the example.
    *   `name` (str): A human-readable name for the example.
    *   `description` (str): A brief description of what the query does.
    *   `natural_language_equivalent` (str): A sample user question that corresponds to the `query_template`. This is used in the few-shot prompt.
    *   `query_template` (str): The SQL query template itself, possibly with placeholders like `:parameter_name` or `{dynamic_table_name}`.
    *   `parameters` (List[str]): A list of parameter names expected by the `query_template`, including dynamic placeholder names.
    *   `expected_intent` (str): The primary intent this query example is designed to address.
    *   `keywords` (List[str]): A list of keywords associated with this query, used for matching.
    *   `tables_involved` (List[str]): A list of database table names that are primarily used in the query.

### `smart_factory_app/agents/kg_agent.py`
This module handles all interactions with the Neo4j Knowledge Graph. It provides functionality to connect to the database and execute Cypher queries.

*   **`KGAgent` Class**:
    *   **`__init__(self, uri, user, password)`**: Initializes the Neo4j driver using connection details from `config.py` (or passed arguments). Verifies connectivity.
    *   **`close(self)`**: Closes the Neo4j driver connection.
    *   **`query(self, cypher_query: str, params: Optional[Dict[str, Any]] = None) -> Optional[List[Dict[str, Any]]]`**: Executes a given Cypher query.
        *   `cypher_query`: The Cypher query string to execute.
        *   `params`: An optional dictionary of parameters for the query.
        *   Uses a Neo4j session and transaction (`session.execute_read` or `session.execute_write` - current implementation uses `execute_read` via a helper).
        *   Returns: A list of records (as dictionaries) if successful, `None` otherwise. Includes error handling for common Neo4j exceptions.

### `smart_factory_app/agents/vector_agent.py`
This module is responsible for interacting with the Vector Database (ChromaDB). It handles text embedding generation, storage, and various search functionalities (semantic, keyword, hybrid).

*   **`VectorAgent` Class**:
    *   **`__init__(self, model_name, chroma_path, collection_name)`**: Initializes the Sentence Transformer model (for embeddings) and the ChromaDB client (either in-memory or persistent based on `chroma_path`). Gets or creates the specified collection.
    *   **`add_texts(self, texts: List[str], metadatas: Optional[List[dict]] = None, ids: Optional[List[str]] = None)`**: Adds texts to the ChromaDB collection.
        *   Generates embeddings for the input `texts` using the Sentence Transformer model.
        *   Assigns unique IDs if not provided.
        *   Stores the original `texts` (as `documents`), their `embeddings`, and associated `metadatas` in the collection.
    *   **`semantic_search(self, query_text: str, n_results: int = 5, where_filter: Optional[dict] = None) -> Optional[Dict[str, Any]]`**: Performs semantic similarity search.
        *   Embeds the `query_text`.
        *   Queries the collection for the top `n_results` most similar documents.
        *   Returns: A dictionary containing the IDs, documents, metadatas, and distances of the search results.
    *   **`keyword_search(self, keywords: List[str], n_results: int = 5, where_filter: Optional[dict] = None) -> Dict[str, Any]]`**: Performs keyword-based search using ChromaDB's `where_document` filter with `$contains` and `$or` operators.
        *   Returns: A dictionary similar to `semantic_search` results (distances are placeholders).
    *   **`hybrid_search(self, query_text: str, keywords: List[str], n_results: int = 5, semantic_weight: float = 0.6, keyword_weight: float = 0.4) -> Dict[str, Any]]`**: Combines results from semantic and keyword searches.
        *   Calculates a weighted `combined_score` for documents found by either search.
        *   Sorts results by this score.
        *   Returns: A dictionary containing the combined and re-ranked IDs, documents, metadatas, and their combined scores.

### `smart_factory_app/data_pipelines/etl_to_vector_db.py`
This script implements the ETL (Extract, Transform, Load) process to populate the Vector Database. It fetches data from specified tables in the PostgreSQL database, generates textual summaries for each record, and then stores these summaries (along with their embeddings) in ChromaDB using the `VectorAgent`.

*   **`fetch_data_from_sql(...)`**: Fetches data from a specified SQL table, with optional time window filtering.
*   **Summary Generation Functions** (e.g., `generate_equipment_summary`, `generate_equipment_alarm_summary`, etc.): A set of functions, each tailored to generate a descriptive text summary and associated metadata for a row from a specific SQL table (as defined in `config.TABLE_CONFIGS`).
*   **`SUMMARY_GENERATORS` (dict)**: A dispatcher dictionary that maps table names to their corresponding summary generation functions.
*   **`generate_text_summaries(df: pd.DataFrame, table_name: str)`**: Orchestrates summary generation for a given DataFrame by calling the appropriate specific function from `SUMMARY_GENERATORS`.
*   **`run_etl()`**: The main function that:
    1.  Initializes the SQL database engine and `VectorAgent`.
    2.  Iterates through `config.TABLE_CONFIGS`.
    3.  For each table, calls `fetch_data_from_sql`.
    4.  Calls `generate_text_summaries` to transform the fetched data.
    5.  Calls `vector_agent.add_texts` to load the summaries and their embeddings into ChromaDB.
*   The script also includes logic for using mock database data for testing (controlled by `config.ETL_USE_MOCK_DB`).

### `smart_factory_app/config/config.py`
This file centralizes all application configurations. It loads settings from environment variables with sensible defaults.

*   **Database Configurations**: `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, `DB_NAME`, `DATABASE_URI` (for PostgreSQL); `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` (for Neo4j).
*   **Vector DB (Chroma) Configuration**: `CHROMA_PERSIST_PATH`, `VECTOR_COLLECTION_NAME`.
*   **Sentence Transformer Model Configuration**: `SENTENCE_TRANSFORMER_MODEL`.
*   **Ollama LLM Configuration**: `OLLAMA_BASE_URL`, `OLLAMA_MODEL`.
*   **ETL Configuration**: `ETL_USE_MOCK_DB` (boolean flag).
*   **API Configuration**: `API_USE_MOCK_AGENTS` (boolean flag).
*   **Prompts Configuration**: `PROMPTS_DIR`, `PARSE_QUERY_PROMPT_FILE`, `GENERATE_RESPONSE_PROMPT_FILE` (absolute paths to prompt files).
*   **`TABLE_CONFIGS` (dict)**: A dictionary defining the schema and processing rules for tables to be included in the ETL pipeline (columns to fetch, time window column, etc.).

### `smart_factory_app/prompts/parse_query_prompt.txt`
This text file provides the template for the prompt sent to the LLM to parse a user's query.
*   **Purpose**: To instruct the LLM on how to analyze the user's natural language query and extract structured information: `intent`, `machine_id`, `timestamp`/`timestamp_range`, and other relevant `parameters`.
*   **Placeholders**:
    *   `{user_query}`: Replaced with the actual user's query.
    *   `{chat_history}`: Replaced with the recent conversation history to provide context for resolving ambiguities or follow-up questions.
*   **Content**: Includes a description of the task, examples of intents and parameters, example user queries and their corresponding desired JSON outputs, and instructions on how to handle missing information. It guides the LLM to understand factory-specific terminology.

### `smart_factory_app/prompts/generate_response_prompt.txt`
This text file provides the template for the prompt sent to the LLM to synthesize the final answer for the user.
*   **Purpose**: To instruct the LLM on how to generate a coherent, human-readable answer based on all the context gathered from various agents (SQL, KG, Vector DB) and the conversation history.
*   **Placeholders**:
    *   `{user_query}`: The original user query.
    *   `{chat_history}`: The recent conversation history.
    *   `{sql_data}`: Information retrieved from the SQL database by the SQL Agent.
    *   `{kg_context}`: Information retrieved from the Neo4j Knowledge Graph by the KG Agent.
    *   `{vector_context_str}`: Contextual documents/summaries retrieved from the Vector Database by the Vector Agent.
*   **Content**: Instructs the LLM to synthesize a comprehensive answer, use factory-specific terminology where appropriate, and base its response on all provided information sections.

## Future Enhancements

- Implement data population for the Neo4j Knowledge Graph.
- Develop a more sophisticated UI for interacting with the application.
- Add support for more diverse data sources and types.
- Enhance the ETL pipeline with more complex data transformations.
- Implement real-time data processing and alerting.
- Expand test coverage, including more integration tests.
- Add user authentication and authorization.
- Improve error handling and logging throughout the application.
- Conduct performance optimization for all components.
- Explore advanced LLM techniques for query understanding and response generation.
