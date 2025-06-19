# nl_to_sql_service/nl_to_sql_processor.py
"""Processes natural language queries to generate SQL queries.

This module defines the NLToSQLProcessor class, which orchestrates the
conversion of natural language questions into SQL queries. It leverages
configuration for LLMs, database schema handling (including RAG via
VectorStoreHandler), few-shot example management, and applies various
processing steps including prompt construction, LLM invocation, output parsing,
SQL syntax validation, semantic validation via EXPLAIN, heuristic-based
confidence scoring, an iterative correction loop, and final SQL execution
with pagination.
"""
import os
import json # Added for __main__ example
import sys # Added for __main__ example
from unittest.mock import patch # Added for __main__ example
import logging
import re
from typing import Dict, Any, Optional, List, Tuple, Set

from .config_manager import NLToSQLConfig
from .few_shot_manager import FewShotManager
from .db_schema_handler import DBSchemaHandler
from .vector_store_handler import VectorStoreHandler

# Attempt to import LangChain components
try:
    from langchain_community.chat_models import ChatOllama
    from langchain_core.messages import HumanMessage
    CHAT_OLLAMA_AVAILABLE = True
except ImportError:
    ChatOllama = None
    HumanMessage = None
    CHAT_OLLAMA_AVAILABLE = False

# Attempt to import sqlglot for syntax validation
try:
    import sqlglot
    from sqlglot.errors import ParseError as SQLGlotParseError
    SQLGLOT_AVAILABLE = True
except ImportError:
    sqlglot = None
    SQLGlotParseError = None # type: ignore
    SQLGLOT_AVAILABLE = False

try:
    from cachetools import LRUCache
    CACHETOOLS_AVAILABLE = True
except ImportError:
    LRUCache = None # type: ignore
    CACHETOOLS_AVAILABLE = False

# Ensure re, datetime, timedelta are available for date preprocessing
import re # re was already imported, ensuring it's noted for this task
from datetime import datetime, timedelta, date # Explicitly import date

# Default set of stop words for basic keyword extraction from natural language queries.
# These words are typically excluded as they don't carry significant semantic weight
# for identifying relevant table names or query intent in a simple keyword matching context.
DEFAULT_NL_TO_SQL_STOP_WORDS: Set[str] = set([
    'is', 'are', 'was', 'were', 'a', 'an', 'the', 'and', 'or', 'what', 'which', 'who',
    'when', 'where', 'how', 'show', 'me', 'list', 'find', 'get', 'of', 'for', 'in',
    'on', 'to', 'from', 'with', 'about', 'give', 'tell', 'can', 'could', 'may',
    'all', 'any', 'some', 'each', 'every', 'data', 'information', 'details',
    'summary', 'report', 'number', 'total', 'average', 'count', 'display',
    'what is', 'what are', 'show me', 'can you', 'could you', 'tell me'
])

def load_prompt_template(filepath: str, logger: logging.Logger) -> Optional[str]:
    """Loads a prompt template from a specified file path.

    Args:
        filepath: The path to the prompt template file.
        logger: The logger instance to use for logging messages.

    Returns:
        The content of the prompt template file as a string, or None if loading fails.
    """
    # Check if the path is absolute, log if not, as resolution might be context-dependent.
    if not os.path.isabs(filepath):
        logger.debug(f"Prompt template filepath '{filepath}' is not absolute. Resolution depends on runtime context.")
    if not os.path.exists(filepath):
        logger.error(f"Prompt template file not found: {filepath}")
        return None
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        logger.error(f"Error loading prompt template file {filepath}: {e}", exc_info=True)
        return None

class NLToSQLProcessor:
    """Orchestrates the conversion of natural language to SQL queries using RAG.

    This class integrates various components like configuration management,
    few-shot example selection, database schema retrieval (static and RAG-based),
    LLM interaction, SQL validation (syntax and semantic), and an iterative
    correction loop to refine generated SQL queries. It aims to provide a robust
    NL-to-SQL conversion pipeline.

    Attributes:
        config: An NLToSQLConfig instance containing all configurations.
        logger: A logging.Logger instance for logging messages.
        few_shot_manager: An instance of FewShotManager for handling few-shot examples.
        vector_store_handler: An instance of VectorStoreHandler for RAG-based schema retrieval.
        db_schema_handler: An optional DBSchemaHandler for dynamic schema operations and SQL execution.
        llm: An optional ChatOllama instance for interacting with the language model.
        base_prompt_template: A string template for constructing LLM prompts.
    """

    def __init__(self, config: NLToSQLConfig,
                 vector_store_handler: Optional[VectorStoreHandler] = None,
                 db_schema_handler: Optional[DBSchemaHandler] = None):
        """Initializes the NLToSQLProcessor.

        Sets up logging, initializes managers for few-shot examples, vector store (for RAG),
        and database schema. It also initializes the LLM based on the provided configuration.

        Args:
            config: The NLToSQLConfig object containing all necessary configurations.
            vector_store_handler: An optional pre-initialized VectorStoreHandler. If None,
                it will be initialized based on the config.
            db_schema_handler: An optional pre-initialized DBSchemaHandler. If None,
                and dynamic schema handling is enabled with DB details in config,
                it will be initialized.
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        self._configure_logger() # Configure logger based on config settings.

        # Log initial configuration, excluding sensitive details like API keys or passwords.
        config_dump = config.model_dump_json(indent=2, exclude={'llm': {'api_key'}, 'db_schema_handler': {'password'}})
        self._log(f"Initializing NLToSQLProcessor with config: {config_dump}", "info")

        # Initialize FewShotManager for loading and selecting few-shot examples.
        self.few_shot_manager = FewShotManager(
            examples_filepath=config.few_shot_examples_path,
            embedding_model_name=config.few_shot_embedding_model,
            logger=self.logger
        )

        # Initialize VectorStoreHandler for RAG if not provided.
        if vector_store_handler:
            self.vector_store_handler = vector_store_handler
        else:
            self.vector_store_handler = VectorStoreHandler(config=config, logger=self.logger)
            self._log("VectorStoreHandler initialized by NLToSQLProcessor based on config.", "info")

        # Initialize DBSchemaHandler if not provided and dynamic schema handling is enabled with valid config.
        self.db_schema_handler: Optional[DBSchemaHandler] = db_schema_handler
        if not self.db_schema_handler and config.use_dynamic_schema_handling and config.db_schema_handler:
             db_handler_config_dict = config.db_schema_handler.model_dump()
             # Ensure essential DB connection details are present before initializing.
             if db_handler_config_dict.get("host") or db_handler_config_dict.get("connection_string"):
                 self.db_schema_handler = DBSchemaHandler(
                     db_config=db_handler_config_dict, # Pass the dict form of DBSchemaHandlerConfig
                     logger=self.logger,
                     cache_ttl_seconds=config.db_schema_handler.schema_cache_ttl_seconds
                 )
                 self._log("DBSchemaHandler initialized by NLToSQLProcessor based on config.", "info")

        # Initialize the Language Model (LLM) using ChatOllama if available.
        self.llm: Optional[ChatOllama] = None
        if CHAT_OLLAMA_AVAILABLE and ChatOllama is not None:
            try:
                self.llm = ChatOllama(
                    model=config.llm.model_name,
                    base_url=config.llm.base_url,
                    temperature=config.llm.temperature
                )
                self._log(f"ChatOllama LLM initialized: model='{config.llm.model_name}', temperature={config.llm.temperature}", "info")
            except Exception as e:
                self._log(f"Error initializing ChatOllama: {e}. LLM will be unavailable.", "error", exc_info=True)
        else:
            self._log("ChatOllama library not available or not imported correctly. LLM couldn't be initialized.", "error")

        # Load the base prompt template from the specified file path.
        self.base_prompt_template: Optional[str] = load_prompt_template(config.base_prompt_template_path, self.logger)
        if not self.base_prompt_template:
            self._log(f"CRITICAL: Base prompt template failed to load from path: {config.base_prompt_template_path}. Prompt construction will fail.", "error")

        # Log availability of sqlglot for syntax validation.
        if not SQLGLOT_AVAILABLE:
            self._log("sqlglot library not found. SQL syntax validation will be skipped.", "warning")
        else:
            self._log("sqlglot library available for SQL syntax validation.", "info")

        # Log status of DBSchemaHandler for semantic validation and execution.
        if not (self.db_schema_handler and self.config.use_dynamic_schema_handling):
            self._log("DBSchemaHandler not available or dynamic schema handling disabled. SQL semantic validation and data execution will be skipped or limited.", "warning")

        # Initialize query cache
        self.query_cache: Optional[LRUCache] = None
        if CACHETOOLS_AVAILABLE and config.query_cache_size > 0 and LRUCache is not None:
            self.query_cache = LRUCache(maxsize=config.query_cache_size)
            self._log(f"Initialized query cache with maxsize: {config.query_cache_size}", "info")
        elif config.query_cache_size > 0 and not CACHETOOLS_AVAILABLE:
            self._log("Query caching enabled in config, but 'cachetools' library not found. Caching will be disabled.", "warning")
        else:
            self._log("Query caching is disabled (cache size <= 0).", "info")

    def _preprocess_nl_query_for_dates(self, nl_query: str) -> str:
        """Identifies and replaces common relative date phrases with explicit date conditions.

        This helps make date-related queries more explicit for the LLM, potentially
        improving SQL generation accuracy for PostgreSQL/TimescaleDB.

        Args:
            nl_query: The natural language query string.

        Returns:
            The modified natural language query string with date phrases replaced.
        """
        today = date.today()
        processed_query = nl_query

        # Define patterns and their replacement logic
        # Order matters: more specific patterns should come before general ones
        # e.g., "last N days" before "last day" (if that were a pattern)
        patterns = [
            # "last N days" or "past N days"
            (r"(?:last|past)\s+(\d+)\s+days",
             lambda m: f"BETWEEN '{ (today - timedelta(days=int(m.group(1)))).strftime('%Y-%m-%d') }' AND '{ today.strftime('%Y-%m-%d') }'"),
            # "next N days"
            (r"next\s+(\d+)\s+days",
             lambda m: f"BETWEEN '{ today.strftime('%Y-%m-%d') }' AND '{ (today + timedelta(days=int(m.group(1)))).strftime('%Y-%m-%d') }'"),
            # "today"
            (r"\b(today)\b",
             lambda m: f"'{today.strftime('%Y-%m-%d')}'"),
            # "yesterday"
            (r"\b(yesterday)\b",
             lambda m: f"'{ (today - timedelta(days=1)).strftime('%Y-%m-%d') }'"),
            # "tomorrow"
            (r"\b(tomorrow)\b",
             lambda m: f"'{ (today + timedelta(days=1)).strftime('%Y-%m-%d') }'"),
            # "this week" (assuming Monday as start of week)
            (r"\b(this\s+week)\b",
             lambda m: f"BETWEEN '{(today - timedelta(days=today.weekday())).strftime('%Y-%m-%d')}' AND '{((today - timedelta(days=today.weekday())) + timedelta(days=6)).strftime('%Y-%m-%d')}'"),
            # "last week"
            (r"\b(last\s+week)\b",
             lambda m: f"BETWEEN '{(today - timedelta(days=today.weekday() + 7)).strftime('%Y-%m-%d')}' AND '{((today - timedelta(days=today.weekday() + 7)) + timedelta(days=6)).strftime('%Y-%m-%d')}'"),
            # "next week"
            (r"\b(next\s+week)\b",
             lambda m: f"BETWEEN '{(today + timedelta(days=(7-today.weekday()))).strftime('%Y-%m-%d')}' AND '{((today + timedelta(days=(7-today.weekday()))) + timedelta(days=6)).strftime('%Y-%m-%d')}'"),
            # "this month"
            (r"\b(this\s+month)\b",
             lambda m: f"BETWEEN '{today.replace(day=1).strftime('%Y-%m-%d')}' AND '{((today.replace(day=1) + timedelta(days=31)).replace(day=1) - timedelta(days=1)).strftime('%Y-%m-%d')}'"), # Approximation for end of month
            # "last month"
            (r"\b(last\s+month)\b",
             lambda m: f"BETWEEN '{(today.replace(day=1) - timedelta(days=1)).replace(day=1).strftime('%Y-%m-%d')}' AND '{(today.replace(day=1) - timedelta(days=1)).strftime('%Y-%m-%d')}'"),
        ]

        for pattern, replacement_func in patterns:
            # Using re.sub with a function allows for dynamic replacement based on match groups
            new_query = re.sub(pattern, replacement_func, processed_query, flags=re.IGNORECASE)
            if new_query != processed_query:
                self._log(f"Date preprocessing: Replaced pattern '{pattern}' in query. Old: '{processed_query}', New: '{new_query}'", "debug")
                processed_query = new_query

        return processed_query

    def _configure_logger(self) -> None:
        """Configures the logger for the class instance.

        Sets the logging level based on the configuration and adds a stream handler
        if no handlers are already configured for the logger.
        """
        log_level_str = self.config.log_level.upper()
        numeric_level = getattr(logging, log_level_str, logging.INFO) # Default to INFO if level is invalid

        # Ensure a handler is configured to see log messages.
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
        self.logger.setLevel(numeric_level)

            handler = logging.StreamHandler() # Default to console output
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
        self.logger.setLevel(numeric_level)

    def _log(self, message: str, level: str = "info", exc_info: bool = False) -> None:
        """Helper method for logging messages.

        Args:
            message: The message string to log.
            level: The logging level (e.g., "debug", "info", "warning", "error", "critical").
                   Defaults to "info".
            exc_info: If True, exception information is added to the logging message.
                      Defaults to False.
        """
        if level.lower() == "debug": self.logger.debug(message)
        elif level.lower() == "info": self.logger.info(message)
        elif level.lower() == "warning": self.logger.warning(message)
        elif level.lower() == "error": self.logger.error(message, exc_info=exc_info)
        elif level.lower() == "critical": self.logger.critical(message, exc_info=exc_info)

    def _extract_keywords(self, text: str) -> List[str]:
        """Extracts potential keywords from a text string.

        This is a basic keyword extraction method used for simple matching or as input
        to more advanced selection strategies (e.g., for few-shot examples or RAG context).
        It converts text to lowercase, removes punctuation, splits into words,
        and filters out common stop words and short words.

        Args:
            text: The input string from which to extract keywords.

        Returns:
            A list of unique keywords extracted from the text.
        """
        if not text: return []
        text_lower = text.lower()
        # Remove punctuation, keeping alphanumeric characters, underscores, and spaces.
        text_cleaned = re.sub(r'[^\w\s_]', '', text_lower)
        words = text_cleaned.split()
        # Filter out stop words and words shorter than 2 characters.
        keywords = [
            word for word in words
            if word not in DEFAULT_NL_TO_SQL_STOP_WORDS and len(word) > 1
        ]
        return list(set(keywords)) # Return unique keywords

    def _retrieve_schema_context_for_query(self, natural_language_query: str) -> Tuple[str, List[str]]:
        """Retrieves relevant database schema context for a natural language query using RAG.

        Uses the `VectorStoreHandler` to find schema chunks (e.g., table DDLs, column descriptions)
        that are semantically similar to the input query.

        Args:
            natural_language_query: The user's natural language question.

        Returns:
            A tuple containing:
                - A string with the combined text of relevant schema chunks.
                - A list of table names identified from the retrieved schema chunks.
            Returns a default error message and empty list if retrieval fails or is not possible.
        """
        self._log(f"Retrieving RAG schema context for query: '{natural_language_query[:70]}...'", "info")
        default_error_return = ("-- Schema context unavailable: Vector store or embedding model not initialized --", [])

        if not self.vector_store_handler or not self.vector_store_handler.embedding_model:
            self._log("VectorStoreHandler or its embedding model not initialized. Cannot retrieve RAG schema context.", "error")
            return default_error_return
        try:
            # Retrieve relevant schema chunks from the vector store.
            retrieved_items: List[Dict[str, Any]] = self.vector_store_handler.retrieve_relevant_schema_chunks(
                query_text=natural_language_query,
                n_results=self.config.num_schema_chunks_for_prompt
            )
        except Exception as e:
            self._log(f"Error during RAG schema chunk retrieval: {e}", "error", exc_info=True)
            return "-- Error retrieving schema context from vector store --", []

        if not retrieved_items:
            self._log("No schema chunks retrieved from vector store for this query.", "debug")
            return "-- No specific schema context found for this query in the vector store --", []

        # Extract text content and table names from the retrieved items.
        schema_context_parts: List[str] = [
            item["text_content"] for item in retrieved_items
            if isinstance(item, dict) and "text_content" in item
        ]
        retrieved_table_names: List[str] = list(set(
            str(item["metadata"]["table_name"]) for item in retrieved_items
            if isinstance(item.get("metadata"), dict) and item["metadata"].get("table_name")
        ))

        # Combine schema parts into a single string for the prompt.
        schema_context_str = "\n\n--- Schema Chunk ---\n".join(schema_context_parts)
        self._log(f"Retrieved {len(schema_context_parts)} schema chunks for RAG. Tables: {retrieved_table_names}. Context snippet: {schema_context_str[:100]}...", "debug")
        return schema_context_str, retrieved_table_names

    def _get_relevant_few_shots(self, natural_language_query: str,
                                custom_few_shot_examples: Optional[List[Dict[str, Any]]]
                               ) -> List[Dict[str, Any]]:
        """Selects relevant few-shot examples for the given query.

        If `custom_few_shot_examples` are provided, they are used directly.
        Otherwise, uses the `FewShotManager` to select examples based on the configured strategy.

        Args:
            natural_language_query: The user's natural language question.
            custom_few_shot_examples: Optional list of custom few-shot examples to use.

        Returns:
            A list of selected few-shot examples (dictionaries).
        """
        if custom_few_shot_examples is not None:
            self._log(f"Using {len(custom_few_shot_examples)} provided custom few-shot examples.", "debug")
            return custom_few_shot_examples

        if self.few_shot_manager:
            self._log(f"Retrieving few-shot examples using strategy: {self.config.few_shot_selection_strategy}", "debug")
            return self.few_shot_manager.get_relevant_examples(
                natural_language_query,
                self.config.num_few_shot_examples_to_select,
                self.config.few_shot_selection_strategy
            )
        self._log("No custom few-shot examples provided and FewShotManager not available.", "warning")
        return []

    def _construct_llm_prompt(self, natural_language_query: str,
                              schema_context: str,
                              relevant_few_shots: List[Dict[str, Any]],
                              is_correction: bool = False,
                              previous_sql: Optional[str] = None,
                              previous_error: Optional[str] = None
                             ) -> Optional[str]:
        """Constructs the full prompt to be sent to the LLM.

        Formats the prompt using the base template, incorporating the schema context,
        few-shot examples, and user query. If it's a correction attempt, a specialized
        prompt is constructed that includes the erroneous SQL and the error message.

        Args:
            natural_language_query: The user's natural language question.
            schema_context: The database schema context (potentially from RAG).
            relevant_few_shots: A list of few-shot examples to include in the prompt.
            is_correction: Boolean flag indicating if this is a correction attempt.
            previous_sql: The previously generated SQL query (if `is_correction` is True).
            previous_error: The error message from the previous attempt (if `is_correction` is True).

        Returns:
            The fully constructed prompt string, or None if the base template is missing.
        """
        if not self.base_prompt_template:
            self._log("Base prompt template is not loaded. Cannot construct LLM prompt.", "error")
            return None

        formatted_examples = self.few_shot_manager.format_examples_for_prompt(relevant_few_shots)
        sql_dialect = (self.config.db_schema_handler.db_type
                       if self.config.db_schema_handler and self.config.db_schema_handler.db_type
                       else "SQL") # Default to "SQL" if not specified

        current_prompt_str: str
        prompt_data: Dict[str, str] = {}

        if is_correction:
            # Construct a specific prompt for correction attempts.
            self._log(f"Constructing a corrective prompt. Previous SQL: '{previous_sql}', Error: '{previous_error}'", "debug")
            # This prompt guides the LLM to fix the provided erroneous SQL based on the error.
            current_prompt_str = (
                f"You are an expert Natural Language to SQL converter. Your task is to correct an erroneous SQL query.\n"
                f"The user's original question was: '{natural_language_query}'\n"
                f"The database schema context provided was:\n{schema_context}\n"
                f"The few-shot examples provided were:\n{formatted_examples or '# No few-shot examples provided.'}\n"
                f"The previously generated SQL query was:\n```sql\n{previous_sql}\n```\n"
                f"This query resulted in the following error:\n{previous_error}\n\n"
                f"Please provide a corrected SQL query for the {sql_dialect} database that addresses the error and accurately answers the user's original question. "
                f"Return ONLY the corrected SQL query, with no other text or explanation."
            )
            # No further formatting needed for the correction prompt as it's self-contained.
        else:
            # Use the base prompt template for initial SQL generation.
            current_prompt_str = self.base_prompt_template
            prompt_data = {
                "schema": schema_context,
                "user_question": natural_language_query,
                "examples": formatted_examples or "# No few-shot examples provided.", # Placeholder if no examples
                "dialect": sql_dialect
            }

        try:
            # Populate the prompt template with data if it's not a correction prompt.
            final_prompt = current_prompt_str.format(**prompt_data) if not is_correction and prompt_data else current_prompt_str
            self._log(f"Final LLM prompt type: {'Corrective' if is_correction else 'Initial'}. Snippet: {final_prompt[:200]}...", "debug")
            return final_prompt
        except KeyError as e:
            self._log(f"Error formatting prompt. Missing key: {e}. Prompt template might be malformed or data incomplete.", "error", exc_info=True)
            return None

    def _invoke_llm(self, full_prompt: str) -> Optional[str]:
        """Invokes the configured LLM with the given prompt.

        Args:
            full_prompt: The complete prompt string to send to the LLM.

        Returns:
            The raw string response from the LLM, or None if invocation fails or LLM is not available.
        """
        if not self.llm:
            self._log("LLM not initialized. Cannot invoke.", "error")
            return None
        # Check for LangChain components if ChatOllama is supposed to be used.
        if not HumanMessage and CHAT_OLLAMA_AVAILABLE and isinstance(self.llm, ChatOllama):
            self._log("LangChain HumanMessage not available, but ChatOllama instance exists. Invocation might fail.", "warning")
            # Depending on exact LangChain version, this might still work or require HumanMessage.
            # Proceeding with caution.

        self._log(f"Invoking LLM. Prompt snippet: {full_prompt[:150]}...", "info")
        try:
            # Use LangChain's specific invocation style if components are available and LLM is ChatOllama.
            if CHAT_OLLAMA_AVAILABLE and HumanMessage and isinstance(self.llm, ChatOllama):
                 message = HumanMessage(content=full_prompt) # Wrap prompt in HumanMessage
                 response = self.llm.invoke([message]) # Invoke with a list of messages
                 content = str(response.content) # Extract content from AIMessage response
            else:
                # Fallback or direct invocation if not using the specific LangChain message structure
                # This path might be taken if self.llm is a different type or LangChain components are missing.
                content = str(self.llm.invoke(full_prompt)) # Standard invoke for other LLM types
            self._log(f"LLM raw response snippet: {content[:150]}...", "debug")
            return content
        except Exception as e:
            self._log(f"Error invoking LLM: {e}", "error", exc_info=True)
            return None

    def _validate_sql_syntax(self, sql_query: str) -> Tuple[bool, Optional[str]]:
        """Validates the syntax of the generated SQL query using sqlglot.

        Args:
            sql_query: The SQL query string to validate.

        Returns:
            A tuple: (is_valid: bool, error_message: Optional[str]).
            `is_valid` is True if syntax is correct or validation is skipped,
            False otherwise. `error_message` contains details if invalid.
        """
        if not SQLGLOT_AVAILABLE or sqlglot is None or SQLGlotParseError is None:
            self._log("sqlglot not available, skipping SQL syntax validation.", "warning")
            return True, "Syntax validation skipped: sqlglot library not available."
        if not sql_query or not sql_query.strip():
            return False, "No SQL query to validate."

        try:
            # Determine SQL dialect from config, if available. sqlglot uses this for parsing.
            dialect = self.config.db_schema_handler.db_type if self.config.db_schema_handler and self.config.db_schema_handler.db_type else None
            sqlglot.parse_one(sql_query, read=dialect) # `read` is the dialect hint
            self._log(f"SQL syntax validation passed for query: {sql_query[:100]}...", "debug")
            return True, None
        except SQLGlotParseError as e:
            self._log(f"SQLGlot ParseError for query '{sql_query[:100]}...': {e}", "warning")
            return False, f"SQLGlot ParseError: {str(e)}"
        except Exception as e: # Catch any other unexpected errors during parsing.
            self._log(f"Unexpected error during SQL syntax validation for query '{sql_query[:100]}...': {e}", "error", exc_info=True)
            return False, f"Unexpected error during SQL syntax validation: {str(e)}"

    def _validate_sql_semantically(self, sql_query: str) -> Tuple[bool, Optional[str]]:
        """Validates the SQL query semantically by attempting to EXPLAIN it against the database.

        Requires `DBSchemaHandler` to be configured and `use_dynamic_schema_handling` enabled.

        Args:
            sql_query: The SQL query string to validate.

        Returns:
            A tuple: (is_valid: bool, error_message: Optional[str]).
            `is_valid` is True if EXPLAIN succeeds or validation is skipped.
            False otherwise. `error_message` contains details if invalid.
        """
        if not self.config.use_dynamic_schema_handling or not self.db_schema_handler:
            self._log("Semantic validation skipped: DBSchemaHandler not configured or dynamic handling disabled.", "info")
            return True, "Semantic validation skipped: DBSchemaHandler not configured or disabled."
        if not sql_query or not sql_query.strip():
            return False, "No SQL query for semantic validation."

        # Construct an EXPLAIN query. This doesn't execute the query but asks the DB to plan it.
        validation_query = f"EXPLAIN {sql_query}"
        self._log(f"Attempting semantic validation with query: {validation_query[:150]}...", "debug")
        try:
            # Use the DBSchemaHandler to execute the EXPLAIN query.
            # The `_execute_query` method in DBSchemaHandler should handle connection and execution.
            explain_results = self.db_schema_handler._execute_query(validation_query) # type: ignore
            if explain_results is not None: # Successful EXPLAIN typically returns rows (plan) or empty list.
                self._log(f"SQL semantic validation (EXPLAIN) passed for query: {sql_query[:100]}...", "debug")
                return True, None
            else:
                # This case might occur if _execute_query returns None on DB error.
                self._log(f"Semantic validation failed for query '{sql_query[:100]}...': EXPLAIN execution error (check DB logs).", "warning")
                return False, "Semantic validation failed: EXPLAIN execution error (check logs for DB error)."
        except Exception as e: # Catch unexpected errors from DB interaction.
            self._log(f"Unexpected error during semantic validation for query '{sql_query[:100]}...': {e}", "error", exc_info=True)
            return False, f"Unexpected error during semantic validation: {str(e)}"

    def _process_llm_output(self, llm_raw_response: Optional[str],
                            tables_from_rag_context: Optional[List[str]] = None
                           ) -> Dict[str, Any]:
        """Processes raw LLM output to extract SQL, assess initial confidence, and identify errors.

        This method performs initial parsing of the LLM's response. It looks for SQL code blocks,
        handles cases where the LLM indicates it cannot convert the query, and performs basic
        cleaning and security checks (like disallowed keywords).

        Confidence scores set here are preliminary and are adjusted by subsequent validation
        steps (syntax, semantic) in the main `convert_nl_to_sql` flow.

        Args:
            llm_raw_response: The raw string response from the LLM.
            tables_from_rag_context: Optional list of table names identified from RAG context,
                                     used as a starting point for `tables_used`.

        Returns:
            A dictionary containing:
                - "sql_query": The extracted SQL query (str) or None.
                - "confidence_score": An initial estimate of confidence (float) or None.
                - "llm_reasoning": Placeholder for future use (None).
                - "tables_used": List of tables potentially used (List[str]).
                - "error_message": Description of any error encountered (str) or None.
        """
        sql_query: Optional[str] = None
        confidence_score: Optional[float] = None # Initialized to None, set based on outcomes
        error_message: Optional[str] = None
        # Start with tables identified from RAG, can be refined later if LLM provides table info.
        tables_used_output: List[str] = tables_from_rag_context if tables_from_rag_context else []

        if not llm_raw_response or not llm_raw_response.strip():
            error_message = "LLM returned no response or an empty response."
            confidence_score = 0.0 # No response means zero confidence.
            self._log(error_message, "warning")
        elif llm_raw_response.strip() == self.config.error_string_for_no_conversion:
            # Handle cases where the LLM explicitly states it cannot convert the query.
            error_message = self.config.error_string_for_no_conversion
            confidence_score = 0.0 # LLM explicitly failed, zero confidence.
            self._log(f"LLM indicated no conversion possible: '{error_message}'", "info")
        else:
            # Attempt to extract SQL query, typically enclosed in markdown backticks.
            match = re.search(r"```(?:sql\s*)?(.*?)\s*```", llm_raw_response, re.DOTALL | re.IGNORECASE)
            if match:
                sql_query = match.group(1).strip()
                self._log(f"Extracted SQL from markdown backticks: {sql_query[:100]}...", "debug")
            else:
                # Fallback: If no backticks, check if the response starts with common SQL keywords
                # after stripping potential conversational prefixes.
                temp_sql_query = llm_raw_response.strip()
                explanation_phrases = [
                    "here is the sql query:", "here's the sql query:", "sure, here is the query:",
                    "the sql query is:", "sql query:", "query:"
                ]
                temp_query_lower = temp_sql_query.lower()
                for phrase in explanation_phrases:
                    if temp_query_lower.startswith(phrase):
                        temp_sql_query = temp_sql_query[len(phrase):].strip()
                        break # Remove the first matching phrase

                # Check if the remaining string looks like an SQL query.
                if temp_sql_query.lstrip().upper().startswith(("SELECT", "WITH", "INSERT", "UPDATE", "DELETE")):
                    sql_query = temp_sql_query
                    self._log(f"No backticks found. Using full/trimmed response as SQL: {sql_query[:100]}...", "debug")
                else:
                    error_message = "Failed to extract SQL from LLM response (no backticks or common SQL start keywords found)."
                    confidence_score = 0.05 # Very low confidence if SQL extraction itself is problematic.
                    self._log(error_message, "warning")

            if sql_query:
                # Clean the extracted SQL query.
                if self.config.remove_trailing_semicolon and sql_query.endswith(';'):
                    sql_query = sql_query[:-1].strip()

                # Perform security check for disallowed SQL keywords.
                # If a disallowed keyword is found, the query is invalidated.
                if self.config.disallowed_sql_keywords:
                    query_upper = sql_query.upper()
                    for keyword in self.config.disallowed_sql_keywords:
                        # Use regex to match whole words to avoid partial matches (e.g., 'UPDATE' in 'MY_UPDATED_TABLE').
                        if re.search(r"\b" + re.escape(keyword.upper()) + r"\b", query_upper):
                            error_message = f"Generated SQL contains disallowed keyword: {keyword}."
                            # Specific confidence for disallowed keyword error will be set in the main loop (e.g., 0.1).
                            sql_query = None # Invalidate the query.
                            self._log(error_message, "warning")
                            break # Stop checking keywords if one is found.

                # If SQL is valid so far and no other critical error has set confidence:
                if sql_query and confidence_score is None:
                    # This is a successfully extracted SQL query, before syntax/semantic validation.
                    # Set a baseline confidence. This will be updated by subsequent validation steps.
                    confidence_score = 0.7 # Default initial confidence for successfully extracted SQL.

            # If SQL query is None by this point (due to bad extraction or security fail)
            # and confidence hasn't been set by a more specific error:
            elif not sql_query and confidence_score is None:
                error_message = error_message or "SQL extraction failed or query invalidated by security checks."
                confidence_score = 0.05 # Fallback low confidence.
                self._log(error_message, "warning")

        # Construct the output dictionary.
        output_dict: Dict[str, Any] = {
            "sql_query": sql_query,
            "confidence_score": confidence_score,
            "llm_reasoning": None,  # Placeholder for potential future parsing of LLM's thought process.
            "tables_used": tables_used_output, # TODO: Could be improved by parsing SQL to find tables if RAG fails
            "error_message": error_message
        }
        self._log(f"Initial LLM output processing -- SQL: {sql_query[:100] if sql_query else 'None'}, Initial Confidence: {confidence_score}, Error: {error_message}", "info")
        return output_dict

    def _execute_final_sql(self, sql_query: str, page_number: int = 1, page_size: Optional[int] = None) -> Dict[str, Any]:
        """Executes the validated SELECT SQL query with pagination.

        Requires `DBSchemaHandler` and `use_dynamic_schema_handling`.
        Only executes SELECT queries.

        Args:
            sql_query: The validated SQL SELECT query to execute.
            page_number: The page number for pagination (1-indexed).
            page_size: The number of records per page. Uses config default if None.

        Returns:
            A dictionary containing:
                - "data": The query results (List[Dict]) or None on error.
                - "error": Error message if execution failed, else None.
                - "row_count": Number of rows returned in the current page.
                - "page_number": The current page number.
                - "page_size": The page size used.
        """
        default_error_payload = {
            "data": None, "error": "An error occurred during SQL execution.",
            "row_count": 0, "page_number": page_number, "page_size": 0
        }

        if not self.config.use_dynamic_schema_handling or not self.db_schema_handler:
            default_error_payload["error"] = "Database connection not available for query execution."
            self._log(default_error_payload["error"], "warning")
            return default_error_payload

        if not sql_query or not sql_query.strip().upper().startswith("SELECT"):
            default_error_payload["error"] = "Execution Error: Only SELECT queries can be executed."
            self._log(default_error_payload["error"], "warning")
            return default_error_payload

        # Determine page size, applying configured defaults and maximums.
        page_size_to_use = page_size if page_size is not None and page_size > 0 else self.config.default_page_size
        if page_size_to_use > self.config.max_page_size:
            page_size_to_use = self.config.max_page_size
        if page_size_to_use <= 0: # Ensure page size is positive.
            page_size_to_use = self.config.default_page_size

        if page_number < 1: page_number = 1 # Ensure page number is positive.
        offset = (page_number - 1) * page_size_to_use

        # Append LIMIT and OFFSET clauses for pagination.
        # Note: This assumes the SQL dialect supports LIMIT/OFFSET (common in PostgreSQL, MySQL, SQLite).
        paginated_sql = f"{sql_query} LIMIT {page_size_to_use} OFFSET {offset}"
        self._log(f"Executing paginated SQL: {paginated_sql[:200]}...", "info")

        try:
            # Execute using DBSchemaHandler.
            results = self.db_schema_handler._execute_query(paginated_sql, fetch_results=True) # type: ignore
            if results is None: # _execute_query might return None on DB error.
                default_error_payload["error"] = "Database execution error (check logs for specific DB message)."
                self._log(default_error_payload["error"], "error")
                return default_error_payload

            self._log(f"SQL execution successful. Returned {len(results)} rows for page {page_number}.", "info")
            return {
                "data": results, "row_count": len(results),
                "page_number": page_number, "page_size": page_size_to_use,
                "error": None
            }
        except Exception as e: # Catch any other unexpected errors.
            default_error_payload["error"] = f"Unexpected execution error: {str(e)}"
            self._log(default_error_payload["error"], "error", exc_info=True)
            return default_error_payload

    def convert_nl_to_sql(self, natural_language_query: str,
                          custom_schema_info: Optional[str] = None,
                          custom_few_shot_examples: Optional[List[Dict[str, Any]]] = None,
                          page_number: int = 1, page_size: Optional[int] = None
                         ) -> Dict[str, Any]:
        """Converts a natural language query to SQL, with validation, correction, and execution.

        This is the main public method of the class. It orchestrates the entire NL-to-SQL
        pipeline:
        1. Retrieves schema context (RAG-based or custom).
        2. Selects few-shot examples.
        3. Enters a correction loop:
            a. Constructs an LLM prompt (initial or for correction).
            b. Invokes the LLM.
            c. Processes the LLM's output (extracts SQL, initial confidence).
            d. Validates SQL syntax.
            e. Validates SQL semantics (using EXPLAIN).
            f. If validations pass, exits loop. Otherwise, attempts correction if attempts remain.
        4. Adjusts final confidence score based on validation outcomes and attempts.
        5. If a valid SELECT SQL is generated, executes it with pagination.
        6. Returns a comprehensive dictionary with results, SQL, confidence, errors, etc.

        Args:
            natural_language_query: The user's question in natural language.
            custom_schema_info: Optional string containing custom schema information to use
                                instead of RAG-based retrieval.
            custom_few_shot_examples: Optional list of custom few-shot examples.
            page_number: For pagination of results if the query is a SELECT.
            page_size: Number of results per page.

        Returns:
            A dictionary containing the generated SQL query, confidence score,
            any error messages, the prompt used, tables identified, and query results
            (if applicable and successful).
            Structure includes:
            - "sql_query": (Optional[str]) The generated SQL.
            - "confidence_score": (Optional[float]) Confidence in the SQL (0.0 to 1.0).
            - "error_message": (Optional[str]) Error message if generation/validation failed.
            - "execution_error_message": (Optional[str]) Error from SQL execution phase.
            - "llm_reasoning": (Optional[str]) Placeholder for LLM's reasoning (currently None).
            - "tables_used": (List[str]) List of tables potentially involved.
            - "prompt_used": (Optional[str]) The actual prompt sent to the LLM.
            - "query_results": (Dict) Results of SQL execution, including:
                - "data": (Optional[List[Dict]]) Query data.
                - "error": (Optional[str]) Execution error.
                - "row_count": (int) Rows in current page.
                - "page_number": (int) Current page.
                - "page_size": (int) Page size used.
        """
        self._log(f"Starting NL-to-SQL conversion for query: '{natural_language_query[:100]}...'", "info")

        # Step 1: Retrieve Schema Context (and prepare parts of the cache key)
        original_schema_context: str
        retrieved_tables_for_context: List[str]
        if custom_schema_info:
            self._log("Using provided custom_schema_info. RAG-based schema retrieval will be skipped.", "info")
            original_schema_context = custom_schema_info
            # Cannot reliably infer table names from an opaque custom schema string here.
            # This could be improved if custom_schema_info had a defined structure or was parsed.
            retrieved_tables_for_context = []
        else:
            original_schema_context, retrieved_tables_for_context = self._retrieve_schema_context_for_query(natural_language_query)

        # Step 2: Get Relevant Few-Shot Examples (and prepare parts of the cache key)
        original_few_shots = self._get_relevant_few_shots(natural_language_query, custom_few_shot_examples)

        # Construct Cache Key
        cache_key_parts = [natural_language_query]
        if original_schema_context:
            cache_key_parts.append(str(hash(original_schema_context))) # Hash to keep key manageable
        if original_few_shots:
            # Using 'query' field of examples for key, assuming it's representative and stable. Hash for safety.
            example_representation = sorted([str(hash(ex.get('query', ''))) for ex in original_few_shots])
            cache_key_parts.extend(example_representation)
        cache_key_parts.append(str(page_number))
        cache_key_parts.append(str(page_size))
        cache_key = tuple(cache_key_parts)

        # Cache Check
        if self.query_cache is not None:
            cached_result = self.query_cache.get(cache_key)
            if cached_result:
                self._log(f"Cache hit for query: '{natural_language_query[:50]}...'. Returning cached result.", "info")
                # Optionally, add a flag to the result: cached_result['from_cache'] = True
                return cached_result

        # Check if schema context retrieval was successful (after cache check, as error response shouldn't be cached here).
        if original_schema_context.startswith("-- Schema context unavailable") or \
           original_schema_context.startswith("-- Error retrieving schema context"):
            self._log(f"Critical: Schema context not obtained or error during retrieval: {original_schema_context}", "error")
            # Return a standardized error structure.
            return {
                "sql_query": None, "error_message": original_schema_context, "confidence_score": 0.0,
                "llm_reasoning": None, "tables_used": [], "prompt_used": None,
                "query_results": {"data": None, "error": original_schema_context, "row_count":0, "page_number":page_number, "page_size":0, "total_pages":0},
                "execution_error_message": None
            }

        # Initialize variables for the correction loop (original_few_shots already fetched)
        processed_output: Dict[str, Any] = {} # Stores results from _process_llm_output and validations
        last_error_message: Optional[str] = None # Stores error from the last failed attempt
        last_generated_sql: Optional[str] = None # Stores SQL from the last failed attempt

        final_attempt_num = 0 # Tracks the number of attempts made

        # Step 3: Correction Loop (Iterate up to max_correction_attempts + 1 for initial attempt)
        for attempt in range(self.config.max_correction_attempts + 1):
            final_attempt_num = attempt + 1 # 1-indexed attempt number for logging
            self._log(f"NL-to-SQL attempt {final_attempt_num}/{self.config.max_correction_attempts + 1}", "info")

            # Step 3a: Construct LLM Prompt
            current_prompt: Optional[str]
            if attempt == 0: # Initial attempt
                current_prompt = self._construct_llm_prompt(
                    natural_language_query, original_schema_context, original_few_shots, is_correction=False
                )
            else: # Correction attempt
                if not last_generated_sql or not last_error_message:
                    # This should ideally not happen if the loop continues after an error.
                    self._log("Cannot attempt correction: missing last generated SQL or error message from previous attempt.", "error")
                    if not processed_output: # Ensure processed_output is initialized for error return
                        processed_output = {"error_message": "Correction failed due to missing prior state.", "confidence_score": 0.0}
                    break # Exit loop if prior state is missing for correction
                current_prompt = self._construct_llm_prompt(
                    natural_language_query, original_schema_context, original_few_shots,
                    is_correction=True, previous_sql=last_generated_sql, previous_error=last_error_message
                )

            if not current_prompt:
                self._log("LLM prompt construction failed. Aborting conversion.", "error")
                processed_output = {"error_message": "LLM prompt construction failed.", "confidence_score": 0.0}
                break # Exit loop if prompt construction fails

            # Step 3b: Invoke LLM
            raw_llm_response = self._invoke_llm(current_prompt)
            # Step 3c: Process LLM Output
            processed_output = self._process_llm_output(raw_llm_response, retrieved_tables_for_context)
            processed_output["prompt_used"] = current_prompt # Store the prompt used for this attempt for debugging/logging

            current_sql_query = processed_output.get('sql_query')
            # current_confidence = processed_output.get('confidence_score') # Initial confidence from _process_llm_output
            current_error = processed_output.get('error_message') # Error from _process_llm_output

            last_generated_sql = current_sql_query # Save for potential next correction
            last_error_message = current_error # Save for potential next correction

            # Check for critical issues from initial processing (no SQL, LLM error, disallowed keyword, bad extraction)
            if current_sql_query is None or current_error:
                self._log(f"Attempt {final_attempt_num} failed after LLM output processing. SQL is None or error exists: '{current_error}'", "warning")
                # Confidence is already set by _process_llm_output for these cases (e.g., 0.0, 0.05).
                # If LLM explicitly says it can't convert, or max attempts reached, stop.
                if self.config.error_string_for_no_conversion in str(current_error) or attempt == self.config.max_correction_attempts:
                    break # Stop if LLM gives up or max attempts reached
                continue # Otherwise, proceed to next attempt to try to correct this

            # At this point, current_sql_query is not None and current_error from _process_llm_output is None.
            # Step 3d: Validate SQL Syntax
            is_syntax_valid, syntax_error_msg = self._validate_sql_syntax(current_sql_query)
            if not is_syntax_valid:
                self._log(f"Syntax validation failed (attempt {final_attempt_num}): {syntax_error_msg}", "warning")
                last_error_message = f"Syntax Error: {syntax_error_msg}" # Update last_error_message for next correction attempt
                processed_output["error_message"] = last_error_message
                processed_output["confidence_score"] = 0.1 # Low confidence for syntax error
                if attempt == self.config.max_correction_attempts: break # Max attempts reached
                continue # Go to next correction attempt
            self._log(f"Syntax validation passed (attempt {final_attempt_num}).", "info")

            # Step 3e: Validate SQL Semantics
            is_semantic_valid, semantic_error_msg = self._validate_sql_semantically(current_sql_query)
            if not is_semantic_valid:
                self._log(f"Semantic validation failed (attempt {final_attempt_num}): {semantic_error_msg}", "warning")
                last_error_message = f"Semantic Error: {semantic_error_msg}" # Update for next correction
                processed_output["error_message"] = last_error_message
                processed_output["confidence_score"] = 0.2 # Low confidence for semantic error
                if attempt == self.config.max_correction_attempts: break # Max attempts reached
                continue # Go to next correction attempt

            # If both syntax and semantic validations pass:
            self._log(f"Semantic validation passed (attempt {final_attempt_num}).", "info")
            processed_output["error_message"] = None # Clear any minor error from _process_llm_output if validations pass

            # Step 3f: Adjust confidence score based on successful validation
            if attempt == 0: # Successful on the first try
                processed_output["confidence_score"] = 0.9 # High confidence
            else: # Successful after one or more corrections
                # Gradually decrease confidence for corrected queries, with a floor.
                processed_output["confidence_score"] = max(0.4, 0.8 - (0.1 * attempt))
            self._log(f"SQL query validated successfully (attempt {final_attempt_num}). Confidence set to: {processed_output['confidence_score']}", "info")
            break # Exit correction loop on successful validation

        # Step 4: Final Confidence Score Adjustment (if loop finished due to errors/max attempts)
        # This ensures that if an error message is present, the confidence score is appropriately low.
        # It handles cases where the loop might exit with a lingering higher confidence from _process_llm_output
        # if the error occurred before syntax/semantic checks in the final attempt.
        if processed_output.get("error_message") and \
           (processed_output.get("confidence_score", 0.0) > 0.3 or processed_output.get("confidence_score") is None):
            current_err = processed_output["error_message"]
            if "Syntax Error" in current_err: processed_output["confidence_score"] = 0.1
            elif "Semantic Error" in current_err: processed_output["confidence_score"] = 0.2
            # Check for disallowed keyword error specifically, if not already handled by _process_llm_output this way
            elif "disallowed keyword" in current_err.lower(): processed_output["confidence_score"] = 0.1
            # Check for LLM's explicit non-conversion
            elif self.config.error_string_for_no_conversion in current_err: processed_output["confidence_score"] = 0.0
            else: processed_output["confidence_score"] = 0.05 # General error or complete failure after attempts
            self._log(f"Adjusted confidence score to {processed_output['confidence_score']} due to error '{current_err}' after loop completion.", "debug")

        # Step 5: Execute SQL Query (if valid SELECT query generated)
        query_execution_result: Optional[Dict[str, Any]] = None
        execution_error_message: Optional[str] = None
        if processed_output.get('sql_query') and not processed_output.get('error_message'):
            # Only execute if SQL is present and no generation/validation errors exist.
            # The _execute_final_sql method handles SELECT query check and pagination.
            query_execution_result = self._execute_final_sql(
                processed_output['sql_query'], page_number, page_size
            )
            processed_output['query_results'] = query_execution_result # Attach results to output
            if query_execution_result.get("error"):
                execution_error_message = str(query_execution_result['error'])
                self._log(f"SQL execution failed: {execution_error_message}", "warning")
                # Optionally, penalize confidence if execution fails, though it passed validation.
                # This could indicate schema drift or subtle issues EXPLAIN didn't catch.
                # current_confidence = processed_output.get('confidence_score', 0.3)
                # processed_output['confidence_score'] = max(0.0, current_confidence - 0.2) # Example penalty
        else:
            # If no valid SQL query to execute (e.g., generation failed, or it's not a SELECT query implicitly)
            self._log("No valid SQL query to execute after all attempts, or execution skipped.", "warning")
            # Ensure 'query_results' structure is present even if execution is skipped.
            processed_output['query_results'] = {
                "data": None,
                "error": processed_output.get('error_message', "SQL query not validated or generated, or not a SELECT query."),
                "row_count":0, "page_number":page_number, "page_size":0, "total_pages":0
            }

        # Step 6: Ensure all expected keys are in the final output dictionary for consistent API.
        # Default values for keys that might be missing.
        final_result_keys = [
            "sql_query", "confidence_score", "llm_reasoning", "tables_used",
            "error_message", "prompt_used", "query_results", "execution_error_message"
        ]
        for key in final_result_keys:
            if key == "tables_used":
                processed_output.setdefault(key, [])
            elif key == "query_results":
                # Ensure query_results has a default structure if it's missing or None
                if processed_output.get(key) is None:
                    processed_output[key] = {"data": None, "error": "Execution not attempted or failed.", "row_count":0, "page_number":page_number, "page_size":0, "total_pages":0}
            elif key == "execution_error_message": # Already handled if it occurred, ensure it's None otherwise
                 processed_output.setdefault(key, None)
            else:
                processed_output.setdefault(key, None)

        # Cache Storage (before returning)
        if self.query_cache is not None and \
           processed_output.get("error_message") is None and \
           processed_output.get("execution_error_message") is None and \
           (processed_output.get("query_results", {}).get("error") is None if processed_output.get("query_results") else True) :
            # Only cache successful results without any errors (generation, validation, or execution)
            try:
                self.query_cache[cache_key] = processed_output
                self._log(f"Stored result in cache for query: '{natural_language_query[:50]}...'", "info")
            except Exception as e: # Catch potential issues with caching complex objects
                self._log(f"Error storing result in cache: {e}", "warning", exc_info=True)


        self._log(f"NL-to-SQL conversion process finished. Final SQL: '{processed_output.get('sql_query', 'No SQL')}', Confidence: {processed_output.get('confidence_score')}", "info")
        return processed_output


if __name__ == '__main__':
    # This __main__ block provides a basic example of how to use NLToSQLProcessor
    # and includes some mock-based tests for the correction loop and confidence scoring.
    # For more comprehensive testing, dedicated unit test files should be used.
    print("--- Basic Test Suite for NLToSQLProcessor ---")
    logging.basicConfig(
        level=logging.DEBUG, # Set to DEBUG to see detailed logs from the processor
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger_main = logging.getLogger(__name__)

    # Create temporary directory for test files
    test_dir = "temp_test_nl_processor_main_files"
    os.makedirs(test_dir, exist_ok=True)
    dummy_examples_path = os.path.join(test_dir, "dummy_examples_main.json")
    dummy_prompt_path = os.path.join(test_dir, "dummy_base_prompt_main.txt")
    dummy_chroma_path = os.path.join(test_dir, "dummy_chroma_main_store")

    try:
        # Create dummy few-shot examples file
        with open(dummy_examples_path, 'w') as f:
            json.dump([
                {"query": "show all machines", "sql": "SELECT * FROM machines;"}
            ], f)

        # Create dummy base prompt template file
        with open(dummy_prompt_path, 'w') as f:
            f.write(
                "Database Schema:\n{schema}\n\n"
                "Few-shot Examples:\n{examples}\n\n"
                "User Question: {user_question}\n\n"
                "Generated SQL for {dialect} (ONLY the SQL query):\n"
            )

        # Set environment variables for NLToSQLConfig
        # These would typically be set in your environment or a .env file
        os.environ["NLSQL_LOG_LEVEL"] = "DEBUG"
        os.environ["NLSQL_FEW_SHOT_PATH"] = dummy_examples_path
        os.environ["NLSQL_FEW_SHOT_EMBEDDING_MODEL"] = "all-MiniLM-L6-v2" # Mocked, so model choice isn't critical here
        os.environ["NLSQL_FEW_SHOT_STRATEGY"] = "basic"
        os.environ["NLSQL_NUM_FEW_SHOT_TO_SELECT"] = "1"

        os.environ["NLSQL_PROMPT_TEMPLATE_PATH"] = dummy_prompt_path

        os.environ["NLSQL_LLM_TYPE"] = "ollama"
        os.environ["NLSQL_LLM_MODEL_NAME"] = os.getenv("NLSQL_LLM_MODEL_NAME", "mistral") # Use env var if set, else default
        os.environ["NLSQL_LLM_BASE_URL"] = os.getenv("NLSQL_LLM_BASE_URL", "http://localhost:11434") # Use env var if set
        os.environ["NLSQL_LLM_TEMPERATURE"] = "0.1"

        os.environ["NLSQL_USE_DYNAMIC_SCHEMA"] = "True" # Enable DB interactions
        os.environ["NLSQL_DB_TYPE"] = "postgresql"
        os.environ["NLSQL_DB_HOST"] = os.getenv("TEST_DB_HOST", "test_db_host") # Mocked, actual connection not made in these tests
        os.environ["NLSQL_DB_PORT"] = os.getenv("TEST_DB_PORT","5432")
        os.environ["NLSQL_DB_USER"] = os.getenv("TEST_DB_USER","test_user")
        os.environ["NLSQL_DB_PASSWORD"] = os.getenv("TEST_DB_PASSWORD","test_pass")
        os.environ["NLSQL_DB_NAME"] = os.getenv("TEST_DB_NAME","test_db")
        os.environ["NLSQL_DB_SCHEMA_CACHE_TTL"] = "300"

        os.environ["NLSQL_USE_RAG_SCHEMA"] = "True" # Enable RAG
        os.environ["NLSQL_CHROMA_PATH"] = dummy_chroma_path
        os.environ["NLSQL_CHROMA_COLLECTION"] = "test_main_collection"
        os.environ["NLSQL_SCHEMA_EMBEDDING_MODEL"] = "all-MiniLM-L6-v2"
        os.environ["NLSQL_NUM_SCHEMA_CHUNKS"] = "3"

        os.environ["NLSQL_REMOVE_TRAILING_SEMICOLON"] = "True"
        os.environ["NLSQL_ERROR_STRING_NO_CONVERSION"] = "NO_CONVERSION_POSSIBLE"
        os.environ["NLSQL_DISALLOWED_KEYWORDS"] = "DROP,DELETE,UPDATE,INSERT" # Example
        os.environ["NLSQL_MAX_CORRECTION_ATTEMPTS"] = "2" # Allow for correction attempts

        os.environ["NLSQL_DEFAULT_PAGE_SIZE"] = "10"
        os.environ["NLSQL_MAX_PAGE_SIZE"] = "100"


        # Load configuration from environment variables
        config = NLToSQLConfig.load()
        logger_main.info("NLToSQLConfig loaded successfully for __main__ tests.")

        # Initialize the processor
        # For these tests, we'll mock external dependencies like DB and VectorStore handlers within tests
        # or provide simple custom schema to avoid needing live services.
        processor = NLToSQLProcessor(config=config)
        logger_main.info("NLToSQLProcessor initialized for __main__ tests.")

        nl_query = "show me all equipment names and their IDs"
        # A simplified custom schema for testing purposes to avoid live DB/VectorStore dependency
        custom_schema_for_test = (
            "CREATE TABLE equipment (machine_id TEXT PRIMARY KEY, machine_name VARCHAR(255), status TEXT);\n"
            "COMMENT ON COLUMN equipment.machine_name IS 'The common name of the equipment';"
        )
        valid_sql_for_query = "SELECT machine_name, machine_id FROM equipment" # Expected SQL

        if processor.llm: # Proceed with tests if LLM could be initialized (e.g., Ollama running)
            logger_main.info(f"LLM ({config.llm.model_name}) seems available. Running mock-based interaction tests.")

            # Test 1: Successful conversion on the first attempt
            with patch.object(processor, '_invoke_llm', return_value=f"```sql\n{valid_sql_for_query}\n```") as mock_llm_first_success, \
                 patch.object(processor.db_schema_handler if processor.db_schema_handler else 'builtins.print', '_execute_query', return_value=[{"plan": "mocked plan"}]) as mock_explain_success, \
                 patch.object(processor, '_retrieve_schema_context_for_query', return_value=(custom_schema_for_test, ["equipment"])) as mock_rag_success:

                logger_main.info(f"\n--- Test 1: Converting NL Query (expecting 1st attempt success): '{nl_query}' ---")
                result = processor.convert_nl_to_sql(
                    natural_language_query=nl_query
                    # custom_schema_info=custom_schema_for_test # Using RAG mock instead
                )
                logger_main.info(f"  SQL Query: {result.get('sql_query')}, Confidence: {result.get('confidence_score')}, Error: {result.get('error_message')}")
                assert result.get('sql_query') == valid_sql_for_query
                assert result.get('confidence_score') == 0.9 # High confidence for first try success
                assert result.get('error_message') is None
                mock_llm_first_success.assert_called_once()
                if processor.db_schema_handler: mock_explain_success.assert_called_once() # Semantic validation called

            # Test 2: Correction loop (syntax error -> semantic error -> success)
            # LLM responses: 1st is syntax error, 2nd is semantic error (e.g., wrong table), 3rd is correct
            llm_responses_for_correction_loop = [
                "SELECT machine_name, machine_id FROM equipmen", # Syntax error (misspelled table)
                "SELECT machine_name, machine_id FROM non_existent_table", # Semantic error (table not in schema)
                f"```sql\n{valid_sql_for_query};\n```"  # Correct SQL (with semicolon for cleaning test)
            ]
            # Mock EXPLAIN: first call (for non_existent_table) returns error, second call (for equipment) succeeds
            explain_side_effects = [None, [{"plan": "mocked plan"}]] # None indicates DB error for DBSchemaHandler

            with patch.object(processor, '_invoke_llm', side_effect=llm_responses_for_correction_loop) as mock_llm_correction, \
                 patch.object(processor.db_schema_handler if processor.db_schema_handler else 'builtins.print', '_execute_query', side_effect=explain_side_effects) as mock_explain_correction, \
                 patch.object(processor, '_retrieve_schema_context_for_query', return_value=(custom_schema_for_test, ["equipment"])) as mock_rag_correction:

                logger_main.info(f"\n--- Test 2: Converting NL Query (testing correction loop): '{nl_query}' ---")
                result_corr = processor.convert_nl_to_sql(
                    natural_language_query=nl_query
                )
                logger_main.info(f"  SQL Query: {result_corr.get('sql_query')}, Confidence: {result_corr.get('confidence_score')}, Error: {result_corr.get('error_message')}")
                assert result_corr.get('sql_query') == valid_sql_for_query # Semicolon removed by cleaning
                # Confidence after 2 correction attempts (0: initial, 1: syntax fix, 2: semantic fix)
                # attempt 0 fails syntax, attempt 1 fails semantic, attempt 2 succeeds. Confidence = 0.8 - (0.1 * 2) = 0.6
                assert result_corr.get('confidence_score') == max(0.4, 0.8 - (0.1 * 2)) # Expected: 0.6
                assert result_corr.get('error_message') is None
                assert mock_llm_correction.call_count == 3 # LLM called three times
                if processor.db_schema_handler: assert mock_explain_correction.call_count == 2 # EXPLAIN called for 2nd and 3rd SQL

            # Test 3: Disallowed keyword detection
            disallowed_sql = "DROP TABLE equipment"
            with patch.object(processor, '_invoke_llm', return_value=f"```{disallowed_sql}```") as mock_llm_disallowed, \
                 patch.object(processor, '_retrieve_schema_context_for_query', return_value=(custom_schema_for_test, ["equipment"])) as mock_rag_disallowed:
                logger_main.info(f"\n--- Test 3: Detecting disallowed keyword ---")
                result_disallowed = processor.convert_nl_to_sql(natural_language_query="Remove the equipment table")
                logger_main.info(f"  SQL Query: {result_disallowed.get('sql_query')}, Confidence: {result_disallowed.get('confidence_score')}, Error: {result_disallowed.get('error_message')}")
                assert result_disallowed.get('sql_query') is None
                assert "disallowed keyword: DROP" in result_disallowed.get('error_message', "")
                # Confidence for disallowed keyword is typically low, check _process_llm_output and convert_nl_to_sql logic
                # If loop finishes with error, confidence is adjusted. It should be around 0.05 or 0.1.
                assert result_disallowed.get('confidence_score') is not None and result_disallowed.get('confidence_score') <= 0.1

            # Test 4: LLM indicates no conversion possible
            with patch.object(processor, '_invoke_llm', return_value=config.error_string_for_no_conversion) as mock_llm_no_conversion, \
                 patch.object(processor, '_retrieve_schema_context_for_query', return_value=(custom_schema_for_test, ["equipment"])) as mock_rag_no_conversion:
                logger_main.info(f"\n--- Test 4: LLM returns configured 'no conversion' string ---")
                result_no_conv = processor.convert_nl_to_sql(natural_language_query="This is not a question about data")
                logger_main.info(f"  SQL Query: {result_no_conv.get('sql_query')}, Confidence: {result_no_conv.get('confidence_score')}, Error: {result_no_conv.get('error_message')}")
                assert result_no_conv.get('sql_query') is None
                assert result_no_conv.get('error_message') == config.error_string_for_no_conversion
                assert result_no_conv.get('confidence_score') == 0.0

        else:
            logger_main.warning("LLM (ChatOllama) not available or not initialized. Skipping mock-based interaction tests in __main__.")
            print("\nWARNING: LLM not available. NL-to-SQL conversion tests that require LLM interaction were skipped.")
            print("Please ensure an Ollama server (or configured LLM endpoint) is running and accessible if you want to run these tests.")


    except Exception as e:
        logger_main.error(f"Error during __main__ test execution: {e}", exc_info=True)
        print(f"An error occurred during the test run: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
    finally:
        # Clean up temporary files and directories
        if os.path.exists(dummy_examples_path): os.remove(dummy_examples_path)
        if os.path.exists(dummy_prompt_path): os.remove(dummy_prompt_path)
        if os.path.exists(dummy_chroma_path):
            import shutil
            shutil.rmtree(dummy_chroma_path)
            logger_main.info(f"Removed dummy Chroma DB path: {dummy_chroma_path}")
        if os.path.exists(test_dir):
            import shutil
            shutil.rmtree(test_dir) # Remove the main test directory
            logger_main.info(f"Removed test directory: {test_dir}")
        logger_main.info("\nCleaned up dummy files and test directory created by __main__.")
        print("\n--- Test Suite Finished ---")
```
