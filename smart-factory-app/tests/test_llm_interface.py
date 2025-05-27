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
        
        # Updated mock prompts to include chat_history placeholder
        self.mock_parse_query_prompt = "New User Query: \"{user_query}\"\nChat History:\n{chat_history}\nJSON Output:"
        self.mock_generate_response_prompt = "User Query: {user_query}\nChat History:\n{chat_history}\nSQL: {sql_data}\nKG: {kg_context}\nVector: {vector_context_str}\nAnswer:"
        
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
        """Test successful query parsing for a standard query."""
        llm_interface = LLMInterface(use_mock=True) 
        
        # Example: Test OEE query without history
        user_query_oee = "What was the OEE for machine CNC-002 yesterday?"
        expected_oee_json = {"intent": "fetch_oee", "machine_id": "CNC-002", "timestamp": "yesterday", "parameters": {"oee_threshold": None}}
        llm_interface.llm.invoke = MagicMock(return_value=json.dumps(expected_oee_json))

        # Call parse_query with explicit empty chat_history
        parsed_output_oee = llm_interface.parse_query(user_query_oee, chat_history="") 
        
        # Verify prompt includes the (empty) chat history
        expected_prompt_oee = self.mock_parse_query_prompt.format(user_query=user_query_oee, chat_history="No history available.")
        llm_interface.llm.invoke.assert_called_once_with(expected_prompt_oee)
        self.assertEqual(parsed_output_oee["intent"], "fetch_oee")
        self.assertEqual(parsed_output_oee["machine_id"], "CNC-002")
        llm_interface.llm.invoke.reset_mock()

        # Test Case: OEE Query with some history
        chat_hist_1 = "Human: What machines are active?\nAI: CNC-001 and CNC-002 are active."
        # MockOllama's invoke will be called with a prompt containing this history.
        # For this test, we assume the mocked LLM still returns the same JSON for simplicity,
        # but we verify the history was passed in the prompt.
        llm_interface.llm.invoke = MagicMock(return_value=json.dumps(expected_oee_json))
        parsed_output_oee_hist = llm_interface.parse_query(user_query_oee, chat_history=chat_hist_1)
        expected_prompt_oee_hist = self.mock_parse_query_prompt.format(user_query=user_query_oee, chat_history=chat_hist_1)
        llm_interface.llm.invoke.assert_called_once_with(expected_prompt_oee_hist)
        self.assertEqual(parsed_output_oee_hist["intent"], "fetch_oee") # Assuming LLM (mocked) still picks up intent correctly
        llm_interface.llm.invoke.reset_mock()


    def test_parse_query_new_intents_with_history(self):
        """Test query parsing for new intents, ensuring history is passed."""
        llm_interface = LLMInterface(use_mock=True) 
        sample_history = "Human: Tell me about CNC-001.\nAI: CNC-001 is a milling machine."

        # Test Case 1: Get Alarms - "it" refers to CNC-001 from history
        user_query_alarms = "Any alarms for it yesterday?" 
        # MockOllama (or a direct mock of llm.invoke) needs to simulate resolving "it" to "CNC-001"
        expected_alarms_json = {"intent": "get_alarms", "machine_id": "CNC-001", "timestamp": "yesterday", "parameters": None}
        llm_interface.llm.invoke = MagicMock(return_value=json.dumps(expected_alarms_json))
        
        parsed_output_alarms = llm_interface.parse_query(user_query_alarms, chat_history=sample_history)
        expected_prompt_alarms = self.mock_parse_query_prompt.format(user_query=user_query_alarms, chat_history=sample_history)
        llm_interface.llm.invoke.assert_called_once_with(expected_prompt_alarms)
        # This assertion now also implicitly tests if the mocked LLM correctly used history to resolve "it"
        self.assertEqual(parsed_output_alarms, expected_alarms_json) 
        llm_interface.llm.invoke.reset_mock()


    def test_parse_query_json_decode_error(self):
        """Test query parsing with a JSONDecodeError from LLM response, with history."""
        llm_interface = LLMInterface(use_mock=True)
        malformed_json_response = "This is not valid JSON"
        llm_interface.llm.invoke = MagicMock(return_value=malformed_json_response)
        sample_history="Human: Previous query.\nAI: Previous answer."

        user_query = "A query that will result in malformed JSON"
        parsed_output = llm_interface.parse_query(user_query, chat_history=sample_history)
        
        expected_prompt_error = self.mock_parse_query_prompt.format(user_query=user_query, chat_history=sample_history)
        llm_interface.llm.invoke.assert_called_once_with(expected_prompt_error)
        
        self.assertEqual(parsed_output["intent"], "unknown") 


    def test_generate_response_success_with_history(self):
        """Test successful response generation including chat history."""
        llm_interface = LLMInterface(use_mock=True)
        mock_llm_generated_text = "This is the synthesized response considering history."
        llm_interface.llm.invoke = MagicMock(return_value=mock_llm_generated_text)

        sql_data = "OEE is 80%"
        kg_context = "Machine M001 is a press."
        vector_context = ["Log: M001 had an error."]
        user_query = "Tell me more about M001 based on this."
        chat_history_for_response = "Human: What is M001's OEE?\nAI: OEE for M001 is 80%."


        expected_vector_str = "Document 1: Log: M001 had an error."
        expected_prompt = self.mock_generate_response_prompt.format(
            user_query=user_query,
            sql_data=sql_data,
            kg_context=kg_context,
            vector_context_str=expected_vector_str,
            chat_history=chat_history_for_response
        )

        response = llm_interface.generate_response(sql_data, kg_context, vector_context, user_query, chat_history=chat_history_for_response)

        llm_interface.llm.invoke.assert_called_once_with(expected_prompt)
        self.assertEqual(response, mock_llm_generated_text)

    def test_generate_response_missing_history_and_context(self):
        """Test response generation with some context missing and no history."""
        llm_interface = LLMInterface(use_mock=True)
        mock_llm_generated_text = "Response with partial context and no history."
        llm_interface.llm.invoke = MagicMock(return_value=mock_llm_generated_text)
        
        sql_data = "OEE is 90%"
        user_query = "OEE status?"

        expected_prompt = self.mock_generate_response_prompt.format(
            user_query=user_query,
            sql_data=sql_data,
            kg_context="N/A", 
            vector_context_str="N/A",
            chat_history="No history available." 
        )
        # Call without chat_history argument to use default empty string
        response = llm_interface.generate_response(sql_data=sql_data, kg_context=None, vector_context=[], user_query=user_query) 
        
        llm_interface.llm.invoke.assert_called_once_with(expected_prompt)
        self.assertEqual(response, mock_llm_generated_text)


if __name__ == '__main__':
    unittest.main()
