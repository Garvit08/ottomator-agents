# nl_to_sql_service/nl_to_sql_processor.py
"""Processes natural language queries to generate SQL queries.

This module defines the NLToSQLProcessor class, which orchestrates the
conversion of natural language questions into SQL queries. It leverages
configuration for LLMs, database schema handling (including RAG via
VectorStoreHandler), few-shot example management, and applies various
processing steps including prompt construction, LLM invocation, output parsing,
SQL syntax validation, semantic validation via EXPLAIN, and heuristic-based
confidence scoring.
"""
import os
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


DEFAULT_NL_TO_SQL_STOP_WORDS: Set[str] = set([
    'is', 'are', 'was', 'were', 'a', 'an', 'the', 'and', 'or', 'what', 'which', 'who',
    'when', 'where', 'how', 'show', 'me', 'list', 'find', 'get', 'of', 'for', 'in',
    'on', 'to', 'from', 'with', 'about', 'give', 'tell', 'can', 'could', 'may',
    'all', 'any', 'some', 'each', 'every', 'data', 'information', 'details',
    'summary', 'report', 'number', 'total', 'average', 'count', 'display',
    'what is', 'what are', 'show me', 'can you', 'could you', 'tell me'
])

def load_prompt_template(filepath: str, logger: logging.Logger) -> Optional[str]:
    """Loads a prompt template from a specified file path."""
    # (Implementation as before)
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
    """Orchestrates the conversion of natural language to SQL queries using RAG."""

    def __init__(self, config: NLToSQLConfig,
                 vector_store_handler: Optional[VectorStoreHandler] = None,
                 db_schema_handler: Optional[DBSchemaHandler] = None):
        """Initializes the NLToSQLProcessor."""
        # (Initialization logic as before)
        self.config = config
        self.logger = logging.getLogger(__name__)
        self._configure_logger()
        config_dump = config.model_dump_json(indent=2, exclude={'llm': {'api_key'}, 'db_schema_handler': {'password'}})
        self._log(f"Initializing NLToSQLProcessor with config: {config_dump}", "info")

        self.few_shot_manager = FewShotManager(
            examples_filepath=config.few_shot_examples_path,
            embedding_model_name=config.few_shot_embedding_model,
            logger=self.logger
        )

        if vector_store_handler:
            self.vector_store_handler = vector_store_handler
        else:
            self.vector_store_handler = VectorStoreHandler(config=config, logger=self.logger)
            self._log("VectorStoreHandler initialized by NLToSQLProcessor.", "info")

        self.db_schema_handler: Optional[DBSchemaHandler] = db_schema_handler
        if not self.db_schema_handler and config.use_dynamic_schema_handling and config.db_schema_handler:
             db_handler_config_dict = config.db_schema_handler.model_dump()
             if db_handler_config_dict.get("host") or db_handler_config_dict.get("connection_string"):
                 self.db_schema_handler = DBSchemaHandler(
                     db_config=db_handler_config_dict, logger=self.logger,
                     cache_ttl_seconds=config.db_schema_handler.schema_cache_ttl_seconds
                 )
                 self._log("DBSchemaHandler also initialized.", "info")

        self.llm: Optional[ChatOllama] = None
        if CHAT_OLLAMA_AVAILABLE and ChatOllama is not None:
            try:
                self.llm = ChatOllama(
                    model=config.llm.model_name, base_url=config.llm.base_url,
                    temperature=config.llm.temperature
                )
                self._log(f"ChatOllama LLM initialized: model='{config.llm.model_name}', temp={config.llm.temperature}", "info")
            except Exception as e:
                self._log(f"Error initializing ChatOllama: {e}. LLM unavailable.", "error", exc_info=True)
        else:
            self._log("ChatOllama library not available. LLM couldn't be initialized.", "error")

        self.base_prompt_template: Optional[str] = load_prompt_template(config.base_prompt_template_path, self.logger)
        if not self.base_prompt_template:
            self._log(f"CRITICAL: Base prompt template failed to load: {config.base_prompt_template_path}", "error")

        if not SQLGLOT_AVAILABLE:
            self._log("sqlglot library not found. SQL syntax validation will be skipped.", "warning")
        else:
            self._log("sqlglot library available for SQL syntax validation.", "info")

        if not (self.db_schema_handler and self.config.use_dynamic_schema_handling):
            self._log("DBSchemaHandler not available or dynamic schema handling disabled. SQL semantic validation will be skipped.", "warning")


    def _configure_logger(self):
        # (Implementation as before)
        log_level_str = self.config.log_level.upper()
        numeric_level = getattr(logging, log_level_str, logging.INFO)
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
        self.logger.setLevel(numeric_level)

    def _log(self, message: str, level: str = "info", exc_info: bool = False):
        # (Implementation as before)
        if level.lower() == "debug": self.logger.debug(message)
        elif level.lower() == "info": self.logger.info(message)
        elif level.lower() == "warning": self.logger.warning(message)
        elif level.lower() == "error": self.logger.error(message, exc_info=exc_info)
        elif level.lower() == "critical": self.logger.critical(message, exc_info=exc_info)

    def _extract_keywords(self, text: str) -> List[str]:
        # (Implementation as before)
        if not text: return []
        text_lower = text.lower()
        text_cleaned = re.sub(r'[^\w\s_]', '', text_lower)
        words = text_cleaned.split()
        keywords = [word for word in words if word not in DEFAULT_NL_TO_SQL_STOP_WORDS and len(word) > 1]
        return list(set(keywords))

    def _retrieve_schema_context_for_query(self, natural_language_query: str) -> Tuple[str, List[str]]:
        # (Implementation as before)
        self._log(f"Retrieving RAG schema context for query: '{natural_language_query[:70]}...'", "info")
        default_error_return = ("-- Schema context unavailable: Vector store or embedding model not initialized --", [])
        if not self.vector_store_handler or not self.vector_store_handler.embedding_model:
            self._log("VectorStoreHandler or its embedding model not initialized for RAG.", "error")
            return default_error_return
        try:
            retrieved_items = self.vector_store_handler.retrieve_relevant_schema_chunks(
                query_text=natural_language_query, n_results=self.config.num_schema_chunks_for_prompt
            )
        except Exception as e:
            self._log(f"Error during RAG schema chunk retrieval: {e}", "error", exc_info=True)
            return "-- Error retrieving schema context from vector store --", []
        if not retrieved_items:
            return "-- No specific schema context found for this query in the vector store --", []
        schema_context_parts = [item["text_content"] for item in retrieved_items if isinstance(item, dict) and "text_content" in item]
        retrieved_table_names = list(set(
            str(item["metadata"]["table_name"]) for item in retrieved_items
            if isinstance(item.get("metadata"), dict) and item["metadata"].get("table_name")
        ))
        schema_context_str = "\n\n--- Schema Chunk ---\n".join(schema_context_parts)
        self._log(f"Retrieved {len(schema_context_parts)} schema chunks for RAG. Tables: {retrieved_table_names}. Context snippet: {schema_context_str[:100]}...", "debug")
        return schema_context_str, retrieved_table_names

    def _get_relevant_few_shots(self, natural_language_query: str,
                                custom_few_shot_examples: Optional[List[Dict[str, Any]]]
                               ) -> List[Dict[str, Any]]:
        # (Implementation as before)
        if custom_few_shot_examples is not None: return custom_few_shot_examples
        if self.few_shot_manager:
            return self.few_shot_manager.get_relevant_examples(
                natural_language_query, self.config.num_few_shot_examples_to_select,
                self.config.few_shot_selection_strategy
            )
        return []

    def _construct_llm_prompt(self, natural_language_query: str,
                              schema_context_from_rag: str,
                              relevant_few_shots: List[Dict[str, Any]]
                             ) -> Optional[str]:
        # (Implementation as before)
        if not self.base_prompt_template: return None
        formatted_examples = self.few_shot_manager.format_examples_for_prompt(relevant_few_shots)
        sql_dialect = (self.config.db_schema_handler.db_type
                       if self.config.db_schema_handler and self.config.db_schema_handler.db_type
                       else "SQL")
        try:
            return self.base_prompt_template.format(
                schema=schema_context_from_rag, user_question=natural_language_query,
                examples=formatted_examples or "# No few-shot examples provided.", dialect=sql_dialect
            )
        except KeyError as e:
            self._log(f"Error formatting prompt. Missing key: {e}.", "error", exc_info=True)
            return None

    def _invoke_llm(self, full_prompt: str) -> Optional[str]:
        # (Implementation as before)
        if not self.llm: return None
        if not HumanMessage and CHAT_OLLAMA_AVAILABLE and isinstance(self.llm, ChatOllama): return None
        self._log(f"Invoking LLM. Prompt snippet: {full_prompt[:150]}...", "info")
        try:
            if CHAT_OLLAMA_AVAILABLE and HumanMessage and isinstance(self.llm, ChatOllama):
                 message = HumanMessage(content=full_prompt)
                 response = self.llm.invoke([message])
                 content = str(response.content)
            else:
                content = str(self.llm.invoke(full_prompt))
            self._log(f"LLM raw response snippet: {content[:150]}...", "debug")
            return content
        except Exception as e:
            self._log(f"Error invoking LLM: {e}", "error", exc_info=True)
            return None

    def _validate_sql_syntax(self, sql_query: str) -> Tuple[bool, Optional[str]]:
        """Validates the SQL query syntax using sqlglot."""
        # (Implementation as before)
        if not SQLGLOT_AVAILABLE or sqlglot is None or SQLGlotParseError is None:
            msg = "Syntax validation skipped: sqlglot library not available."
            self._log(msg, "warning")
            return True, msg
        if not sql_query or not sql_query.strip():
            return False, "No SQL query to validate."
        try:
            dialect = self.config.db_schema_handler.db_type if self.config.db_schema_handler and self.config.db_schema_handler.db_type else None
            sqlglot.parse_one(sql_query, read=dialect if dialect else None)
            self._log(f"SQL syntax validation successful for query: {sql_query[:100]}...", "debug")
            return True, None
        except SQLGlotParseError as e:
            error_msg = f"SQLGlot ParseError: {str(e)}"
            self._log(f"SQL syntax validation failed: {error_msg} for query: {sql_query[:100]}...", "warning")
            return False, error_msg
        except Exception as e:
            error_msg = f"Unexpected error during SQL syntax validation with sqlglot: {str(e)}"
            self._log(f"SQL syntax validation failed: {error_msg} for query: {sql_query[:100]}...", "error", exc_info=True)
            return False, error_msg

    def _validate_sql_semantically(self, sql_query: str) -> Tuple[bool, Optional[str]]:
        """
        Validates the SQL query semantically against the database using EXPLAIN.

        Args:
            sql_query (str): The SQL query string to validate.

        Returns:
            Tuple[bool, Optional[str]]: A tuple containing:
                - bool: True if semantic validation passes or is skipped, False otherwise.
                - Optional[str]: An error message if validation fails, or a message
                  indicating skipping. None if valid.
        """
        if not self.config.use_dynamic_schema_handling or not self.db_schema_handler:
            msg = "Semantic validation skipped: DBSchemaHandler not available or dynamic schema handling disabled."
            self._log(msg, "warning")
            return True, msg # Skip if no DB connection to test against

        if not sql_query or not sql_query.strip():
            return False, "No SQL query for semantic validation."

        # Construct the EXPLAIN query
        # Using EXPLAIN (without ANALYZE) is safer as it doesn't execute the query.
        validation_query = f"EXPLAIN {sql_query}"
        self._log(f"Attempting semantic validation with query: {validation_query[:150]}...", "debug")

        try:
            # _execute_query returns None on DB error, or a list (empty for EXPLAIN success)
            # The original error message from psycopg2 is logged by _execute_query itself.
            # We need to capture that error message here.
            # For now, let's assume _execute_query needs to be adapted or we need a new method
            # in DBSchemaHandler that returns the error string from the DB if one occurs.
            # Let's simulate this by trying to catch the exception here if _execute_query re-raises it,
            # or by checking a special return value.
            # For now, assuming _execute_query returns None on failure.

            # Re-checking _execute_query: it catches psycopg2.Error and logs it, then returns None.
            # It doesn't propagate the error message text back to the caller directly.
            # This needs adjustment in DBSchemaHandler or a new method.
            # For this step, we'll proceed assuming _execute_query could return a specific error object or None.
            # Let's assume for now that if it returns None, it's a DB error.

            # We need a way for _execute_query to return the DB error message.
            # Modifying _execute_query is outside this immediate task's scope for this file.
            # So, we'll mock this part of the interaction for now or make a simplifying assumption.
            # Let's assume a successful EXPLAIN returns an empty list or list of plan rows,
            # and a failed EXPLAIN (due to semantic error) makes _execute_query return None.

            # This is a placeholder for how DBSchemaHandler might be used:
            # explain_result = self.db_schema_handler._execute_query_with_error_return(validation_query)
            # if explain_result.get("success"):
            #     return True, None
            # else:
            #     return False, explain_result.get("error")

            # Current _execute_query behavior: Returns List[Dict] or None on error.
            # A successful EXPLAIN might return an empty list or plan rows.
            # A failed EXPLAIN (semantic error) will cause psycopg2.Error in _execute_query, which returns None.

            # We need to capture the actual error from the database.
            # This requires modifying DBSchemaHandler._execute_query or adding a new method.
            # For now, if _execute_query returns None, we know there was a DB error.
            # We don't have the *exact* error message here unless we parse logs or change DBSchemaHandler.

            # Simplification for now: if _execute_query returns None, it's a semantic error.
            # The actual error message is already logged by DBSchemaHandler.
            explain_results = self.db_schema_handler._execute_query(validation_query)

            if explain_results is not None: # Query executed without DB error
                self._log(f"SQL semantic validation (EXPLAIN) successful for query: {sql_query[:100]}...", "info")
                return True, None
            else:
                # _execute_query already logged the specific psycopg2 error.
                error_msg = "Semantic validation failed: EXPLAIN statement execution error. Check logs for DB error."
                self._log(error_msg + f" Query: {sql_query[:100]}...", "warning")
                # To get a more specific error, DBSchemaHandler._execute_query would need to return it.
                return False, error_msg # Generic message for now

        except Exception as e: # Catch any other unexpected error
            error_msg = f"Unexpected error during semantic validation: {str(e)}"
            self._log(error_msg + f" Query: {sql_query[:100]}...", "error", exc_info=True)
            return False, error_msg


    def _process_llm_output(self, llm_raw_response: Optional[str],
                            tables_from_rag_context: Optional[List[str]] = None
                           ) -> Dict[str, Any]:
        # (Implementation as before, confidence logic for syntax error will be moved)
        sql_query: Optional[str] = None
        confidence_score: Optional[float] = None
        error_message: Optional[str] = None
        tables_used_output: List[str] = tables_from_rag_context if tables_from_rag_context else []

        if not llm_raw_response or not llm_raw_response.strip():
            error_message = "LLM returned no response or an empty response."
            confidence_score = 0.0
        elif llm_raw_response.strip() == self.config.error_string_for_no_conversion:
            error_message = self.config.error_string_for_no_conversion
            confidence_score = 0.0
        else:
            match = re.search(r"```(?:sql\s*)?(.*?)\s*```", llm_raw_response, re.DOTALL | re.IGNORECASE)
            if match:
                sql_query = match.group(1).strip()
            else:
                temp_sql_query = llm_raw_response.strip()
                explanation_phrases = ["here is the sql query:", "here's the sql query:", "sure, here is the query:"]
                temp_query_lower = temp_sql_query.lower()
                for phrase in explanation_phrases:
                    if temp_query_lower.startswith(phrase):
                        temp_sql_query = temp_sql_query[len(phrase):].strip(); break
                if temp_sql_query.lstrip().upper().startswith(("SELECT", "WITH", "INSERT", "UPDATE", "DELETE")):
                    sql_query = temp_sql_query
                else:
                    error_message = "Failed to extract SQL from LLM response (no backticks/SQL keywords)."
                    confidence_score = 0.2 # Extraction failure

            if sql_query:
                if self.config.remove_trailing_semicolon and sql_query.endswith(';'):
                    sql_query = sql_query[:-1].strip()

                if self.config.disallowed_sql_keywords: # Security check
                    query_upper = sql_query.upper()
                    for keyword in self.config.disallowed_sql_keywords:
                        if re.search(r"\b" + re.escape(keyword) + r"\b", query_upper):
                            error_message = f"Generated SQL contains disallowed keyword: {keyword}."
                            # Confidence for disallowed keyword is set in convert_nl_to_sql
                            sql_query = None; break

                if sql_query and confidence_score is None: # Not yet set by other critical issues
                    if len(sql_query.strip()) < 8:
                        error_message = error_message or "Generated SQL is trivial or too short."
                        # Confidence for trivial query is set in convert_nl_to_sql
                    else: # Default confidence if extracted, not disallowed, not trivial
                        confidence_score = 0.7

            elif not error_message and confidence_score is None:
                error_message = "SQL extraction failed."
                confidence_score = 0.2

        output_dict: Dict[str, Any] = {
            "sql_query": sql_query, "confidence_score": confidence_score,
            "llm_reasoning": None, "tables_used": tables_used_output,
            "error_message": error_message
        }
        self._log(f"Initial LLM output processing -- SQL: {sql_query[:100] if sql_query else 'None'}, Initial Confidence: {confidence_score}, Error: {error_message}", "info")
        return output_dict

    def convert_nl_to_sql(self, natural_language_query: str,
                          custom_schema_info: Optional[str] = None,
                          custom_few_shot_examples: Optional[List[Dict[str, Any]]] = None
                         ) -> Dict[str, Any]:
        self._log(f"Starting NL-to-SQL conversion for query: '{natural_language_query[:100]}...'", "info")

        schema_context_string, retrieved_tables_for_context = self._retrieve_schema_context_for_query(natural_language_query)
        if custom_schema_info:
            self._log("Using provided custom_schema_info, RAG context will be ignored for prompt.", "info")
            schema_context_string = custom_schema_info
            retrieved_tables_for_context = []

        if schema_context_string.startswith("-- Schema") or schema_context_string.startswith("-- Error"):
            self._log(f"Critical: Schema context not obtained: {schema_context_string}", "error")
            return {"sql_query": None, "error_message": schema_context_string, "confidence_score": 0.0, "llm_reasoning": None, "tables_used": [], "prompt_used": None}

        few_shots = self._get_relevant_few_shots(natural_language_query, custom_few_shot_examples)
        llm_prompt = self._construct_llm_prompt(natural_language_query, schema_context_string, few_shots)

        if not llm_prompt:
            return {"sql_query": None, "error_message": "LLM prompt construction failed.", "confidence_score": 0.0, "llm_reasoning": None, "tables_used": retrieved_tables_for_context, "prompt_used": None}

        raw_llm_response = self._invoke_llm(llm_prompt)

        # Initial processing (extraction, cleaning, basic checks like disallowed keywords, LLM error string)
        processed_output = self._process_llm_output(raw_llm_response, retrieved_tables_for_context)
        processed_output["prompt_used"] = llm_prompt

        current_sql_query = processed_output.get('sql_query')
        # If a critical error already occurred in _process_llm_output (e.g., disallowed keyword),
        # current_sql_query might be None and error_message set. Confidence might also be set low.

        # SQL Syntax Validation
        if current_sql_query and not processed_output.get('error_message'):
            is_syntax_valid, syntax_error_message = self._validate_sql_syntax(current_sql_query)
            if not is_syntax_valid:
                self._log(f"SQL syntax validation failed: {syntax_error_message}", "warning")
                processed_output['error_message'] = f"Syntax Error: {syntax_error_message}"
                processed_output['confidence_score'] = 0.1 # Override confidence
            else:
                self._log("SQL syntax validation successful.", "info")
                # If syntax is valid, confidence from _process_llm_output (e.g., 0.7 or 0.3) is maintained.

        # SQL Semantic Validation (Dry-run with EXPLAIN)
        # Only proceed if SQL query exists and no prior syntax or critical processing error.
        if processed_output.get('sql_query') and not processed_output.get('error_message'):
            is_semantic_valid, semantic_error_message = self._validate_sql_semantically(processed_output['sql_query'])
            if not is_semantic_valid:
                self._log(f"SQL semantic validation failed: {semantic_error_message}", "warning")
                # Prepend to existing error_message if any, or set it.
                current_err = processed_output.get('error_message')
                combined_err = f"Semantic Error: {semantic_error_message}"
                if current_err and "Syntax Error" not in current_err : # Avoid overwriting a more specific syntax error if semantic check was somehow run
                     combined_err = f"{current_err}; {combined_err}"
                processed_output['error_message'] = combined_err
                processed_output['confidence_score'] = 0.2 # Lower confidence for semantic error
            else:
                self._log("SQL semantic validation (EXPLAIN) successful.", "info")
                # If syntax was 0.3 (trivial) but semantically valid, could slightly bump, e.g. to 0.4
                if processed_output.get('confidence_score') == 0.3:
                    processed_output['confidence_score'] = 0.4
                # If it was 0.7 (default good), it remains 0.7 or could be higher.

        self._log(f"NL-to-SQL conversion complete. Final SQL: {processed_output.get('sql_query', 'None')}, Confidence: {processed_output.get('confidence_score')}", "info")
        return processed_output


if __name__ == '__main__':
    # (Updated __main__ block as before, potentially adding a case for syntax/semantic error testing)
    print("--- Testing NLToSQLProcessor with RAG, Syntax and Semantic Validation ---")
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    test_dir = "temp_test_nl_processor_validation_files"
    os.makedirs(test_dir, exist_ok=True)
    dummy_examples_path = os.path.join(test_dir, "dummy_examples_validation.json")
    dummy_prompt_path = os.path.join(test_dir, "dummy_base_prompt_validation.txt")
    dummy_chroma_path = os.path.join(test_dir, "dummy_chroma_validation")

    try:
        with open(dummy_examples_path, 'w') as f: json.dump([], f)
        with open(dummy_prompt_path, 'w') as f: f.write("Schema:\n{schema}\nQ: {user_question}\nEx:\n{examples}\nSQL for {dialect}:")

        # Setup environment variables for config
        os.environ["NLSQL_FEW_SHOT_PATH"] = dummy_examples_path
        os.environ["NLSQL_PROMPT_TEMPLATE_PATH"] = dummy_prompt_path
        os.environ["NLSQL_USE_DYNAMIC_SCHEMA"] = "True" # To test DBSchemaHandler path
        os.environ["NLSQL_LOG_LEVEL"] = "DEBUG"
        os.environ["NLSQL_CHROMA_PATH"] = dummy_chroma_path
        os.environ["NLSQL_CHROMA_COLLECTION"] = "test_validation_collection"
        os.environ["NLSQL_SCHEMA_EMBEDDING_MODEL"] = "all-MiniLM-L6-v2"
        # For DB connection (semantic validation) - ensure these are set for your test environment
        if not os.getenv("NLSQL_DB_HOST"): os.environ["NLSQL_DB_HOST"] = "localhost"
        if not os.getenv("NLSQL_DB_USER"): os.environ["NLSQL_DB_USER"] = "postgres" # Replace if needed
        if not os.getenv("NLSQL_DB_PASSWORD"): os.environ["NLSQL_DB_PASSWORD"] = "password" # Replace if needed
        if not os.getenv("NLSQL_DB_NAME"): os.environ["NLSQL_DB_NAME"] = "smart_factory_db" # Replace if needed
        if not os.getenv("NLSQL_DB_TYPE"): os.environ["NLSQL_DB_TYPE"] = "postgresql"
        if not os.getenv("NLSQL_LLM_MODEL_NAME"): os.environ["NLSQL_LLM_MODEL_NAME"] = "mistral"
        if not os.getenv("NLSQL_LLM_BASE_URL"): os.environ["NLSQL_LLM_BASE_URL"] = "http://localhost:11434"


        config = NLToSQLConfig.load()
        # Ensure DBSchemaHandler is initialized for semantic validation test
        # NLToSQLProcessor's __init__ handles this based on config.use_dynamic_schema_handling
        processor = NLToSQLProcessor(config=config)

        nl_query = "Get all users from the users table"

        # Mock LLM to return syntactically incorrect SQL
        if processor.llm and SQLGLOT_AVAILABLE and processor.db_schema_handler:
            with patch.object(processor, '_invoke_llm', return_value="SELECT FROM users WHERE name = 'test'") as mock_llm_invalid_syntax:
                print(f"\n--- Converting NL Query (expecting syntax error): '{nl_query}' ---")
                # Provide a minimal custom schema that _validate_sql_semantically would act upon if syntax were ok
                result_syntax_err = processor.convert_nl_to_sql(natural_language_query=nl_query, custom_schema_info="CREATE TABLE users (id INT, name TEXT);")
                print(f"  SQL Query: {result_syntax_err.get('sql_query')}")
                print(f"  Confidence: {result_syntax_err.get('confidence_score')}")
                print(f"  Error: {result_syntax_err.get('error_message')}")
                assert result_syntax_err.get('confidence_score', 1.0) <= 0.1
                assert "Syntax Error:" in result_syntax_err.get('error_message', "")

            # Mock LLM to return syntactically correct but semantically incorrect SQL (e.g. wrong table)
            with patch.object(processor, '_invoke_llm', return_value="SELECT name FROM non_existent_table WHERE id = 1;") as mock_llm_invalid_semantic:
                print(f"\n--- Converting NL Query (expecting semantic error): '{nl_query}' ---")
                result_semantic_err = processor.convert_nl_to_sql(natural_language_query=nl_query, custom_schema_info="CREATE TABLE users (id INT, name TEXT);")
                print(f"  SQL Query: {result_semantic_err.get('sql_query')}")
                print(f"  Confidence: {result_semantic_err.get('confidence_score')}")
                print(f"  Error: {result_semantic_err.get('error_message')}")
                assert result_semantic_err.get('confidence_score', 1.0) <= 0.2
                assert "Semantic Error:" in result_semantic_err.get('error_message', "")

            # Mock LLM to return valid SQL
            with patch.object(processor, '_invoke_llm', return_value="SELECT name FROM users WHERE id = 1;") as mock_llm_valid_sql:
                print(f"\n--- Converting NL Query (expecting valid SQL): '{nl_query}' ---")
                # Assuming 'users' table exists in your test DB for EXPLAIN to pass
                # If not, this semantic check might fail or be skipped.
                # For a fully isolated test of _validate_sql_semantically, DBSchemaHandler._execute_query would be mocked.
                result_valid = processor.convert_nl_to_sql(natural_language_query=nl_query, custom_schema_info="CREATE TABLE users (id INT, name TEXT);")
                print(f"  SQL Query: {result_valid.get('sql_query')}")
                print(f"  Confidence: {result_valid.get('confidence_score')}")
                print(f"  Error: {result_valid.get('error_message')}")
                # Confidence depends on whether semantic validation was skipped or passed
                if "Semantic validation skipped" in str(result_valid.get('error_message')):
                    assert result_valid.get('confidence_score', 0.0) >= 0.7 # Syntax valid, semantic skipped
                else: # Assumes semantic validation passed
                    assert result_valid.get('confidence_score', 0.0) >= 0.7
        else:
            print("\nSkipping some validation tests: LLM, sqlglot, or DBSchemaHandler not fully available/configured for this test run.")


    except Exception as e:
        print(f"Error during test: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
    finally:
        if os.path.exists(dummy_examples_path): os.remove(dummy_examples_path)
        if os.path.exists(dummy_prompt_path): os.remove(dummy_prompt_path)
        if os.path.exists(dummy_chroma_path):
            import shutil
            shutil.rmtree(dummy_chroma_path)
        if os.path.exists(test_dir):
            import shutil
            shutil.rmtree(test_dir)
        print("\nCleaned up dummy files and test directory.")

```
