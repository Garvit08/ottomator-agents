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

        if not (self.db_schema_handler and self.config.use_dynamic_schema_handling): # Check if handler is usable
            self._log("DBSchemaHandler not available or dynamic schema handling disabled. SQL semantic validation and execution will be skipped/limited.", "warning")


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
                              schema_context: str,
                              relevant_few_shots: List[Dict[str, Any]],
                              is_correction: bool = False,
                              previous_sql: Optional[str] = None,
                              previous_error: Optional[str] = None
                             ) -> Optional[str]:
        # (Implementation as before)
        if not self.base_prompt_template: return None
        formatted_examples = self.few_shot_manager.format_examples_for_prompt(relevant_few_shots)
        sql_dialect = (self.config.db_schema_handler.db_type
                       if self.config.db_schema_handler and self.config.db_schema_handler.db_type
                       else "SQL")
        current_prompt_str = self.base_prompt_template
        prompt_data = { "schema": schema_context, "user_question": natural_language_query,
                        "examples": formatted_examples or "# No few-shot examples provided.", "dialect": sql_dialect}
        if is_correction:
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
            prompt_data = {} # Prompt is fully formed for correction
        try:
            final_prompt = current_prompt_str.format(**prompt_data) if prompt_data else current_prompt_str
            self._log(f"Final LLM prompt type: {'Corrective' if is_correction else 'Initial'}.", "debug")
            return final_prompt
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
        # (Implementation as before)
        if not SQLGLOT_AVAILABLE or sqlglot is None or SQLGlotParseError is None:
            return True, "Syntax validation skipped: sqlglot library not available."
        if not sql_query or not sql_query.strip(): return False, "No SQL query to validate."
        try:
            dialect = self.config.db_schema_handler.db_type if self.config.db_schema_handler and self.config.db_schema_handler.db_type else None
            sqlglot.parse_one(sql_query, read=dialect)
            return True, None
        except SQLGlotParseError as e: return False, f"SQLGlot ParseError: {str(e)}"
        except Exception as e: return False, f"Unexpected error during SQL syntax validation: {str(e)}"

    def _validate_sql_semantically(self, sql_query: str) -> Tuple[bool, Optional[str]]:
        # (Implementation as before)
        if not self.config.use_dynamic_schema_handling or not self.db_schema_handler:
            return True, "Semantic validation skipped: DBSchemaHandler not configured or disabled."
        if not sql_query or not sql_query.strip(): return False, "No SQL query for semantic validation."
        validation_query = f"EXPLAIN {sql_query}"
        self._log(f"Attempting semantic validation with query: {validation_query[:150]}...", "debug")
        try:
            explain_results = self.db_schema_handler._execute_query(validation_query)
            if explain_results is not None: return True, None
            else: return False, "Semantic validation failed: EXPLAIN execution error (check logs for DB error)."
        except Exception as e: return False, f"Unexpected error during semantic validation: {str(e)}"


    def _process_llm_output(self, llm_raw_response: Optional[str],
                            tables_from_rag_context: Optional[List[str]] = None
                           ) -> Dict[str, Any]:
        """Processes raw LLM output for initial SQL extraction and basic checks.

        Confidence scores set here are preliminary and may be adjusted by subsequent
        validation steps in the main `convert_nl_to_sql` flow.
        """
        sql_query: Optional[str] = None
        confidence_score: Optional[float] = None # Initialized to None
        error_message: Optional[str] = None
        tables_used_output: List[str] = tables_from_rag_context if tables_from_rag_context else []

        if not llm_raw_response or not llm_raw_response.strip():
            error_message = "LLM returned no response or an empty response."
            confidence_score = 0.0 # Explicitly 0.0 for no response
        elif llm_raw_response.strip() == self.config.error_string_for_no_conversion:
            error_message = self.config.error_string_for_no_conversion
            confidence_score = 0.0 # Explicitly 0.0 for LLM non-conversion
        else:
            # Attempt to extract SQL query
            match = re.search(r"```(?:sql\s*)?(.*?)\s*```", llm_raw_response, re.DOTALL | re.IGNORECASE)
            if match:
                sql_query = match.group(1).strip()
                self._log(f"Extracted SQL from backticks: {sql_query[:100]}...", "debug")
            else:
                temp_sql_query = llm_raw_response.strip()
                explanation_phrases = ["here is the sql query:", "here's the sql query:", "sure, here is the query:"]
                temp_query_lower = temp_sql_query.lower()
                for phrase in explanation_phrases:
                    if temp_query_lower.startswith(phrase):
                        temp_sql_query = temp_sql_query[len(phrase):].strip()
                        break
                if temp_sql_query.lstrip().upper().startswith(("SELECT", "WITH", "INSERT", "UPDATE", "DELETE")):
                    sql_query = temp_sql_query
                    self._log(f"No backticks. Using full/trimmed response as SQL: {sql_query[:100]}...", "debug")
                else:
                    error_message = "Failed to extract SQL from LLM response (no backticks or common SQL start keywords)."
                    confidence_score = 0.05 # Very low if extraction fails completely

            if sql_query:
                if self.config.remove_trailing_semicolon and sql_query.endswith(';'):
                    sql_query = sql_query[:-1].strip()

                # Security check - if this fails, SQL is None, error_message is set.
                # Confidence will be handled by the main loop for this specific error.
                if self.config.disallowed_sql_keywords:
                    query_upper = sql_query.upper()
                    for keyword in self.config.disallowed_sql_keywords:
                        if re.search(r"\b" + re.escape(keyword) + r"\b", query_upper):
                            error_message = f"Generated SQL contains disallowed keyword: {keyword}."
                            # Confidence for disallowed keyword (0.1) will be set in convert_nl_to_sql
                            sql_query = None
                            break

                if sql_query and confidence_score is None: # If not yet set by other issues
                    # This is a successfully extracted query, pre-validation.
                    # Trivial check will be done after syntax/semantic pass.
                    confidence_score = 0.7 # Default initial confidence for successfully extracted SQL

            # If SQL query is None by now (either bad extraction or security issue) AND no specific confidence set
            elif not sql_query and confidence_score is None:
                error_message = error_message or "SQL extraction failed or query invalidated by security checks."
                confidence_score = 0.05 # Very low for failed extraction or security invalidation

        output_dict: Dict[str, Any] = {
            "sql_query": sql_query, "confidence_score": confidence_score,
            "llm_reasoning": None, "tables_used": tables_used_output,
            "error_message": error_message
        }
        self._log(f"Initial LLM output processing -- SQL: {sql_query[:100] if sql_query else 'None'}, Initial Confidence: {confidence_score}, Error: {error_message}", "info")
        return output_dict

    def _execute_final_sql(self, sql_query: str, page_number: int = 1, page_size: Optional[int] = None) -> Dict[str, Any]:
        # (Implementation as before)
        default_error_payload = {"data": None, "error": "An error occurred during SQL execution.", "row_count":0, "page_number":page_number, "page_size":0}
        if not self.config.use_dynamic_schema_handling or not self.db_schema_handler:
            default_error_payload["error"] = "Database connection not available for query execution."; return default_error_payload
        if not sql_query or not sql_query.strip().upper().startswith("SELECT"):
            default_error_payload["error"] = "Execution Error: Only SELECT queries can be executed."; return default_error_payload
        page_size_to_use = page_size if page_size is not None and page_size > 0 else self.config.default_page_size
        if page_size_to_use > self.config.max_page_size: page_size_to_use = self.config.max_page_size
        if page_size_to_use <= 0 : page_size_to_use = self.config.default_page_size
        if page_number < 1: page_number = 1
        offset = (page_number - 1) * page_size_to_use
        paginated_sql = f"{sql_query} LIMIT {page_size_to_use} OFFSET {offset}"
        self._log(f"Executing paginated SQL: {paginated_sql[:200]}...", "info")
        try:
            results = self.db_schema_handler._execute_query(paginated_sql)
            if results is None: default_error_payload["error"] = "Database execution error (check logs)."; return default_error_payload
            return {"data": results, "row_count": len(results), "page_number": page_number, "page_size": page_size_to_use, "error": None}
        except Exception as e: default_error_payload["error"] = f"Unexpected execution error: {str(e)}"; return default_error_payload


    def convert_nl_to_sql(self, natural_language_query: str,
                          custom_schema_info: Optional[str] = None,
                          custom_few_shot_examples: Optional[List[Dict[str, Any]]] = None,
                          page_number: int = 1, page_size: Optional[int] = None
                         ) -> Dict[str, Any]:
        self._log(f"Starting NL-to-SQL conversion for query: '{natural_language_query[:100]}...'", "info")

        original_schema_context, retrieved_tables_for_context = self._retrieve_schema_context_for_query(natural_language_query)
        if custom_schema_info:
            self._log("Using provided custom_schema_info; RAG context will be ignored if custom_schema_info is preferred.", "info")
            original_schema_context = custom_schema_info
            retrieved_tables_for_context = [] # Cannot infer from opaque custom schema string

        if original_schema_context.startswith("-- Schema") or original_schema_context.startswith("-- Error"):
            self._log(f"Critical: Schema context not obtained: {original_schema_context}", "error")
            return {"sql_query": None, "error_message": original_schema_context, "confidence_score": 0.0,
                    "llm_reasoning": None, "tables_used": [], "prompt_used": None,
                    "query_results": {"data": None, "error": original_schema_context, "row_count":0, "page_number":page_number, "page_size":0}}

        original_few_shots = self._get_relevant_few_shots(natural_language_query, custom_few_shot_examples)

        processed_output: Dict[str, Any] = {}
        last_error_message: Optional[str] = None
        last_generated_sql: Optional[str] = None

        final_attempt_num = 0

        for attempt in range(self.config.max_correction_attempts + 1):
            final_attempt_num = attempt + 1
            self._log(f"NL-to-SQL attempt {final_attempt_num}/{self.config.max_correction_attempts + 1}", "info")

            current_prompt: Optional[str]
            if attempt == 0:
                current_prompt = self._construct_llm_prompt(
                    natural_language_query, original_schema_context, original_few_shots
                )
            else:
                if not last_generated_sql or not last_error_message:
                    self._log("Cannot attempt correction: missing last generated SQL or error message.", "error")
                    if not processed_output: # Should not happen if loop continued
                        processed_output = {"error_message": "Correction failed due to missing prior state.", "confidence_score": 0.0}
                    break
                current_prompt = self._construct_llm_prompt(
                    natural_language_query, original_schema_context, original_few_shots,
                    is_correction=True, previous_sql=last_generated_sql, previous_error=last_error_message
                )

            if not current_prompt:
                self._log("LLM prompt construction failed.", "error")
                processed_output = {"error_message": "LLM prompt construction failed.", "confidence_score": 0.0}
                break

            raw_llm_response = self._invoke_llm(current_prompt)
            processed_output = self._process_llm_output(raw_llm_response, retrieved_tables_for_context)
            processed_output["prompt_used"] = current_prompt # Store prompt for this attempt

            current_sql_query = processed_output.get('sql_query')
            current_confidence = processed_output.get('confidence_score') # From _process_llm_output
            current_error = processed_output.get('error_message')

            last_generated_sql = current_sql_query
            last_error_message = current_error

            # If initial processing already found a critical issue (no response, LLM error, disallowed keyword, bad extraction)
            if current_sql_query is None or current_error:
                self._log(f"Attempt {final_attempt_num} failed: SQL is None or error exists after _process_llm_output. Error: '{current_error}'", "warning")
                # Confidence score is already set by _process_llm_output for these cases (e.g., 0.0, 0.05, 0.1, 0.2)
                if self.config.error_string_for_no_conversion in str(current_error) or attempt == self.config.max_correction_attempts:
                    break # Stop if LLM gives up or max attempts reached
                continue # Try to correct

            # Syntax Validation
            is_syntax_valid, syntax_error_msg = self._validate_sql_syntax(current_sql_query)
            if not is_syntax_valid:
                self._log(f"Syntax validation failed (attempt {final_attempt_num}): {syntax_error_msg}", "warning")
                last_error_message = f"Syntax Error: {syntax_error_msg}"
                processed_output["error_message"] = last_error_message
                processed_output["confidence_score"] = 0.1
                if attempt == self.config.max_correction_attempts: break
                continue
            self._log(f"Syntax validation passed (attempt {final_attempt_num}).", "info")

            # Semantic Validation
            is_semantic_valid, semantic_error_msg = self._validate_sql_semantically(current_sql_query)
            if not is_semantic_valid:
                self._log(f"Semantic validation failed (attempt {final_attempt_num}): {semantic_error_msg}", "warning")
                last_error_message = f"Semantic Error: {semantic_error_msg}"
                processed_output["error_message"] = last_error_message
                processed_output["confidence_score"] = 0.2
                if attempt == self.config.max_correction_attempts: break
                continue

            self._log(f"Semantic validation passed (attempt {final_attempt_num}).", "info")
            processed_output["error_message"] = None # Clear any minor prior errors if all validations pass
            # Refined confidence scoring for successful validation
            if attempt == 0:
                processed_output["confidence_score"] = 0.9 # High confidence for first-time success
            else:
                # Gradually decrease confidence for corrected queries, with a floor
                processed_output["confidence_score"] = max(0.4, 0.8 - (0.1 * attempt))
            self._log(f"SQL query validated successfully (attempt {final_attempt_num}). Confidence: {processed_output['confidence_score']}", "info")
            break # Exit loop on successful validation

        # Final check on confidence if loop finished due to errors
        if processed_output.get("error_message") and (processed_output.get("confidence_score", 0.0) > 0.3 or processed_output.get("confidence_score") is None) :
            # If there's an error but confidence is still high (e.g. default 0.7 from extraction) or None, force it low.
            # This ensures errors correctly reflect low confidence.
            if "Syntax Error" in processed_output["error_message"]: processed_output["confidence_score"] = 0.1
            elif "Semantic Error" in processed_output["error_message"]: processed_output["confidence_score"] = 0.2
            else: processed_output["confidence_score"] = 0.0 # General error or complete failure
            self._log(f"Adjusted confidence score due to error after loop: {processed_output['confidence_score']}", "debug")


        if processed_output.get('sql_query') and not processed_output.get('error_message'):
            query_execution_result = self._execute_final_sql(processed_output['sql_query'], page_number, page_size)
            processed_output['query_results'] = query_execution_result
            if query_execution_result.get("error"):
                self._log(f"SQL execution failed: {query_execution_result['error']}", "warning")
                processed_output['execution_error_message'] = query_execution_result['error']
        else:
            self._log("No valid SQL query to execute after all attempts.", "warning")
            processed_output['query_results'] = {"data": None,
                                                 "error": processed_output.get('error_message', "SQL query not validated or generated."),
                                                 "row_count":0, "page_number":page_number, "page_size":0}

        # Ensure all expected keys are in processed_output before returning
        for key in ["sql_query", "confidence_score", "llm_reasoning", "tables_used", "error_message", "prompt_used", "query_results"]:
            processed_output.setdefault(key, None if key != "tables_used" else [])
            if key == "query_results" and processed_output.get(key) is None:
                processed_output[key] = {"data": None, "error": "Execution not attempted.", "row_count":0, "page_number":page_number, "page_size":0}


        self._log(f"NL-to-SQL conversion process finished. Final SQL: {processed_output.get('sql_query', 'No SQL')}, Confidence: {processed_output.get('confidence_score')}", "info")
        return processed_output


if __name__ == '__main__':
    # (Updated __main__ block for testing data retrieval)
    print("--- Testing NLToSQLProcessor with Data Retrieval ---")
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    # ... (setup for test_dir, dummy files, env vars as before) ...
    test_dir = "temp_test_nl_processor_exec_files"
    os.makedirs(test_dir, exist_ok=True)
    dummy_examples_path = os.path.join(test_dir, "dummy_examples_exec.json")
    dummy_prompt_path = os.path.join(test_dir, "dummy_base_prompt_exec.txt")
    dummy_chroma_path = os.path.join(test_dir, "dummy_chroma_exec") # Separate chroma for this test

    try:
        with open(dummy_examples_path, 'w') as f: json.dump([], f)
        with open(dummy_prompt_path, 'w') as f: f.write("Schema:\n{schema}\nQ: {user_question}\nEx:\n{examples}\nSQL for {dialect}:")

        # Set environment variables
        os.environ["NLSQL_FEW_SHOT_PATH"] = dummy_examples_path
        os.environ["NLSQL_PROMPT_TEMPLATE_PATH"] = dummy_prompt_path
        os.environ["NLSQL_USE_DYNAMIC_SCHEMA"] = "True"
        os.environ["NLSQL_LOG_LEVEL"] = "DEBUG"
        os.environ["NLSQL_CHROMA_PATH"] = dummy_chroma_path
        os.environ["NLSQL_CHROMA_COLLECTION"] = "test_exec_collection"
        os.environ["NLSQL_SCHEMA_EMBEDDING_MODEL"] = "all-MiniLM-L6-v2"
        # Database connection details (replace with your actual test DB if running this part live)
        os.environ["NLSQL_DB_HOST"] = os.getenv("TEST_DB_HOST", "localhost")
        os.environ["NLSQL_DB_PORT"] = os.getenv("TEST_DB_PORT", "5432")
        os.environ["NLSQL_DB_USER"] = os.getenv("TEST_DB_USER", "postgres")
        os.environ["NLSQL_DB_PASSWORD"] = os.getenv("TEST_DB_PASSWORD", "password")
        os.environ["NLSQL_DB_NAME"] = os.getenv("TEST_DB_NAME", "smart_factory_db") # Test DB
        os.environ["NLSQL_DB_TYPE"] = "postgresql"
        if not os.getenv("NLSQL_LLM_MODEL_NAME"): os.environ["NLSQL_LLM_MODEL_NAME"] = "mistral"
        if not os.getenv("NLSQL_LLM_BASE_URL"): os.environ["NLSQL_LLM_BASE_URL"] = "http://localhost:11434"
        os.environ["NLSQL_MAX_CORRECTION_ATTEMPTS"] = "1"


        config = NLToSQLConfig.load()
        processor = NLToSQLProcessor(config=config)

        nl_query = "show me all equipment"

        if processor.llm:
            # Mock LLM to return a query that will pass syntax and semantic checks (if DB is up)
            # or use custom_schema_info to avoid DB dependency for semantic check in this test.
            valid_sql_for_schema = "SELECT machine_id, machine_name FROM equipment" # Assuming 'equipment' table
            custom_schema = "CREATE TABLE equipment (machine_id TEXT, machine_name TEXT);"

            # Test 1: Successful first attempt
            with patch.object(processor, '_invoke_llm', return_value=f"```sql\n{valid_sql_for_schema}\n```") as mock_llm_valid:
                 # Mock semantic validation to pass if DBSchemaHandler is not fully set up for testing
                with patch.object(processor, '_validate_sql_semantically', return_value=(True, None)) as mock_semantic_valid:
                    print(f"\n--- Converting NL Query (expecting 1st attempt success): '{nl_query}' ---")
                    result = processor.convert_nl_to_sql(natural_language_query=nl_query, custom_schema_info=custom_schema)
                    print(f"  SQL Query: {result.get('sql_query')}")
                    print(f"  Confidence: {result.get('confidence_score')}")
                    print(f"  Error: {result.get('error_message')}")
                    assert result.get('sql_query') == valid_sql_for_schema
                    assert result.get('confidence_score') == 0.9
                    assert result.get('error_message') is None
                    mock_llm_valid.assert_called_once()


            # Test 2: Correction loop (syntax error then success)
            llm_responses_correction = [
                "SELECT FROM equipment", # Syntax error
                f"```sql\n{valid_sql_for_schema};\n```"  # Corrected (with semicolon to test cleaning)
            ]
            with patch.object(processor, '_invoke_llm', side_effect=llm_responses_correction) as mock_llm_correction:
                with patch.object(processor, '_validate_sql_semantically', return_value=(True, None)) as mock_semantic_valid_corr:
                    print(f"\n--- Converting NL Query (testing 1 correction): '{nl_query}' ---")
                    result_corr = processor.convert_nl_to_sql(natural_language_query=nl_query, custom_schema_info=custom_schema)
                    print(f"  SQL Query: {result_corr.get('sql_query')}")
                    print(f"  Confidence: {result_corr.get('confidence_score')}")
                    print(f"  Error: {result_corr.get('error_message')}")
                    assert result_corr.get('sql_query') == valid_sql_for_schema # Semicolon should be removed
                    assert result_corr.get('confidence_score') == 0.7 # 0.8 - 0.1 * 1 attempt
                    assert result_corr.get('error_message') is None
                    assert mock_llm_correction.call_count == 2
        else:
            print("LLM not available, skipping refinement tests.")

    except Exception as e:
        print(f"Error during test: {e}", file=sys.stderr)
        import traceback; traceback.print_exc()
    finally:
        if os.path.exists(dummy_examples_path): os.remove(dummy_examples_path)
        if os.path.exists(dummy_prompt_path): os.remove(dummy_prompt_path)
        if os.path.exists(dummy_chroma_path):
            import shutil; shutil.rmtree(dummy_chroma_path)
        if os.path.exists(test_dir):
            import shutil; shutil.rmtree(test_dir)
        print("\nCleaned up dummy files and test directory.")

```
