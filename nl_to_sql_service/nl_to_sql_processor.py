# nl_to_sql_service/nl_to_sql_processor.py
import os
import logging
import re # For SQL extraction
from typing import Dict, Any, Optional, List, Tuple

from .config_manager import NLToSQLConfig
from .few_shot_manager import FewShotManager
from .db_schema_handler import DBSchemaHandler

# Attempt to import ChatOllama and HumanMessage
try:
    from langchain_community.chat_models import ChatOllama
    from langchain_core.messages import HumanMessage
    CHAT_OLLAMA_AVAILABLE = True
except ImportError:
    ChatOllama = None # type: ignore
    HumanMessage = None # type: ignore
    CHAT_OLLAMA_AVAILABLE = False

def load_prompt_template(filepath: str, logger: logging.Logger) -> Optional[str]:
    """Loads a prompt template from a file."""
    if not os.path.isabs(filepath):
        logger.debug(f"Prompt template filepath '{filepath}' is not absolute. Assuming it's resolvable.")

    if not os.path.exists(filepath):
        logger.error(f"Prompt template file not found: {filepath}")
        return None
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        logger.error(f"Error loading prompt template file {filepath}: {e}")
        return None

class NLToSQLProcessor:
    """
    Processes natural language queries to generate SQL queries using an LLM,
    database schema information, and few-shot examples.
    """

    def __init__(self, config: NLToSQLConfig):
        """Initializes the NLToSQLProcessor."""
        self.config = config
        self.logger = logging.getLogger(__name__)
        self._configure_logger()

        self._log(f"Initializing NLToSQLProcessor with config: {config.model_dump_json(indent=2, exclude={'llm': {'api_key'}, 'db_schema_handler': {'password'}})}", "info")

        self.few_shot_manager = FewShotManager(
            examples_filepath=config.few_shot_examples_path,
            embedding_model_name=config.few_shot_embedding_model,
            logger=self.logger
        )

        self.schema_handler: Optional[DBSchemaHandler] = None
        if config.use_dynamic_schema_handling and config.db_schema_handler:
            db_handler_config_dict = config.db_schema_handler.model_dump()
            if db_handler_config_dict.get("host") or db_handler_config_dict.get("connection_string"):
                self.schema_handler = DBSchemaHandler(
                    db_config=db_handler_config_dict,
                    logger=self.logger,
                    cache_ttl_seconds=config.db_schema_handler.schema_cache_ttl_seconds
                )
                self._log("DBSchemaHandler initialized.", "info")
            else:
                self._log("DBSchemaHandler not initialized: Host or connection string missing.", "warning")
        else:
            self._log("Dynamic schema handling disabled or DB config missing.", "info")

        self.llm: Optional[ChatOllama] = None
        if CHAT_OLLAMA_AVAILABLE and ChatOllama is not None: # Explicit None check for type safety
            try:
                self.llm = ChatOllama(
                    model=config.llm.model_name,
                    base_url=config.llm.base_url,
                    temperature=config.llm.temperature
                )
                self._log(f"ChatOllama LLM initialized: model={config.llm.model_name}", "info")
            except Exception as e:
                self._log(f"Error initializing ChatOllama: {e}. LLM unavailable.", "error", exc_info=True)
        else:
            self._log("ChatOllama not available. LLM couldn't be initialized.", "error")

        self.base_prompt_template: Optional[str] = load_prompt_template(config.base_prompt_template_path, self.logger)
        if not self.base_prompt_template:
            self._log(f"Base prompt template failed to load from {config.base_prompt_template_path}.", "error")

    def _configure_logger(self):
        log_level_str = self.config.log_level.upper()
        numeric_level = getattr(logging, log_level_str, logging.INFO)
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
        self.logger.setLevel(numeric_level)

    def _log(self, message: str, level: str = "info", exc_info: bool = False):
        if level.lower() == "debug": self.logger.debug(message)
        elif level.lower() == "info": self.logger.info(message)
        elif level.lower() == "warning": self.logger.warning(message)
        elif level.lower() == "error": self.logger.error(message, exc_info=exc_info)
        elif level.lower() == "critical": self.logger.critical(message, exc_info=exc_info)

    def _select_relevant_tables(self, natural_language_query: str,
                                custom_schema_info: Optional[str] = None
                               ) -> Optional[List[str]]:
        """Selects relevant tables. Placeholder: uses all if schema handler available."""
        self._log(f"Selecting relevant tables for query: '{natural_language_query[:50]}...'", "debug")
        if custom_schema_info:
            self._log("Custom schema provided; table selection relies on full custom schema.", "info")
            return None

        if self.schema_handler:
            # For now, we don't implement dynamic table selection from schema_handler here.
            # It will fetch all tables based on schema_handler's get_schema_representation(table_names=None)
            # A more advanced version would list all tables and then filter.
            self._log("Using DBSchemaHandler. Defaulting to all tables specified by schema mode.", "info")
            return None # Let _get_schema_for_prompt handle fetching all tables via schema_handler

        self._log("No custom schema and no DBSchemaHandler. Cannot select tables.", "warning")
        return [] # Return empty list if no tables can be determined


    def _get_schema_for_prompt(self, selected_tables: Optional[List[str]],
                               custom_schema_info: Optional[str]) -> str:
        if custom_schema_info:
            self._log("Using provided custom schema information.", "info")
            return custom_schema_info

        if self.schema_handler:
            self._log(f"Fetching schema from DBSchemaHandler for tables: {selected_tables or 'all'}", "info")
            schema_repr = self.schema_handler.get_schema_representation(
                table_names=selected_tables, # If None, schema_handler gets all for its default schema
                mode=self.config.schema_representation_mode
            )
            if isinstance(schema_repr, str): return schema_repr
            elif isinstance(schema_repr, list): return "\n".join(schema_repr)
            self._log(f"Unexpected schema format from DBSchemaHandler: {type(schema_repr)}", "warning")
            return "-- Error: Unexpected schema format --"

        self._log("DBSchemaHandler not available and no custom schema. Returning placeholder.", "warning")
        return "-- Schema information not available --"

    def _get_relevant_few_shots(self, natural_language_query: str,
                                custom_few_shot_examples: Optional[List[Dict[str, Any]]]
                               ) -> List[Dict[str, Any]]:
        if custom_few_shot_examples is not None:
            self._log(f"Using {len(custom_few_shot_examples)} provided custom few-shot examples.", "info")
            return custom_few_shot_examples

        if self.few_shot_manager:
            self._log("Retrieving few-shot examples via FewShotManager.", "info")
            return self.few_shot_manager.get_relevant_examples(
                natural_language_query,
                n_examples=self.config.num_few_shot_examples_to_select,
                selection_strategy=self.config.few_shot_selection_strategy
            )
        self._log("FewShotManager not available and no custom examples. No few-shots used.", "warning")
        return []

    def _construct_llm_prompt(self, natural_language_query: str,
                              schema_representation: str,
                              relevant_few_shots: List[Dict[str, Any]]
                             ) -> Optional[str]:
        if not self.base_prompt_template:
            self._log("Base prompt template not loaded. Cannot construct prompt.", "error")
            return None
        formatted_examples = self.few_shot_manager.format_examples_for_prompt(relevant_few_shots)
        dialect = self.config.db_schema_handler.db_type if self.config.db_schema_handler else "SQL"
        try:
            prompt = self.base_prompt_template.format(
                schema=schema_representation, user_question=natural_language_query,
                examples=formatted_examples or "# No few-shot examples provided.", dialect=dialect
            )
            self._log("LLM prompt constructed.", "debug")
            return prompt
        except KeyError as e:
            self._log(f"Error formatting prompt. Missing key: {e}. Check template.", "error", exc_info=True)
            return None
        except Exception as e:
            self._log(f"Unexpected error during prompt construction: {e}", "error", exc_info=True)
            return None

    def _invoke_llm(self, full_prompt: str) -> Optional[str]:
        """Invokes the LLM with the provided prompt and returns the raw response string."""
        if not self.llm:
            self._log("LLM not initialized. Cannot invoke.", "error")
            return None
        if not HumanMessage : # Should not happen if CHAT_OLLAMA_AVAILABLE is true
            self._log("HumanMessage not available for LLM invocation.", "error")
            return None

        self._log(f"Invoking LLM. Prompt (first 200 chars): {full_prompt[:200]}...", "info")
        try:
            # For ChatOllama, wrap string prompt in HumanMessage
            message = HumanMessage(content=full_prompt)
            response = self.llm.invoke([message]) # Invoke expects a list of messages
            llm_response_content = response.content
            if not isinstance(llm_response_content, str):
                 # Should be string, but defensive check
                llm_response_content = str(llm_response_content)
            self._log(f"LLM raw response (first 200 chars): {llm_response_content[:200]}...", "debug")
            return llm_response_content
        except Exception as e:
            self._log(f"Error invoking LLM: {e}", "error", exc_info=True)
            return None

    def _process_llm_output(self, llm_raw_response: Optional[str],
                            selected_tables: Optional[List[str]]
                           ) -> Dict[str, Any]:
        """Processes the raw LLM output to extract SQL and other metadata."""
        output: Dict[str, Any] = {
            "sql_query": None, "confidence_score": None, "llm_reasoning": None,
            "tables_used": selected_tables if selected_tables else [], # Default to selected, can be refined
            "error_message": None
        }
        if not llm_raw_response:
            output["error_message"] = "LLM returned no response."
            self._log(output["error_message"], "warning")
            return output

        # Attempt to extract SQL query (e.g., from ```sql ... ``` block)
        sql_query = llm_raw_response
        match = re.search(r"```sql\s*(.*?)\s*```", llm_raw_response, re.DOTALL | re.IGNORECASE)
        if match:
            sql_query = match.group(1).strip()
            # Potential reasoning might be outside the SQL block
            # For now, we don't explicitly capture it unless prompted for and formatted.
        else: # Assume the whole response might be SQL if no backticks
            sql_query = llm_raw_response.strip()

        # Basic cleaning: remove trailing semicolon (assuming config option, default True)
        # remove_trailing_semicolon = getattr(self.config, 'remove_trailing_semicolon', True)
        remove_trailing_semicolon = True # Hardcoded for now as per instruction
        if remove_trailing_semicolon and sql_query.endswith(';'):
            sql_query = sql_query[:-1].strip()

        output["sql_query"] = sql_query

        # Security check for disallowed keywords
        if self.config.disallowed_sql_keywords and sql_query:
            query_upper = sql_query.upper()
            for keyword in self.config.disallowed_sql_keywords:
                # Use word boundaries to avoid matching substrings
                if re.search(r"\b" + re.escape(keyword) + r"\b", query_upper):
                    error_msg = f"Disallowed SQL keyword '{keyword}' found in generated query."
                    self._log(error_msg, "error")
                    output["error_message"] = error_msg
                    output["sql_query"] = None # Invalidate query
                    break

        # Placeholder for confidence and reasoning (not implemented yet)
        output["confidence_score"] = 0.5 # Default placeholder
        # output["llm_reasoning"] = "LLM reasoning placeholder..."

        self._log(f"Processed SQL query: {output['sql_query'][:100] if output['sql_query'] else 'None'}", "info")
        return output

    def convert_nl_to_sql(self, natural_language_query: str,
                          custom_schema_info: Optional[str] = None,
                          custom_few_shot_examples: Optional[List[Dict[str, Any]]] = None,
                          # session_context: Optional[Dict[str, Any]] = None # Placeholder for future context
                         ) -> Dict[str, Any]:
        """
        Converts a natural language query to SQL.

        Orchestrates the process of schema retrieval, few-shot example selection,
        prompt construction, LLM invocation, and output processing.

        Args:
            natural_language_query (str): The user's natural language query.
            custom_schema_info (Optional[str]): A string containing pre-defined schema
                information to be used instead of dynamic schema fetching.
            custom_few_shot_examples (Optional[List[Dict[str, Any]]]): A list of
                few-shot examples to use instead of those from the FewShotManager.
            # session_context (Optional[Dict[str, Any]]): Additional context from the
            #                                            user's session (e.g., previous turns).

        Returns:
            Dict[str, Any]: A dictionary containing the generated SQL query,
                            confidence score, LLM reasoning (if available), tables used,
                            and any error messages.
        """
        self._log(f"Starting NL-to-SQL conversion for query: '{natural_language_query[:100]}...'", "info")

        # 1. Select relevant tables (if dynamic schema handling is used)
        #    This step needs more robust implementation if we are to dynamically select tables.
        #    For now, _select_relevant_tables might return None, meaning _get_schema_for_prompt
        #    will fetch schema for all tables if not using custom_schema_info.
        selected_tables: Optional[List[str]] = None
        if self.config.use_dynamic_schema_handling and self.schema_handler and not custom_schema_info:
             # In a more advanced scenario, schema_handler would provide a list of all tables
             # and _select_relevant_tables would filter them.
             # For now, if selected_tables is None, schema_handler.get_schema_representation
             # gets all tables.
             # all_tables = self.schema_handler._get_all_tables_and_views() # Example of getting table list
             # selected_tables = self._select_relevant_tables(natural_language_query, None, all_tables)
             selected_tables = self._select_relevant_tables(natural_language_query, None, None) # Basic version
        elif custom_schema_info :
             selected_tables = self._select_relevant_tables(natural_language_query, custom_schema_info, None)


        # 2. Get schema representation
        schema_representation = self._get_schema_for_prompt(selected_tables, custom_schema_info)
        if "-- Schema information not available --" in schema_representation or \
           "-- Error: Unexpected schema format --" in schema_representation:
            self._log("Critical: Schema could not be obtained for prompt construction.", "error")
            # Fallback or error response
            return {
                "sql_query": None, "error_message": "Schema information is unavailable.",
                "confidence_score": 0.0, "llm_reasoning": None, "tables_used": []
            }

        # 3. Get few-shot examples
        few_shots = self._get_relevant_few_shots(natural_language_query, custom_few_shot_examples)

        # 4. Construct prompt
        llm_prompt = self._construct_llm_prompt(natural_language_query, schema_representation, few_shots)

        if not llm_prompt:
            self._log("LLM prompt construction failed.", "error")
            return {
                "sql_query": None, "error_message": "LLM prompt construction failed.",
                "confidence_score": 0.0, "llm_reasoning": None, "tables_used": selected_tables or []
            }

        # 5. Invoke LLM
        raw_llm_response = self._invoke_llm(llm_prompt)

        # 6. Process LLM output
        processed_output = self._process_llm_output(raw_llm_response, selected_tables)

        # Add the prompt used to the output for debugging purposes
        processed_output["prompt_used"] = llm_prompt

        self._log(f"NL-to-SQL conversion complete. Result: {processed_output.get('sql_query', 'Error')}", "info")
        return processed_output


if __name__ == '__main__':
    print("--- Testing NLToSQLProcessor Full Flow (Basic) ---")
    try:
        dummy_examples_path = "dummy_examples_for_processor_full.json"
        with open(dummy_examples_path, 'w') as f:
            json.dump([{"id": "test_full", "nl_query": "show all equipment", "sql_query": "SELECT * FROM equipment;"}], f)

        dummy_prompt_path = "dummy_base_prompt_full.txt"
        with open(dummy_prompt_path, 'w') as f:
            f.write("Schema: {schema}\nQuestion: {user_question}\nExamples: {examples}\nDialect: {dialect}\nSQL:")

        os.environ["NLSQL_FEW_SHOT_PATH"] = dummy_examples_path
        os.environ["NLSQL_PROMPT_TEMPLATE_PATH"] = dummy_prompt_path
        os.environ["NLSQL_USE_DYNAMIC_SCHEMA"] = "False"
        # To test with schema_handler, set NLSQL_USE_DYNAMIC_SCHEMA="True" and configure DB env vars
        # e.g., NLSQL_DB_HOST, NLSQL_DB_PORT, etc.

        config = NLToSQLConfig.load()
        processor = NLToSQLProcessor(config=config)

        nl_query = "List all active alarms for machine EQP-005."

        # Test with custom schema if DB handler is not active
        custom_schema_for_test = """
        CREATE TABLE equipment (machine_id VARCHAR(50) PRIMARY KEY, status VARCHAR(20));
        CREATE TABLE alarms (alarm_id INT PRIMARY KEY, machine_id VARCHAR(50), alarm_description TEXT, timestamp TIMESTAMP);
        """

        result = processor.convert_nl_to_sql(
            natural_language_query=nl_query,
            custom_schema_info=custom_schema_for_test if not processor.schema_handler else None
        )

        print("\n--- NL-to-SQL Result ---")
        print(f"  NL Query: {nl_query}")
        print(f"  SQL Query: {result.get('sql_query')}")
        print(f"  Error: {result.get('error_message')}")
        print(f"  Tables Used (expected): {result.get('tables_used')}") # Based on simple selection
        # print(f"  Prompt Used (snippet): {result.get('prompt_used', '')[:300]}...")


        # Example with no custom schema, relying on (mocked/non-functional) DBSchemaHandler
        if not processor.config.use_dynamic_schema_handling or not processor.schema_handler :
             print("\n--- Testing without dynamic schema (should use placeholder schema) ---")
             result_no_schema = processor.convert_nl_to_sql(natural_language_query="Show me something.")
             print(f"  SQL Query (no schema): {result_no_schema.get('sql_query')}")
             print(f"  Error (no schema): {result_no_schema.get('error_message')}")


        os.remove(dummy_examples_path)
        os.remove(dummy_prompt_path)

    except Exception as e:
        print(f"Error during NLToSQLProcessor full flow test: {e}")
        if os.path.exists("dummy_examples_for_processor_full.json"): os.remove("dummy_examples_for_processor_full.json")
        if os.path.exists("dummy_base_prompt_full.txt"): os.remove("dummy_base_prompt_full.txt")

```
