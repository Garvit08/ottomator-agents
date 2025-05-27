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
        self.mock_run_sql_query_func.return_value = "Default mock SQL response."
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
        self.mock_run_sql_query_func.return_value = "SQL: OEE for M001 yesterday was 85%."
        # Vector agent will always be called with current logic, KG might be skipped.
        self.mock_vector_agent.hybrid_search.return_value = {"documents": [["OEE maintenance log for M001"]]}

        response = self.client.post("/process-query/", json={"query": user_query})
        self.assertEqual(response.status_code, 200)

        self.mock_llm_interface.parse_query.assert_called_once_with(user_query)
        self.mock_run_sql_query_func.assert_called_once()
        # Check the question passed to SQL agent based on new logic
        expected_sql_question = "What was the OEE for machine M001 around yesterday?"
        self.assertIn(expected_sql_question, self.mock_run_sql_query_func.call_args[0][0])
        
        self.mock_kg_agent.query.assert_not_called() # Should not be called for simple OEE fetch
        
        self.mock_vector_agent.hybrid_search.assert_called_once()
        # Check refined query for vector agent
        vector_call_args = self.mock_vector_agent.hybrid_search.call_args[1]
        self.assertIn(user_query, vector_call_args['query_text'])
        self.assertIn("SQL: OEE for M001 yesterday was 85%", vector_call_args['query_text']) # SQL context added
        self.assertIn("M001", vector_call_args['keywords'])
        self.assertIn("oee", vector_call_args['keywords'])


        self.mock_llm_interface.generate_response.assert_called_once()
        # Verify debug info
        debug_info = response.json()["debug_info"]
        self.assertEqual(debug_info["question_to_sql_agent"], expected_sql_question)
        self.assertTrue(debug_info["sql_agent_response_snippet"].startswith("SQL: OEE for M001"))
        self.assertEqual(debug_info["cypher_query_to_kg_agent"], "N/A") # Or actual query if it was formulated but skipped
        self.assertTrue(debug_info["kg_agent_response_snippet"].startswith("No KG query needed"))


    def test_orchestration_sql_then_kg(self):
        """Test a query path that uses SQL, then KG due to SQL results."""
        user_query = "Why did machine CNC-001 stop yesterday?"
        parsed_intent = {"intent": "analyze_downtime", "machine_id": "CNC-001", "timestamp": "yesterday", "parameters": None}
        
        self.mock_llm_interface.parse_query.return_value = parsed_intent
        # Mock SQL to return a fault code
        self.mock_run_sql_query_func.return_value = "SQL: Machine CNC-001 stopped due to alarm_code: ALM001 (fault_code = 'FC-123'). Status was CRITICAL_STOP."
        self.mock_kg_agent.query.return_value = [{"fault_code": "FC-123", "related_info": "Sensor S2 failure.", "related_type": ["Recommendation"]}]
        self.mock_vector_agent.hybrid_search.return_value = {"documents": [["Log for FC-123 on CNC-001"]]}


        response = self.client.post("/process-query/", json={"query": user_query})
        self.assertEqual(response.status_code, 200)

        self.mock_llm_interface.parse_query.assert_called_once_with(user_query)
        self.mock_run_sql_query_func.assert_called_once()
        expected_sql_question = "What were the alarms and operational status for machine CNC-001 around yesterday that might explain a stop or downtime?"
        self.assertEqual(self.mock_run_sql_query_func.call_args[0][0], expected_sql_question)

        self.mock_kg_agent.query.assert_called_once()
        # Based on "fault_code = 'FC-123'" in SQL response, KG should be queried for "FC-123"
        expected_kg_query = "MATCH (f:Fault {code: $code})-[:CAUSED_BY|LINKED_TO_RECOMMENDATION*1..2]->(related) RETURN f.code AS fault_code, related.description AS related_info, labels(related) as related_type"
        actual_kg_call = self.mock_kg_agent.query.call_args
        self.assertEqual(actual_kg_call[0][0], expected_kg_query) # Cypher query
        self.assertEqual(actual_kg_call[1]['params'], {'code': 'FC-123'}) # Params

        self.mock_vector_agent.hybrid_search.assert_called_once()
        vector_call_args = self.mock_vector_agent.hybrid_search.call_args[1]
        self.assertIn("SQL: Machine CNC-001 stopped", vector_call_args['query_text'])
        self.assertIn("Knowledge Graph found:", vector_call_args['query_text'])
        self.assertIn("FC-123", vector_call_args['keywords'])

        self.mock_llm_interface.generate_response.assert_called_once()
        debug_info = response.json()["debug_info"]
        self.assertEqual(debug_info["fault_code_from_sql_for_kg"], "FC-123")
        self.assertTrue(debug_info["kg_agent_response_snippet"].startswith("Knowledge Graph found:"))


    def test_orchestration_full_path_with_params(self):
        """Test a query involving parameters that trigger specific agent behaviors."""
        user_query = "Show alarms for Welder-002 yesterday with alarm_code E-101."
        # LLM parse_query should extract 'alarm_code' into parameters.
        parsed_intent = {
            "intent": "get_alarms", 
            "machine_id": "Welder-002", 
            "timestamp": "yesterday", 
            "parameters": {"alarm_code": "E-101"}
        }
        self.mock_llm_interface.parse_query.return_value = parsed_intent
        self.mock_run_sql_query_func.return_value = "SQL: Alarm E-101 on Welder-002 at 10:00 AM, duration 5m."
        # KG might be called if alarm_code E-101 is also treated as a fault_code for lookup
        # Let's assume E-101 is NOT treated as a fault_code for KG in this path, so KG not called.
        # This depends on the exact logic in main.py for `intermediate_data["fault_code_from_sql"]`
        # and the conditions for KG call. The current intermediate_data logic is very specific.
        # For "get_alarms" intent without explicit fault_code in SQL response, KG might not be called.
        # Let's refine `main.py` logic or this test.
        # If sql_data_str contains "alarm_code: E-101" and that sets intermediate_data, then KG would be called.
        # For this test, let's assume SQL response does *not* trigger the KG's fault_code logic.
        self.mock_kg_agent.query.return_value = [] # Or assert not called if conditions aren't met

        self.mock_vector_agent.hybrid_search.return_value = {"documents": [["Procedure for alarm E-101."]]}

        response = self.client.post("/process-query/", json={"query": user_query})
        self.assertEqual(response.status_code, 200)

        self.mock_llm_interface.parse_query.assert_called_once_with(user_query)
        self.mock_run_sql_query_func.assert_called_once()
        expected_sql_question = "List alarms for machine Welder-002 around yesterday. Filter by alarm code E-101."
        self.assertEqual(self.mock_run_sql_query_func.call_args[0][0], expected_sql_question)
        
        # Based on current main.py, KG is called if intent is find_error_cause OR fault_code is found.
        # If "get_alarms" doesn't set a fault_code in intermediate_data, KG won't be called for this.
        # Let's assume it's not called for this specific intent unless SQL output triggers it.
        # If SQL output was "fault_code = 'E-101'", then KG would be called.
        # For this test, assume the SQL output "Alarm E-101..." does *not* set intermediate_data["fault_code_from_sql"].
        self.mock_kg_agent.query.assert_not_called() 

        self.mock_vector_agent.hybrid_search.assert_called_once()
        vector_call_args = self.mock_vector_agent.hybrid_search.call_args[1]
        self.assertIn("SQL: Alarm E-101 on Welder-002", vector_call_args['query_text'])
        self.assertIn("E-101", vector_call_args['keywords']) # From parameters
        self.assertIn("Welder-002", vector_call_args['keywords'])
        self.assertIn("alarms", vector_call_args['keywords'])


        self.mock_llm_interface.generate_response.assert_called_once()
        debug_info = response.json()["debug_info"]
        self.assertEqual(debug_info["fault_code_from_sql_for_kg"], "N/A") # As KG was not called for fault
        self.assertTrue(debug_info["kg_agent_response_snippet"].startswith("No KG query needed"))


    def test_process_query_llm_parse_error(self):
        """Test /process-query/ when LLM parsing raises an exception."""
        self.mock_llm_interface.parse_query.side_effect = Exception("Simulated LLM parsing error")

        response = self.client.post("/process-query/", json={"query": "any query"})
        
        self.assertEqual(response.status_code, 500)
        self.assertIn("Simulated LLM parsing error", response.json()["detail"])


if __name__ == '__main__':
    unittest.main()
