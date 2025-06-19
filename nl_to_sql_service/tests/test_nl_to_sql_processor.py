# nl_to_sql_service/tests/test_nl_to_sql_processor.py
import unittest
from unittest.mock import patch, MagicMock, call
import os
import json
import logging
import shutil # For cleaning up directories

# Adjust path to import from the nl_to_sql_service package
import sys
PACKAGE_PARENT = os.path.join(os.path.dirname(__file__), '..', '..')
sys.path.insert(0, os.path.normpath(PACKAGE_PARENT))

from nl_to_sql_service.nl_to_sql_processor import NLToSQLProcessor, DEFAULT_NL_TO_SQL_STOP_WORDS
from nl_to_sql_service.config_manager import NLToSQLConfig, LLMConfig, DBSchemaHandlerConfig
# FewShotManager, DBSchemaHandler, VectorStoreHandler will be mocked

# Mock external libraries globally for this test file
mock_sqlglot = MagicMock()
mock_sqlglot.errors = MagicMock()
mock_sqlglot.errors.ParseError = type('ParseError', (Exception,), {})

mock_chatollama = MagicMock()
mock_humanmessage = MagicMock()

# This mock needs to be sophisticated enough to handle .content attribute
mock_llm_instance = MagicMock()
mock_llm_response = MagicMock()
mock_llm_response.content = "SELECT * FROM mock_table;" # Default mock response
mock_llm_instance.invoke.return_value = mock_llm_response
mock_chatollama.ChatOllama.return_value = mock_llm_instance


@patch.dict('sys.modules', {
    'sqlglot': mock_sqlglot,
    'sqlglot.errors': mock_sqlglot.errors,
    'langchain_community.chat_models': mock_chatollama, # Corrected path for ChatOllama
    'langchain_core.messages': mock_humanmessage
})
@patch('nl_to_sql_service.nl_to_sql_processor.SQLGLOT_AVAILABLE', True) # Assume available for most tests
@patch('nl_to_sql_service.nl_to_sql_processor.CHAT_OLLAMA_AVAILABLE', True) # Assume available
class TestNLToSQLProcessor(unittest.TestCase):
    """
    Unit tests for the NLToSQLProcessor class.
    Dependencies like Config, LLM, Handlers are mocked.
    """
    test_dir = "temp_test_processor_files"
    dummy_examples_path = os.path.join(test_dir, "dummy_examples_for_processor.json")
    dummy_prompt_path = os.path.join(test_dir, "dummy_base_prompt_for_processor.txt")

    @classmethod
    def setUpClass(cls):
        os.makedirs(cls.test_dir, exist_ok=True)
        with open(cls.dummy_examples_path, 'w') as f:
            json.dump([{"id": "proc_ex1", "nl_query": "q1", "sql_query": "s1"}], f)
        with open(cls.dummy_prompt_path, 'w') as f:
            f.write("Schema: {schema}\nQ: {user_question}\nEx: {examples}\nDialect: {dialect}\nSQL:")
        logging.disable(logging.CRITICAL) # Disable logging during tests

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.test_dir):
            shutil.rmtree(cls.test_dir)
        logging.disable(logging.NOTSET)

    def setUp(self):
        """Set up for each test method."""
        self.mock_config = MagicMock(spec=NLToSQLConfig)
        self.mock_config.llm = MagicMock(spec=LLMConfig)
        self.mock_config.llm.model_name = "test_model"
        self.mock_config.llm.base_url = "http://testurl"
        self.mock_config.llm.temperature = 0.1

        self.mock_config.few_shot_examples_path = self.dummy_examples_path
        self.mock_config.num_few_shot_examples_to_select = 1
        self.mock_config.few_shot_selection_strategy = "random"
        self.mock_config.few_shot_embedding_model = "test_embed_model"

        self.mock_config.use_dynamic_schema_handling = True # Default to True for some tests
        self.mock_config.db_schema_handler = MagicMock(spec=DBSchemaHandlerConfig)
        self.mock_config.db_schema_handler.db_type = "postgres" # For sqlglot
        self.mock_config.db_schema_handler.default_schema_name = "public"
        self.mock_config.db_schema_handler.schema_cache_ttl_seconds = 3600


        self.mock_config.schema_representation_mode = "create_table"
        self.mock_config.base_prompt_template_path = self.dummy_prompt_path
        self.mock_config.log_level = "DEBUG"
        self.mock_config.disallowed_sql_keywords = ["DROP", "DELETE", "INSERT", "UPDATE"]
        self.mock_config.error_string_for_no_conversion = "ERROR_CANNOT_CONVERT"
        self.mock_config.remove_trailing_semicolon = True
        self.mock_config.num_schema_chunks_for_prompt = 3
        self.mock_config.max_correction_attempts = 1 # 1 attempt + 1 retry = 2 total

        # Mock handlers that NLToSQLProcessor would initialize internally if not passed
        self.mock_vector_store_handler_instance = MagicMock()
        self.mock_db_schema_handler_instance = MagicMock()

        # Patch the constructors of the handlers that NLToSQLProcessor might create
        self.patch_vsh = patch('nl_to_sql_service.nl_to_sql_processor.VectorStoreHandler', return_value=self.mock_vector_store_handler_instance)
        self.patch_dbsh = patch('nl_to_sql_service.nl_to_sql_processor.DBSchemaHandler', return_value=self.mock_db_schema_handler_instance)

        self.MockVectorStoreHandler = self.patch_vsh.start()
        self.MockDBSchemaHandler = self.patch_dbsh.start()

        # Reset ChatOllama mock for each test
        mock_chatollama.ChatOllama.reset_mock(return_value=True, side_effect=True) # Clear previous return_value
        mock_chatollama.ChatOllama.return_value = mock_llm_instance
        mock_llm_instance.invoke.reset_mock(return_value=True, side_effect=True)
        mock_llm_instance.invoke.return_value = mock_llm_response # Default successful response


    def tearDown(self):
        self.patch_vsh.stop()
        self.patch_dbsh.stop()

    def test_init_processor(self, MockChatOllamaAvailable, MockSqlglotAvailable):
        """Test successful initialization of NLToSQLProcessor."""
        processor = NLToSQLProcessor(config=self.mock_config)
        self.assertIsNotNone(processor.llm)
        self.assertIsNotNone(processor.few_shot_manager)
        self.assertIsNotNone(processor.vector_store_handler)
        # DBSchemaHandler is initialized only if host/conn_str is in its config part
        # For this test, let's assume it's not fully configured to be created in NLToSQLProcessor's init
        # self.assertIsNotNone(processor.db_schema_handler)
        self.assertIsNotNone(processor.base_prompt_template)

    def test_extract_keywords_simple(self, MockChatOllamaAvailable, MockSqlglotAvailable):
        processor = NLToSQLProcessor(config=self.mock_config)
        text = "Show me total sales for product X"
        expected = ["total", "sales", "product", "x"]
        self.assertCountEqual(processor._extract_keywords(text), expected)

    def test_retrieve_schema_context_for_query(self, MockChatOllamaAvailable, MockSqlglotAvailable):
        """Test schema retrieval using mocked VectorStoreHandler."""
        processor = NLToSQLProcessor(config=self.mock_config)

        mock_chunks = [
            {"text_content": "CREATE TABLE users (id INT, name TEXT)", "metadata": {"table_name": "users"}},
            {"text_content": "CREATE TABLE orders (id INT, user_id INT)", "metadata": {"table_name": "orders"}}
        ]
        self.mock_vector_store_handler_instance.retrieve_relevant_schema_chunks.return_value = mock_chunks

        context_str, table_names = processor._retrieve_schema_context_for_query("some query")

        self.assertIn("CREATE TABLE users", context_str)
        self.assertIn("CREATE TABLE orders", context_str)
        self.assertCountEqual(table_names, ["users", "orders"])
        self.mock_vector_store_handler_instance.retrieve_relevant_schema_chunks.assert_called_once()

    def test_process_llm_output_sql_extraction(self, MockChatOllamaAvailable, MockSqlglotAvailable):
        """Test various SQL extraction scenarios."""
        processor = NLToSQLProcessor(config=self.mock_config)

        # SQL in backticks
        raw_response_backticks = "Some text before ```sql\nSELECT * FROM test_table;\n``` and after."
        processed = processor._process_llm_output(raw_response_backticks)
        self.assertEqual(processed["sql_query"], "SELECT * FROM test_table")

        # SQL only
        raw_response_sql_only = "SELECT id FROM another_table WHERE condition;"
        processed = processor._process_llm_output(raw_response_sql_only)
        self.assertEqual(processed["sql_query"], "SELECT id FROM another_table WHERE condition")

        # SQL with conversational text
        raw_response_convo = "Sure, here is the SQL query: SELECT name FROM convo_table;"
        processed = processor._process_llm_output(raw_response_convo)
        self.assertEqual(processed["sql_query"], "SELECT name FROM convo_table")

        # LLM error string
        processed = processor._process_llm_output(self.mock_config.error_string_for_no_conversion)
        self.assertIsNone(processed["sql_query"])
        self.assertEqual(processed["error_message"], self.mock_config.error_string_for_no_conversion)
        self.assertEqual(processed["confidence_score"], 0.0)

        # Empty response
        processed = processor._process_llm_output("")
        self.assertIsNone(processed["sql_query"])
        self.assertEqual(processed["error_message"], "LLM returned no response or an empty response.")
        self.assertEqual(processed["confidence_score"], 0.0)

    def test_validate_sql_syntax_with_sqlglot(self, MockChatOllamaAvailable, MockSqlglotAvailable):
        """Test syntax validation using mocked sqlglot."""
        processor = NLToSQLProcessor(config=self.mock_config)

        # Valid SQL
        mock_sqlglot.parse_one.reset_mock(side_effect=None) # Clear any previous side_effect
        is_valid, error = processor._validate_sql_syntax("SELECT * FROM valid_table")
        self.assertTrue(is_valid)
        self.assertIsNone(error)

        # Invalid SQL
        mock_sqlglot.parse_one.side_effect = mock_sqlglot.errors.ParseError("Syntax error details")
        is_valid, error = processor._validate_sql_syntax("SELECT FROM invalid_syntax")
        self.assertFalse(is_valid)
        self.assertIn("SQLGlot ParseError: Syntax error details", error)

    def test_validate_sql_semantically_mocked_db(self, MockChatOllamaAvailable, MockSqlglotAvailable):
        """Test semantic validation using mocked DBSchemaHandler."""
        processor = NLToSQLProcessor(config=self.mock_config, db_schema_handler=self.mock_db_schema_handler_instance)

        # Simulate EXPLAIN success (returns empty list or list of plans)
        self.mock_db_schema_handler_instance._execute_query.return_value = []
        is_valid, error = processor._validate_sql_semantically("SELECT * FROM existing_table")
        self.assertTrue(is_valid)
        self.assertIsNone(error)
        self.mock_db_schema_handler_instance._execute_query.assert_called_with("EXPLAIN SELECT * FROM existing_table")

        # Simulate EXPLAIN failure (DB error, _execute_query returns None)
        self.mock_db_schema_handler_instance._execute_query.return_value = None
        is_valid, error = processor._validate_sql_semantically("SELECT * FROM non_existent_table")
        self.assertFalse(is_valid)
        self.assertIn("Semantic validation failed: EXPLAIN execution error", error)

    def test_execute_final_sql_pagination_and_select_only(self, MockChatOllamaAvailable, MockSqlglotAvailable):
        """Test _execute_final_sql for pagination and SELECT query enforcement."""
        self.mock_config.default_page_size = 10
        self.mock_config.max_page_size = 50
        processor = NLToSQLProcessor(config=self.mock_config, db_schema_handler=self.mock_db_schema_handler_instance)

        # Test SELECT query
        self.mock_db_schema_handler_instance._execute_query.return_value = [{"id":1}]
        result = processor._execute_final_sql("SELECT * FROM my_table", page_number=2, page_size=5)
        self.mock_db_schema_handler_instance._execute_query.assert_called_with("SELECT * FROM my_table LIMIT 5 OFFSET 5")
        self.assertEqual(result["row_count"], 1)
        self.assertEqual(result["page_number"], 2)
        self.assertEqual(result["page_size"], 5)

        # Test non-SELECT query
        result_non_select = processor._execute_final_sql("DROP TABLE my_table")
        self.assertIsNone(result_non_select["data"])
        self.assertIn("Only SELECT queries can be executed", result_non_select["error"])


    def test_convert_nl_to_sql_successful_first_attempt(self, MockChatOllamaAvailable, MockSqlglotAvailable):
        """Test the full convert_nl_to_sql flow for a successful first attempt."""
        # Mock dependencies
        self.mock_vector_store_handler_instance.retrieve_relevant_schema_chunks.return_value = ([
            {"text_content": "CREATE TABLE users (id INT, name TEXT)", "metadata": {"table_name": "users"}}
        ], ["users"])

        mock_llm_instance.invoke.return_value = MagicMock(content="SELECT id, name FROM users WHERE name = 'Alice';")

        mock_sqlglot.parse_one.reset_mock(side_effect=None) # Syntax valid
        self.mock_db_schema_handler_instance._execute_query.side_effect = [
            [], # For EXPLAIN (semantic validation success)
            [{"id": 1, "name": "Alice"}] # For actual data execution
        ]


        processor = NLToSQLProcessor(config=self.mock_config,
                                     vector_store_handler=self.mock_vector_store_handler_instance,
                                     db_schema_handler=self.mock_db_schema_handler_instance)

        result = processor.convert_nl_to_sql("Get Alice from users")

        self.assertEqual(result["sql_query"], "SELECT id, name FROM users WHERE name = 'Alice'")
        self.assertIsNone(result["error_message"])
        self.assertEqual(result["confidence_score"], 0.9) # Success on first attempt
        self.assertIsNotNone(result["query_results"])
        self.assertEqual(result["query_results"]["row_count"], 1)
        self.assertEqual(result["query_results"]["data"][0]["name"], "Alice")

    def test_convert_nl_to_sql_correction_loop_syntax_then_success(self, MockChatOllamaAvailable, MockSqlglotAvailable):
        """Test correction loop: syntax error on first try, success on second."""
        self.mock_vector_store_handler_instance.retrieve_relevant_schema_chunks.return_value = ([
            {"text_content": "CREATE TABLE products (pid INT, product_name TEXT)", "metadata": {"table_name": "products"}}
        ], ["products"])

        # LLM first returns bad SQL, then good SQL
        mock_llm_responses = [
            MagicMock(content="SELECT pid FROM products WHERE pid = "), # Syntax error
            MagicMock(content="SELECT pid FROM products WHERE pid = 101;") # Corrected
        ]
        mock_llm_instance.invoke.side_effect = mock_llm_responses

        # sqlglot: first call raises error, second call is fine
        mock_sqlglot.parse_one.side_effect = [SQLGlotParseError("Syntax error"), None]

        # DBSchemaHandler for EXPLAIN (called once for the valid SQL) and final execution
        self.mock_db_schema_handler_instance._execute_query.side_effect = [
            [], # EXPLAIN for the corrected query
            [{"pid": 101}] # Data for the corrected query
        ]

        processor = NLToSQLProcessor(config=self.mock_config,
                                     vector_store_handler=self.mock_vector_store_handler_instance,
                                     db_schema_handler=self.mock_db_schema_handler_instance)

        result = processor.convert_nl_to_sql("Get product 101")

        self.assertEqual(result["sql_query"], "SELECT pid FROM products WHERE pid = 101")
        self.assertIsNone(result["error_message"])
        self.assertAlmostEqual(result["confidence_score"], 0.7) # 0.8 - 0.1 * 1 attempt
        self.assertEqual(mock_llm_instance.invoke.call_count, 2) # Initial + 1 correction
        self.assertIsNotNone(result["query_results"])
        self.assertEqual(result["query_results"]["row_count"], 1)


if __name__ == '__main__':
    unittest.main()
