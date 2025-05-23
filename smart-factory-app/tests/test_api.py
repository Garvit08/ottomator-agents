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

    def setUp(self):
        # This is tricky: main.py initializes agents at import time.
        # To ensure our API tests use controlled mocks for agents, we need to patch
        # the *instances* that `app` (from main.py) will use.
        # The patching should happen *before* `app` is imported the first time by a test runner.
        # Or, we patch them after import but before TestClient makes calls.

        # Let's assume main.py's API_USE_MOCK_AGENTS is True or we patch the instances.
        # For this setup, we will patch the agent instances that `main.py` creates or imports.
        # This requires knowing the variable names in `main.py` (e.g., `llm_interface`, `kg_agent`).

        self.mock_llm_interface = MagicMock()
        self.mock_kg_agent = MagicMock()
        self.mock_vector_agent = MagicMock()
        # run_sql_query is a function, so it's patched differently.

        # Patching the agent instances within the loaded 'main' module.
        # This assumes 'smart_factory_app.api.main' will be loaded.
        self.llm_patch = patch('smart_factory_app.api.main.llm_interface', self.mock_llm_interface)
        self.kg_patch = patch('smart_factory_app.api.main.kg_agent', self.mock_kg_agent)
        self.vector_patch = patch('smart_factory_app.api.main.vector_agent', self.mock_vector_agent)
        self.sql_run_query_patch = patch('smart_factory_app.api.main.run_sql_query') # This is a function

        self.mock_llm_interface_instance = self.llm_patch.start()
        self.mock_kg_agent_instance = self.kg_patch.start()
        self.mock_vector_agent_instance = self.vector_patch.start()
        self.mock_run_sql_query_func = self.sql_run_query_patch.start()
        
        # Now that patches are started, import the app
        from smart_factory_app.api.main import app
        self.client = TestClient(app)


    def tearDown(self):
        self.llm_patch.stop()
        self.kg_patch.stop()
        self.vector_patch.stop()
        self.sql_run_query_patch.stop()

    def test_root_endpoint(self):
        """Test the root endpoint."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"message": "Welcome to the Smart Factory AI Assistant API. Use the /process-query/ endpoint to ask questions."})

    def test_process_query_success_mocked_orchestration(self):
        """Test /process-query/ endpoint with mocked agent interactions."""
        user_query_text = "What is the OEE of machine CNC-001?"
        
        # Configure mocks for the orchestration steps
        # 1. llm_interface.parse_query
        parsed_query_mock = {
            "intent": "fetch_oee", 
            "machine_id": "CNC-001", 
            "timestamp": "today", 
            "parameters": None
        }
        self.mock_llm_interface_instance.parse_query.return_value = parsed_query_mock

        # 2. Mock data fetching based on intent (as per main.py's simplified logic)
        #    For "fetch_oee", main.py currently constructs mock SQL/KG/Vector strings/results
        #    It calls vector_agent.semantic_search for this intent.
        self.mock_vector_agent_instance.semantic_search.return_value = {
            "documents": [["Mocked OEE document for CNC-001 from vector search."]]
        }
        # The SQL and KG parts are string formatted in main.py's current placeholder logic,
        # so no direct function calls to mock for them for this specific intent's placeholder path.

        # 3. llm_interface.generate_response
        final_answer_mock = "The OEE for CNC-001 is currently 85% (mocked)."
        self.mock_llm_interface_instance.generate_response.return_value = final_answer_mock

        # Make the request
        response = self.client.post("/process-query/", json={"query": user_query_text, "user_id": "test_user"})
        
        # Assertions
        self.assertEqual(response.status_code, 200)
        response_data = response.json()
        
        self.assertEqual(response_data["answer"], final_answer_mock)
        self.assertEqual(response_data["parsed_intent"], parsed_query_mock)
        
        # Verify that the mocked agent methods were called as expected
        self.mock_llm_interface_instance.parse_query.assert_called_once_with(user_query_text)
        
        # Verify vector_agent.semantic_search was called (as per main.py's current mock logic for 'fetch_oee')
        self.mock_vector_agent_instance.semantic_search.assert_called_once_with(
            query_text="OEE issues and solutions for CNC-001", n_results=1
        )
        
        # Verify generate_response was called with expected (mocked) contexts
        # The exact context strings are generated inside main.py's placeholder logic.
        # We can check that it was called with the original query and some string/list contexts.
        self.mock_llm_interface_instance.generate_response.assert_called_once_with(
            sql_data=unittest.mock.ANY, # Or the exact mock string if stable
            kg_context=unittest.mock.ANY, # Or the exact mock string
            vector_context=unittest.mock.ANY, # Should be ['Mocked OEE document...']
            user_query=user_query_text
        )
        # More precise check for vector_context if needed:
        args, kwargs = self.mock_llm_interface_instance.generate_response.call_args
        self.assertEqual(kwargs['vector_context'], ["Mocked OEE document for CNC-001 from vector search."])


    def test_process_query_llm_parse_error(self):
        """Test /process-query/ when LLM parsing raises an exception (simulated)."""
        self.mock_llm_interface_instance.parse_query.side_effect = Exception("Simulated LLM parsing error")

        response = self.client.post("/process-query/", json={"query": "any query"})
        
        self.assertEqual(response.status_code, 500) # Internal Server Error
        self.assertIn("Simulated LLM parsing error", response.json()["detail"])


    def test_process_query_general_intent_mocked(self):
        """Test /process-query/ for a general intent using mocks."""
        user_query_text = "Tell me about the factory."
        
        parsed_query_mock = {"intent": "general_query", "machine_id": None, "timestamp": None, "parameters": None}
        self.mock_llm_interface_instance.parse_query.return_value = parsed_query_mock

        # For "general_query", main.py's placeholder logic calls vector_agent.semantic_search
        self.mock_vector_agent_instance.semantic_search.return_value = {
            "documents": [["General factory information document."]]
        }
        
        final_answer_mock = "The factory is doing great (mocked general response)."
        self.mock_llm_interface_instance.generate_response.return_value = final_answer_mock

        response = self.client.post("/process-query/", json={"query": user_query_text})
        
        self.assertEqual(response.status_code, 200)
        response_data = response.json()
        self.assertEqual(response_data["answer"], final_answer_mock)
        
        self.mock_llm_interface_instance.parse_query.assert_called_once_with(user_query_text)
        self.mock_vector_agent_instance.semantic_search.assert_called_once_with(
            query_text=user_query_text, n_results=1 # As per main.py's general case
        )
        self.mock_llm_interface_instance.generate_response.assert_called_once()


if __name__ == '__main__':
    # Note: Running unittest.main() directly here might have issues with FastAPI app lifecycle
    # or patches if not managed carefully. It's often better to run tests via `python -m unittest discover`.
    # However, for self-contained test files, it can work.
    unittest.main()
