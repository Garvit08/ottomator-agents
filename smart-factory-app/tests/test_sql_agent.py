import unittest
import sys
import os
from unittest.mock import patch, MagicMock

# --- Path Adjustments ---
# Add the parent directory of 'smart-factory-app' to sys.path
# This allows `from smart_factory_app.agents...` imports
current_test_dir = os.path.dirname(os.path.abspath(__file__)) # .../tests
smart_factory_app_dir = os.path.abspath(os.path.join(current_test_dir, '..')) # .../smart-factory-app
project_root = os.path.abspath(os.path.join(smart_factory_app_dir, '..')) # Parent of .../smart-factory-app

if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Now we can import the module to be tested
from smart_factory_app.agents import sql_agent

class TestSQLAgent(unittest.TestCase):

    @patch('smart_factory_app.agents.sql_agent.create_engine') # Mock at the source
    @patch('smart_factory_app.agents.sql_agent.OpenAI') # Mock the LLM
    @patch('smart_factory_app.agents.sql_agent.SQLDatabase')
    @patch('smart_factory_app.agents.sql_agent.SQLDatabaseToolkit')
    @patch('smart_factory_app.agents.sql_agent.create_sql_agent')
    def test_agent_initialization_and_query(self, 
                                             mock_create_sql_agent, 
                                             mock_SQLDatabaseToolkit, 
                                             mock_SQLDatabase, 
                                             mock_OpenAI, 
                                             mock_create_engine):
        """
        Test that the SQL agent components are initialized and run_sql_query uses the agent.
        This is a high-level test.
        """
        # Configure mocks
        mock_engine_instance = MagicMock()
        mock_create_engine.return_value = mock_engine_instance

        mock_llm_instance = MagicMock()
        mock_OpenAI.return_value = mock_llm_instance
        
        # Ensure the global `llm` in sql_agent is this mock instance for the test duration
        # This requires careful patching if the module has already been loaded and `llm` set.
        # A more robust way is to ensure sql_agent.llm can be set or is re-evaluated.
        # For this structure, we rely on sql_agent being imported fresh or using patch.object.
        
        # If sql_agent.llm is initialized at module level, we need to patch it directly
        # after it's set, or ensure it's re-initialized.
        # Let's assume the current structure in sql_agent.py where `llm` is a global variable.
        # If OPENAI_API_KEY is not set, sql_agent.llm will be None.
        # We will mock os.getenv for OPENAI_API_KEY to ensure llm is attempted to be created.

        mock_agent_executor_instance = MagicMock()
        mock_agent_executor_instance.run.return_value = "Mocked SQL query result"
        mock_create_sql_agent.return_value = mock_agent_executor_instance

        # Temporarily set OPENAI_API_KEY for this test if sql_agent.llm depends on it for init
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test_key"}):
            # Re-import or reload sql_agent if its globals are set on first import and don't see patches.
            # Or, if sql_agent is structured as a class, instantiate it.
            # Given sql_agent.py's current structure (globals and functions),
            # we need to ensure the mocks are in place when its top-level code runs.
            # The current sql_agent.py initializes agent_executor globally.
            # This makes direct testing of run_sql_query difficult without refactoring sql_agent.py
            # to initialize agent_executor within a function or class.
            
            # For now, let's assume we can test run_sql_query by directly mocking the agent_executor it uses.
            # We need to patch 'sql_agent.agent_executor' which is tricky if it's initialized at import.
            # A common pattern is to have an init function for the agent.
            
            # Let's try to directly patch the global agent_executor in the sql_agent module
            # This is a bit of a hack due to the current structure of sql_agent.py
            if hasattr(sql_agent, 'agent_executor'):
                 original_agent_executor = sql_agent.agent_executor
                 sql_agent.agent_executor = mock_agent_executor_instance
            else: # If agent_executor was not created (e.g. LLM init failed in module)
                 sql_agent.agent_executor = mock_agent_executor_instance


            test_query = "List all tables."
            result = sql_agent.run_sql_query(test_query)

            self.assertEqual(result, "Mocked SQL query result")
            mock_agent_executor_instance.run.assert_called_once_with(test_query)
            
            # Restore original agent_executor if it existed
            if 'original_agent_executor' in locals():
                sql_agent.agent_executor = original_agent_executor


    def test_run_sql_query_agent_not_initialized(self):
        """Test run_sql_query when agent_executor is None."""
        original_agent_executor = sql_agent.agent_executor
        sql_agent.agent_executor = None # Simulate agent not being initialized

        result = sql_agent.run_sql_query("Any query")
        self.assertEqual(result, "SQL Agent not initialized. Cannot run query.")

        sql_agent.agent_executor = original_agent_executor # Restore

    @patch('smart_factory_app.agents.sql_agent.agent_executor') # Mock the global agent_executor
    def test_run_sql_query_error_handling(self, mock_agent_executor_instance):
        """Test error handling in run_sql_query if agent.run() raises an exception."""
        mock_agent_executor_instance.run.side_effect = Exception("Database access error")

        test_query = "SELECT * FROM non_existent_table"
        result, examples_used = sql_agent.run_sql_query(test_query) # Unpack tuple

        self.assertTrue("Error running query: Database access error" in result)
        self.assertEqual(examples_used, []) # No examples should be listed on error before example processing

    @patch('smart_factory_app.agents.sql_agent.get_relevant_sql_examples')
    @patch('smart_factory_app.agents.sql_agent.agent_executor') # Mock the agent_executor
    def test_run_sql_query_with_parsed_dict_and_examples(self, mock_agent_executor, mock_get_examples):
        """Test run_sql_query with parsed_query_dict to include few-shot examples and table hints."""
        # Mock setup
        mock_agent_executor.run.return_value = "SQL result with examples"
        mock_parsed_query = {"intent": "get_daily_summary", "machine_id": "M001"}
        
        # Mock get_relevant_sql_examples to return controlled examples and tables
        mock_example_1 = {
            "id": "ex1", 
            "natural_language_equivalent": "User question for ex1", 
            "query_template": "SELECT * FROM table1 WHERE id = :id"
        }
        mock_example_2 = {
            "id": "ex2", 
            "natural_language_equivalent": "User question for ex2", 
            "query_template": "SELECT name FROM table2 WHERE category = :cat"
        }
        mock_suggested_tables = {"table1", "table2", "shift_data"}
        mock_get_examples.return_value = ([mock_example_1, mock_example_2], mock_suggested_tables)

        nl_query = "Get summary for M001"
        result, examples_used_ids = sql_agent.run_sql_query(nl_query, parsed_query_dict=mock_parsed_query)

        # Assertions
        self.assertEqual(result, "SQL result with examples")
        self.assertEqual(examples_used_ids, ["ex1", "ex2"])
        
        mock_get_examples.assert_called_once_with(mock_parsed_query, max_examples=2)
        
        # Verify the augmented query structure passed to agent_executor.run
        augmented_query_arg = mock_agent_executor.run.call_args[0][0]
        
        self.assertIn("User Question: User question for ex1", augmented_query_arg)
        self.assertIn("SQL Query:\nSELECT * FROM table1 WHERE id = :id", augmented_query_arg)
        self.assertIn("User Question: User question for ex2", augmented_query_arg)
        self.assertIn("SQL Query:\nSELECT name FROM table2 WHERE category = :cat", augmented_query_arg)
        self.assertIn("Hint: For the following question, consider using tables such as: shift_data, table1, table2.", augmented_query_arg) # Sorted order
        self.assertIn(f"Based on these examples and the database schema, please answer the following question by generating and executing SQL:\n{nl_query}", augmented_query_arg)

    @patch('smart_factory_app.agents.sql_agent.get_relevant_sql_examples')
    @patch('smart_factory_app.agents.sql_agent.agent_executor')
    def test_run_sql_query_no_relevant_examples(self, mock_agent_executor, mock_get_examples):
        """Test run_sql_query when no relevant examples or tables are found."""
        mock_agent_executor.run.return_value = "SQL result without examples"
        mock_parsed_query = {"intent": "some_other_intent"}
        mock_get_examples.return_value = ([], set()) # No examples, no tables

        nl_query = "A very unique query"
        result, examples_used_ids = sql_agent.run_sql_query(nl_query, parsed_query_dict=mock_parsed_query)

        self.assertEqual(result, "SQL result without examples")
        self.assertEqual(examples_used_ids, [])
        
        # The augmented query should not contain the few-shot header or table hint if none are found.
        # It should just be the instructional prefix + natural_language_query.
        augmented_query_arg = mock_agent_executor.run.call_args[0][0]
        # Check if the query is the original query or if it still has the base instruction.
        # The current implementation will still add the base instruction.
        self.assertIn(f"Based on these examples and the database schema, please answer the following question by generating and executing SQL:\n{nl_query}", augmented_query_arg)
        self.assertNotIn("User Question:", augmented_query_arg) # No examples
        self.assertNotIn("Hint: For the following question, consider using tables such as:", augmented_query_arg) # No table hints


if __name__ == '__main__':
    unittest.main()
