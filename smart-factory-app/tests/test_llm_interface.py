import unittest
import sys
import os
import json
from unittest.mock import patch, MagicMock, mock_open

# --- Path Adjustments ---
current_test_dir = os.path.dirname(os.path.abspath(__file__))
smart_factory_app_dir = os.path.abspath(os.path.join(current_test_dir, '..'))
project_root = os.path.abspath(os.path.join(smart_factory_app_dir, '..'))

if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Import the module to be tested
from smart_factory_app.agents.llm_interface import LLMInterface, load_prompt_template
# Import config to verify defaults or override for testing
from smart_factory_app.config import config 

class TestLLMInterface(unittest.TestCase):

    def setUp(self):
        # This setup can be used to mock config values if needed for specific tests
        # For example, to force using MockOllama or specific prompt file paths
        self.mock_parse_query_prompt = "Parse: {user_query}"
        self.mock_generate_response_prompt = "Respond to: {user_query} with SQL: {sql_data}, KG: {kg_context}, Vector: {vector_context_str}"

        # Patch the load_prompt_template function directly within the llm_interface module
        # to avoid issues with where it's called from.
        self.patcher_load_prompt = patch('smart_factory_app.agents.llm_interface.load_prompt_template')
        self.mock_load_prompt_template = self.patcher_load_prompt.start()

        # Configure the mock to return different templates based on the file path argument
        def load_prompt_side_effect(file_path):
            if file_path == config.PARSE_QUERY_PROMPT_FILE:
                return self.mock_parse_query_prompt
            elif file_path == config.GENERATE_RESPONSE_PROMPT_FILE:
                return self.mock_generate_response_prompt
            return None
        self.mock_load_prompt_template.side_effect = load_prompt_side_effect
        
        # Also patch OLLAMA_AVAILABLE if you want to control real vs mock LLM behavior
        # For most tests here, we'll rely on LLMInterface's use_mock=True or mock self.llm directly.
        self.patcher_ollama_available = patch('smart_factory_app.agents.llm_interface.OLLAMA_AVAILABLE', False)
        self.mock_ollama_available = self.patcher_ollama_available.start()


    def tearDown(self):
        self.patcher_load_prompt.stop()
        self.patcher_ollama_available.stop()

    def test_load_prompt_template_success(self):
        """Test successful loading of a prompt template."""
        # This test is for the helper function, separate from LLMInterface itself
        # To test it, we unpatch the original load_prompt_template or call it directly
        self.patcher_load_prompt.stop() # Stop the class-level patch for this specific test
        
        mock_file_content = "Test prompt content: {placeholder}"
        # Use mock_open to simulate file operations
        with patch("builtins.open", mock_open(read_data=mock_file_content)) as mocked_file:
            prompt = load_prompt_template("dummy/path/prompt.txt")
            self.assertEqual(prompt, mock_file_content)
            mocked_file.assert_called_once_with("dummy/path/prompt.txt", 'r')
        
        self.patcher_load_prompt.start() # Restart the patch for other tests

    def test_load_prompt_template_file_not_found(self):
        """Test load_prompt_template when file is not found."""
        self.patcher_load_prompt.stop()
        with patch("builtins.open", mock_open()) as mocked_file:
            mocked_file.side_effect = FileNotFoundError
            prompt = load_prompt_template("dummy/path/nonexistent.txt")
            self.assertIsNone(prompt)
        self.patcher_load_prompt.start()

    def test_initialization_with_mock_ollama(self):
        """Test LLMInterface initialization forces mock when OLLAMA_AVAILABLE is False."""
        # OLLAMA_AVAILABLE is patched to False in setUp
        llm_interface = LLMInterface(model_name="test_model", base_url="http://mockhost:1234")
        self.assertTrue(llm_interface.use_mock) # Should be true because OLLAMA_AVAILABLE is false
        self.assertIsInstance(llm_interface.llm, MagicMock) # Assuming MockOllama is used or llm is MagicMocked
                                                             # The current LLMInterface uses its own MockOllama class.
                                                             # So, check for that or patch MockOllama to be a MagicMock.
        # To be more precise if MockOllama is the actual class used:
        # from smart_factory_app.agents.llm_interface import MockOllama as LLMInterfaceMockOllama
        # self.assertIsInstance(llm_interface.llm, LLMInterfaceMockOllama)
        # For simplicity, if use_mock=True, it uses MockOllama instance. We can check its behavior.
        self.assertTrue(hasattr(llm_interface.llm, "invoke"))


    @patch('smart_factory_app.agents.llm_interface.Ollama') # Mock the actual Ollama class
    def test_initialization_with_real_ollama_success(self, mock_ollama_class):
        """Test LLMInterface initialization with real Ollama successfully."""
        # Ensure OLLAMA_AVAILABLE is True for this test
        self.patcher_ollama_available.stop() # Stop previous patch
        patcher_ollama_available_true = patch('smart_factory_app.agents.llm_interface.OLLAMA_AVAILABLE', True)
        mock_ollama_available_true = patcher_ollama_available_true.start()

        mock_ollama_instance = MagicMock()
        mock_ollama_instance.invoke.return_value = "Hi test"
        mock_ollama_class.return_value = mock_ollama_instance
        
        llm_interface = LLMInterface(use_mock=False) # Explicitly ask not to use mock

        self.assertFalse(llm_interface.use_mock) # Should be False
        self.assertEqual(llm_interface.llm, mock_ollama_instance)
        mock_ollama_class.assert_called_once_with(model=config.OLLAMA_MODEL, base_url=config.OLLAMA_BASE_URL)
        mock_ollama_instance.invoke.assert_called_once_with("Hi") # Test prompt
        
        patcher_ollama_available_true.stop()
        self.patcher_ollama_available.start() # Restart class-level patch

    def test_parse_query_success(self):
        """Test successful query parsing."""
        llm_interface = LLMInterface(use_mock=True) # Forces MockOllama via constructor
        
        mock_llm_response_json = {"intent": "fetch_oee", "machine_id": "M001", "timestamp": "today", "parameters": None}
        # Mock the invoke method of the llm instance (which is MockOllama)
        llm_interface.llm.invoke = MagicMock(return_value=json.dumps(mock_llm_response_json))

        user_query = "What is the OEE for M001 today?"
        expected_prompt = self.mock_parse_query_prompt.format(user_query=user_query)
        
        parsed_output = llm_interface.parse_query(user_query)

        llm_interface.llm.invoke.assert_called_once_with(expected_prompt)
        self.assertEqual(parsed_output, mock_llm_response_json)

    def test_parse_query_json_decode_error(self):
        """Test query parsing with a JSONDecodeError from LLM response."""
        llm_interface = LLMInterface(use_mock=True)
        malformed_json_response = "This is not valid JSON"
        llm_interface.llm.invoke = MagicMock(return_value=malformed_json_response)

        user_query = "A query that will result in malformed JSON"
        parsed_output = llm_interface.parse_query(user_query)
        
        # Expecting the default fallback structure due to JSON error
        self.assertEqual(parsed_output["intent"], "unknown") # Default from current implementation
        # Check if basic keyword fallback was hit (if any)
        if "oee" in user_query.lower(): # Example from current fallback
             self.assertEqual(parsed_output["intent"], "fetch_oee")


    def test_generate_response_success(self):
        """Test successful response generation."""
        llm_interface = LLMInterface(use_mock=True)
        mock_llm_generated_text = "This is the synthesized response."
        llm_interface.llm.invoke = MagicMock(return_value=mock_llm_generated_text)

        sql_data = "OEE is 80%"
        kg_context = "Machine M001 is a press."
        vector_context = ["Log: M001 had an error."]
        user_query = "Tell me about M001."

        expected_vector_str = "Document 1: Log: M001 had an error."
        expected_prompt = self.mock_generate_response_prompt.format(
            user_query=user_query,
            sql_data=sql_data,
            kg_context=kg_context,
            vector_context_str=expected_vector_str
        )

        response = llm_interface.generate_response(sql_data, kg_context, vector_context, user_query)

        llm_interface.llm.invoke.assert_called_once_with(expected_prompt)
        self.assertEqual(response, mock_llm_generated_text)

    def test_generate_response_missing_context(self):
        """Test response generation with some context missing."""
        llm_interface = LLMInterface(use_mock=True)
        mock_llm_generated_text = "Response with partial context."
        llm_interface.llm.invoke = MagicMock(return_value=mock_llm_generated_text)
        
        sql_data = "OEE is 90%"
        user_query = "OEE status?"

        expected_prompt = self.mock_generate_response_prompt.format(
            user_query=user_query,
            sql_data=sql_data,
            kg_context="N/A", # How generate_response handles None
            vector_context_str="N/A"  # How generate_response handles empty list
        )
        response = llm_interface.generate_response(sql_data=sql_data, kg_context=None, vector_context=[], user_query=user_query)
        
        llm_interface.llm.invoke.assert_called_once_with(expected_prompt)
        self.assertEqual(response, mock_llm_generated_text)


if __name__ == '__main__':
    unittest.main()
