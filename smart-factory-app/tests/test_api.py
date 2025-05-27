import unittest
import sys
import os
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

# --- Path Adjustments ---
# This is to ensure that `from smart_factory_app.api.main import app` works
# and that `app` can in turn find its own dependencies like `agents` and `config`.
current_test_dir = os.path.dirname(os.path.abspath(__file__)) # .../tests
smart_factory_app_dir = os.path.abspath(os.path.join(current_test_dir, '..')) # .../smart-factory-app
project_root = os.path.abspath(os.path.join(smart_factory_app_dir, '..')) # Parent of .../smart-factory-app

if project_root not in sys.path:
    sys.path.insert(0, project_root)
if smart_factory_app_dir not in sys.path: # Also add smart_factory_app_dir itself for `from agents...` if needed by main.py
    sys.path.insert(0, smart_factory_app_dir)


# Import the FastAPI app instance
# The import of 'app' will trigger the initialization code in main.py,
# including agent initializations (real or mocked based on its own logic and config).
# For these tests, we will often patch the agent instances *within* main.py
# or ensure main.py uses mocks via its config (API_USE_MOCK_AGENTS).

# To control agent behavior for API tests, we have a few options:
# 1. Set environment variables that `config.py` reads (e.g., API_USE_MOCK_AGENTS=true)
# 2. Patch the agent instances directly in the `main` module after import.
# For clarity, patching instances in `main` is often more direct for unit testing specific API behaviors.

class TestAPISync(unittest.TestCase): # Using synchronous test client for simplicity with unittest

    @classmethod
    def setUpClass(cls):
        # Apply patches at the class level to affect the import of 'app'
        # This ensures that when 'app' is imported by TestClient, it already sees the mocked agents.
        # Set API_USE_MOCK_AGENTS to False in config for these tests, so main.py tries to use "real" (mocked here) agents
        cls.config_patch = patch('smart_factory_app.api.main.API_USE_MOCK_AGENTS', False)
        cls.config_patch.start()

        cls.mock_llm_interface = MagicMock()
        cls.mock_kg_agent = MagicMock()
        cls.mock_vector_agent = MagicMock()
        cls.mock_run_sql_query_func = MagicMock()

        cls.llm_patch = patch('smart_factory_app.api.main.llm_interface', cls.mock_llm_interface)
        cls.kg_patch = patch('smart_factory_app.api.main.kg_agent', cls.mock_kg_agent)
        cls.vector_patch = patch('smart_factory_app.api.main.vector_agent', cls.mock_vector_agent)
        cls.sql_run_query_patch = patch('smart_factory_app.api.main.run_sql_query', cls.mock_run_sql_query_func)

        cls.llm_patch.start()
        cls.kg_patch.start()
        cls.vector_patch.start()
        cls.sql_run_query_patch.start()
        
        # Import app after all relevant patches are started
        from smart_factory_app.api.main import app
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        cls.llm_patch.stop()
        cls.kg_patch.stop()
        cls.vector_patch.stop()
        cls.sql_run_query_patch.stop()
        cls.config_patch.stop()

    def setUp(self):
        # Reset mocks before each test
        self.mock_llm_interface.reset_mock()
        self.mock_kg_agent.reset_mock()
        self.mock_vector_agent.reset_mock()
        self.mock_run_sql_query_func.reset_mock()

        # Default mock behaviors
        self.mock_llm_interface.parse_query.return_value = {"intent": "unknown", "machine_id": None, "timestamp": None, "parameters": None}
        self.mock_llm_interface.generate_response.return_value = "Default mock LLM response."
        # Update mock_run_sql_query_func to return a tuple (result, example_ids)
        self.mock_run_sql_query_func.return_value = ("Default mock SQL response.", []) 
        self.mock_kg_agent.query.return_value = [{"info": "Default mock KG response"}]
        self.mock_vector_agent.hybrid_search.return_value = {"documents": [["Default mock vector document."]]}


    def test_root_endpoint(self):
        """Test the root endpoint."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"message": "Welcome to the Smart Factory AI Assistant API. Use the /process-query/ endpoint to ask questions."})

    def test_orchestration_sql_only(self):
        """Test a query path that should primarily use the SQL agent."""
        user_query = "What was the OEE for M001 yesterday?"
        parsed_intent = {"intent": "fetch_oee", "machine_id": "M001", "timestamp": "yesterday", "parameters": None}
        
        self.mock_llm_interface.parse_query.return_value = parsed_intent
        # Ensure run_sql_query mock returns the new tuple format (result, example_ids_used)
        self.mock_run_sql_query_func.return_value = ("SQL: OEE for M001 yesterday was 85%.", ["daily_summary_report"])
        self.mock_vector_agent.hybrid_search.return_value = {"documents": [["OEE maintenance log for M001"]]}

        response = self.client.post("/process-query/", json={"query": user_query})
        self.assertEqual(response.status_code, 200)

        # Check parse_query was called with empty history initially
        self.mock_llm_interface.parse_query.assert_called_once_with(user_query, chat_history="")
        
        self.mock_run_sql_query_func.assert_called_once()
        # Check that parsed_query_dict was passed to run_sql_query
        call_args_sql = self.mock_run_sql_query_func.call_args[1] # kwargs
        self.assertEqual(call_args_sql['parsed_query_dict'], parsed_intent)
        expected_sql_question = "What was the OEE for machine M001 around yesterday?"
        self.assertIn(expected_sql_question, call_args_sql['natural_language_query'])
        
        self.mock_kg_agent.query.assert_not_called()
        self.mock_vector_agent.hybrid_search.assert_called_once()
        
        self.mock_llm_interface.generate_response.assert_called_once()
        # Check generate_response was called with empty history initially
        self.assertIn("chat_history", self.mock_llm_interface.generate_response.call_args[1])
        self.assertEqual(self.mock_llm_interface.generate_response.call_args[1]['chat_history'], "")
        
        debug_info = response.json()["debug_info"]
        self.assertEqual(debug_info["sql_agent_few_shot_examples_used"], ["daily_summary_report"])
        self.assertEqual(debug_info["chat_history_provided_to_llm"], "")


    def test_orchestration_sql_then_kg(self):
        """Test a query path that uses SQL, then KG due to SQL results."""
        user_query = "Why did machine CNC-001 stop yesterday?"
        parsed_intent = {"intent": "analyze_downtime", "machine_id": "CNC-001", "timestamp": "yesterday", "parameters": None}
        
        self.mock_llm_interface.parse_query.return_value = parsed_intent
        # Mock SQL to return a fault code and example_ids
        self.mock_run_sql_query_func.return_value = (
            "SQL: Machine CNC-001 stopped due to alarm_code: ALM001 (fault_code = 'FC-123'). Status was CRITICAL_STOP.",
            ["machine_last_running_status"] 
        )
        self.mock_kg_agent.query.return_value = [{"fault_code": "FC-123", "related_info": "Sensor S2 failure.", "related_type": ["Recommendation"]}]
        self.mock_vector_agent.hybrid_search.return_value = {"documents": [["Log for FC-123 on CNC-001"]]}

        response = self.client.post("/process-query/", json={"query": user_query})
        self.assertEqual(response.status_code, 200)

        self.mock_llm_interface.parse_query.assert_called_once_with(user_query, chat_history="")
        self.mock_run_sql_query_func.assert_called_once()
        self.assertEqual(self.mock_run_sql_query_func.call_args[1]['parsed_query_dict'], parsed_intent)

        self.mock_kg_agent.query.assert_called_once()
        self.mock_vector_agent.hybrid_search.assert_called_once()
        self.mock_llm_interface.generate_response.assert_called_once()
        
        debug_info = response.json()["debug_info"]
        self.assertEqual(debug_info["fault_code_from_sql_for_kg"], "FC-123")
        self.assertEqual(debug_info["sql_agent_few_shot_examples_used"], ["machine_last_running_status"])

    def test_conversation_flow_with_memory(self):
        """Test a sequence of API calls for a single user, verifying memory usage."""
        user_id = "test_user_conv_flow"

        # --- First query ---
        query1 = "What was the OEE for M001 yesterday?"
        parsed_intent1 = {"intent": "fetch_oee", "machine_id": "M001", "timestamp": "yesterday"}
        sql_response1 = "SQL: OEE for M001 yesterday was 75%."
        final_response1 = "The OEE for M001 yesterday was 75%."

        self.mock_llm_interface.parse_query.return_value = parsed_intent1
        self.mock_run_sql_query_func.return_value = (sql_response1, ["daily_summary_report"])
        self.mock_vector_agent.hybrid_search.return_value = {"documents": [["OEE doc for M001"]]}
        self.mock_llm_interface.generate_response.return_value = final_response1
        
        response1 = self.client.post("/process-query/", json={"query": query1, "user_id": user_id})
        self.assertEqual(response1.status_code, 200)
        self.assertEqual(response1.json()["answer"], final_response1)

        # Verify parse_query and generate_response were called with empty history for the first call
        self.mock_llm_interface.parse_query.assert_called_with(query1, chat_history="")
        self.mock_llm_interface.generate_response.assert_called_with(
            sql_data=sql_response1, 
            kg_context=unittest.mock.ANY, # Actual value depends on logic if KG is called or not
            vector_context=["OEE doc for M001"], 
            user_query=query1, 
            chat_history=""
        )
        self.assertEqual(response1.json()["debug_info"]["chat_history_provided_to_llm"], "")

        # Reset mocks for the next call in the conversation
        self.mock_llm_interface.reset_mock()
        self.mock_run_sql_query_func.reset_mock()
        self.mock_kg_agent.reset_mock()
        self.mock_vector_agent.reset_mock()

        # --- Second query (follow-up) ---
        query2 = "And for machine M002?" # Relies on previous context (OEE, yesterday)
        # Expected history to be passed to parse_query
        expected_history_for_q2 = f"Human: {query1}\nAI: {final_response1}"
        
        # Mock LLMInterface.parse_query to understand the follow-up based on history
        # This is where the LLM's ability to use history for context resolution is key.
        parsed_intent2 = {"intent": "fetch_oee", "machine_id": "M002", "timestamp": "yesterday"} # Resolved by LLM
        self.mock_llm_interface.parse_query.return_value = parsed_intent2
        
        sql_response2 = "SQL: OEE for M002 yesterday was 80%."
        final_response2 = "The OEE for M002 yesterday was 80%."
        self.mock_run_sql_query_func.return_value = (sql_response2, ["daily_summary_report"])
        self.mock_vector_agent.hybrid_search.return_value = {"documents": [["OEE doc for M002"]]}
        self.mock_llm_interface.generate_response.return_value = final_response2

        response2 = self.client.post("/process-query/", json={"query": query2, "user_id": user_id})
        self.assertEqual(response2.status_code, 200)
        self.assertEqual(response2.json()["answer"], final_response2)

        # Verify parse_query was called with the history from the first interaction
        self.mock_llm_interface.parse_query.assert_called_with(query2, chat_history=expected_history_for_q2)
        
        # Verify run_sql_query was called with data for M002
        self.mock_run_sql_query_func.assert_called_once()
        self.assertIn("M002", self.mock_run_sql_query_func.call_args[1]['natural_language_query'])
        self.assertEqual(self.mock_run_sql_query_func.call_args[1]['parsed_query_dict'], parsed_intent2)

        # Verify generate_response was called with history
        self.mock_llm_interface.generate_response.assert_called_with(
            sql_data=sql_response2, 
            kg_context=unittest.mock.ANY,
            vector_context=["OEE doc for M002"], 
            user_query=query2, 
            chat_history=expected_history_for_q2
        )
        self.assertEqual(response2.json()["debug_info"]["chat_history_provided_to_llm"], expected_history_for_q2)
        
        # Clean up memory for this user_id if it's a global store and tests might interfere
        from smart_factory_app.api.main import conversation_memory_store
        if user_id in conversation_memory_store:
            del conversation_memory_store[user_id]


    def test_process_query_llm_parse_error(self):
        """Test /process-query/ when LLM parsing raises an exception."""
        self.mock_llm_interface.parse_query.side_effect = Exception("Simulated LLM parsing error")

        response = self.client.post("/process-query/", json={"query": "any query"})
        
        self.assertEqual(response.status_code, 500)
        self.assertIn("Simulated LLM parsing error", response.json()["detail"])


if __name__ == '__main__':
    unittest.main()
