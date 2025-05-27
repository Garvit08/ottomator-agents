import os
import json
from typing import Dict, List, Optional, Any

# Attempt to import Ollama. If not available, use a mock.
try:
    from langchain_community.llms import Ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False
    # print("Ollama not found. Using MockOllama for LLM interactions.")


# Path adjustments for config import
current_dir_llm_interface = os.path.dirname(os.path.abspath(__file__)) # .../agents
smart_factory_app_dir_llm = os.path.abspath(os.path.join(current_dir_llm_interface, '..')) # .../smart-factory-app
project_root_llm_interface = os.path.abspath(os.path.join(smart_factory_app_dir_llm, '..')) # parent of smart-factory-app

if project_root_llm_interface not in sys.path:
    sys.path.insert(0, project_root_llm_interface) # Allows `from smart_factory_app.config...`

try:
    from smart_factory_app.config.config import (
        OLLAMA_MODEL, 
        OLLAMA_BASE_URL,
        PARSE_QUERY_PROMPT_FILE,
        GENERATE_RESPONSE_PROMPT_FILE
    )
except ImportError:
    print("Error importing config for LLMInterface. Using fallback environment variables/defaults.")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mistral")
    OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    # Fallback prompt file paths (less robust, assumes script run from specific location or prompts dir is findable)
    _fallback_prompts_dir = os.path.join(os.path.dirname(__file__), '..', 'prompts')
    PARSE_QUERY_PROMPT_FILE = os.path.join(_fallback_prompts_dir, 'parse_query_prompt.txt')
    GENERATE_RESPONSE_PROMPT_FILE = os.path.join(_fallback_prompts_dir, 'generate_response_prompt.txt')


# --- Prompt Loading Function ---
def load_prompt_template(file_path: str) -> Optional[str]:
    """Loads a prompt template from a file."""
    try:
        # Paths from config.py are constructed to be absolute or resolvable.
        if not os.path.isabs(file_path):
             # This case should ideally not be hit if config.py sets up absolute paths.
             # If it's relative, it's assumed relative to the project root (smart_factory_app_dir_llm)
             file_path = os.path.join(smart_factory_app_dir_llm, file_path)

        with open(file_path, 'r') as f:
            return f.read()
    except FileNotFoundError:
        print(f"Prompt file not found: {file_path}")
    except Exception as e:
        print(f"Error loading prompt file {file_path}: {e}")
    return None

# --- Mock LLM for testing when Ollama is not available ---
class MockOllama:
    def __init__(self, model: str = OLLAMA_MODEL, base_url: Optional[str] = OLLAMA_BASE_URL, **kwargs):
        self.model = model
        self.base_url = base_url
        print(f"MockOllama initialized with model: {self.model}, base_url: {self.base_url}")

    def invoke(self, prompt: str, **kwargs) -> str:
        """Simulates LLM invocation with predefined responses based on prompt content."""
        print(f"\n--- MockOllama received prompt for model {self.model} ---\n{prompt}\n----------------------------------")
        if "extract intent, machine_id, and timestamp" in prompt.lower():
            # Simulate response for parse_query
            if "oee for cnc-002 yesterday" in prompt.lower():
                return json.dumps({
                    "intent": "fetch_oee", 
                    "machine_id": "CNC-002", 
                    "timestamp": "yesterday",
                    "parameters": {"oee_threshold": None} # Example of an optional parameter
                })
            elif "downtime for machine op-10 last week" in prompt.lower():
                 return json.dumps({
                    "intent": "get_downtime_summary",
                    "machine_id": "OP-10",
                    "timestamp_range": {"start": "start of last week", "end": "end of last week"},
                    "parameters": None
                })
            elif "production count for m001 today" in prompt.lower():
                return json.dumps({
                    "intent": "get_production_count",
                    "machine_id": "m001",
                    "timestamp": "today",
                    "parameters": None
                })
            elif "alarms for machine 'cnc-001' yesterday" in prompt.lower():
                return json.dumps({
                    "intent": "get_alarms",
                    "machine_id": "CNC-001",
                    "timestamp": "yesterday",
                    "parameters": None
                })
            elif "hourly production count for 'welder-003'" in prompt.lower() and "june 15th, 2024" in prompt.lower() :
                return json.dumps({
                    "intent": "get_hourly_data",
                    "machine_id": "Welder-003",
                    "timestamp": "2024-06-15",
                    "parameters": {"kpi_name": "production_count"}
                })
            elif "current status of 'press-002'" in prompt.lower():
                return json.dumps({
                    "intent": "get_status",
                    "machine_id": "Press-002",
                    "timestamp": "current",
                    "parameters": None
                })
            elif "production goals for 'assembler-005'" in prompt.lower():
                return json.dumps({
                    "intent": "get_production_goals",
                    "machine_id": "Assembler-005",
                    "timestamp": None,
                    "parameters": None
                })
            elif "compare the daily oee for 'cnc-001' and 'cnc-002' last week" in prompt.lower():
                return json.dumps({
                    "intent": "compare_daily_oee",
                    "machine_id": None,
                    "timestamp_range": {"start": "start of last week", "end": "end of last week"},
                    "parameters": {"comparison_items": ["CNC-001", "CNC-002"], "kpi_name": "OEE"}
                })
            elif "type of machine is eqp-101" in prompt.lower():
                 return json.dumps({
                    "intent": "get_equipment_details",
                    "machine_id": "EQP-101",
                    "timestamp": null, # JSON null
                    "parameters": null
                })
            elif "temperature for sensor s1 on machine mtr-5" in prompt.lower():
                return json.dumps({
                    "intent": "get_minute_data",
                    "machine_id": "MTR-5",
                    "timestamp": "today at 3:45 PM", # Assuming the prompt captured this detail
                    "parameters": {"sensor_id": "S1", "parameter_name": "Temperature"}
                })
            else:
                # Fallback for unknown queries within parse_query simulation
                return json.dumps({
                    "intent": "unknown",
                    "machine_id": None,
                    "timestamp": None,
                    "parameters": None
                })
        elif "synthesize a comprehensive answer" in prompt.lower():
            # Simulate response for generate_response
            if "SQL Data" in prompt and "KG Context" in prompt and "Vector Context" in prompt:
                return (
                    "Based on the provided data: The OEE for CNC-002 was 85%. "
                    "The knowledge graph indicates it's part of Production Line A. "
                    "Recent vector search results show a maintenance log for a coolant top-up."
                )
            else:
                return "Could not generate a response due to missing context."
        return "Mock response: Unable to process the generic prompt."

    def __call__(self, prompt: str, **kwargs) -> str: # For compatibility with some Langchain patterns
        return self.invoke(prompt, **kwargs)

# --- LLM Interface Class ---
class LLMInterface:
    def __init__(self, model_name: str = OLLAMA_MODEL, 
                 base_url: Optional[str] = OLLAMA_BASE_URL, 
                 use_mock: bool = not OLLAMA_AVAILABLE):
        
        self.model_name = model_name
        self.base_url = base_url
        self.use_mock = use_mock

        # Load prompt templates
        self.parse_query_prompt_template = load_prompt_template(PARSE_QUERY_PROMPT_FILE)
        self.generate_response_prompt_template = load_prompt_template(GENERATE_RESPONSE_PROMPT_FILE)

        if not self.parse_query_prompt_template or not self.generate_response_prompt_template:
            print("LLMInterface: Critical error - prompt templates could not be loaded. Mocking or LLM calls will likely fail.")
            # Potentially force mock usage or raise an error if prompts are essential
            self.use_mock = True # Force mock if prompts are missing

        if self.use_mock or not OLLAMA_AVAILABLE:
            print(f"LLMInterface: Using MockOllama. (Ollama available: {OLLAMA_AVAILABLE}, use_mock flag: {self.use_mock}, Prompts loaded: {bool(self.parse_query_prompt_template and self.generate_response_prompt_template)})")
            self.llm = MockOllama(model=self.model_name, base_url=self.base_url)
        else:
            try:
                print(f"LLMInterface: Attempting to initialize real Ollama with model: {self.model_name}, base_url: {self.base_url}")
                self.llm = Ollama(model=self.model_name, base_url=self.base_url)
                print("LLMInterface: Testing Ollama connection...")
                test_response = self.llm.invoke("Hi")
                print(f"LLMInterface: Ollama test response received (first 50 chars): '{test_response[:50]}...'")
                print("LLMInterface: Ollama initialized and connection successful.")
            except Exception as e:
                print(f"LLMInterface: Failed to initialize or connect to Ollama ({self.model_name} at {self.base_url}): {e}")
                print("LLMInterface: Falling back to MockOllama.")
                self.llm = MockOllama(model=self.model_name, base_url=self.base_url)
                self.use_mock = True # Ensure use_mock reflects fallback

    def parse_query(self, user_query: str) -> Dict[str, Any]:
        """
        Parses the user query to extract intent, machine_id, and timestamp using the LLM.
        Output format is expected to be JSON.
        """
        parsed_info = {"intent": "unknown", "machine_id": None, "timestamp": None, "parameters": None}

        if not self.parse_query_prompt_template:
            print("LLMInterface: Parse query prompt template not loaded. Cannot process query.")
            return parsed_info
        
        prompt = self.parse_query_prompt_template.format(user_query=user_query)
        
        try:
            response = self.llm.invoke(prompt)
            
            # Clean the response: LLMs sometimes add ```json ... ``` or other text
            if "```json" in response:
                response = response.split("```json")[1].split("```")[0].strip()
            elif "```" in response: # Simpler case of just ``` wrapping
                 response = response.split("```")[1].strip()


            parsed_json = json.loads(response)
            
            # Validate and fill structure, ensuring all keys are present
            parsed_info["intent"] = parsed_json.get("intent", "unknown")
            parsed_info["machine_id"] = parsed_json.get("machine_id")
            # Handle both 'timestamp' and 'timestamp_range'
            if "timestamp" in parsed_json:
                parsed_info["timestamp"] = parsed_json.get("timestamp")
            if "timestamp_range" in parsed_json:
                parsed_info["timestamp_range"] = parsed_json.get("timestamp_range")
                if "timestamp" not in parsed_info and parsed_info["timestamp_range"]: # If only range is present
                    parsed_info.pop("timestamp", None) # Remove the single timestamp if range exists

            parsed_info["parameters"] = parsed_json.get("parameters")

            return parsed_info
            
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON response from LLM: {e}")
            print(f"LLM Raw Response was: {response}") # Log the problematic response
            # Fallback: try to extract key terms using simple string matching if JSON fails
            # This is a very basic fallback.
            if "oee" in user_query.lower(): parsed_info["intent"] = "fetch_oee"
            # Add more basic keyword checks if needed
            return parsed_info 
        except Exception as e:
            print(f"Error invoking LLM or processing response: {e}")
            return parsed_info


    def generate_response(self, sql_data: Optional[str], kg_context: Optional[str], 
                          vector_context: Optional[List[str]], user_query: str) -> str:
        """
        Generates a human-readable response using the LLM based on provided contexts.
        """
        if not self.generate_response_prompt_template:
            print("LLMInterface: Generate response prompt template not loaded. Cannot generate response.")
            return "Error: Response generation template is missing."

        vector_context_str = "\n".join([f"Document {i+1}: {item}" for i, item in enumerate(vector_context)]) if vector_context else "N/A"
        
        full_prompt = self.generate_response_prompt_template.format(
            user_query=user_query,
            sql_data=sql_data if sql_data else "N/A",
            kg_context=kg_context if kg_context else "N/A",
            vector_context_str=vector_context_str
        )
        
        try:
            llm_response = self.llm.invoke(full_prompt)
            return llm_response
        except Exception as e:
            print(f"Error invoking LLM for response generation: {e}")
            return "I encountered an error trying to generate a response. Please check the logs."

# --- Example Usage ---
if __name__ == "__main__":
    # Path adjustments for config are at the top.
    print(f"Ollama available: {OLLAMA_AVAILABLE}")
    # Initialize with use_mock=True if Ollama is not running or not installed,
    # or use config.py settings (which might also lead to mock if Ollama is down).
    # By default, LLMInterface now uses config values for model and URL.
    # The use_mock flag in LLMInterface constructor can override this.
    # For this test, we let LLMInterface decide based on OLLAMA_AVAILABLE and its internal fallback.
    print(f"LLMInterface example: OLLAMA_AVAILABLE={OLLAMA_AVAILABLE}. LLMInterface will attempt real connection if available.")
    llm_interface = LLMInterface() # Uses defaults from config
    
    print(f"\n--- LLMInterface Configuration in use ---")
    print(f"Model: {llm_interface.model_name}")
    print(f"Base URL: {llm_interface.base_url}")
    print(f"Currently using mock: {llm_interface.use_mock}") # Reflects actual state after init
    print(f"--- End LLMInterface Configuration ---\n")

    print("\n--- Testing Query Parsing ---")

    if not llm_interface.parse_query_prompt_template or not llm_interface.generate_response_prompt_template:
        print("\nExample usage cannot proceed fully as prompt templates are missing.")
    else:
        print("\n--- Testing Query Parsing (with loaded prompt) ---")
        # Test Case 1: OEE Query
        query1 = "What was the OEE for machine CNC-002 yesterday?"
        parsed_query1 = llm_interface.parse_query(query1)
        print(f"User Query 1: {query1}")
        print(f"Parsed Output 1: {json.dumps(parsed_query1, indent=2)}")

        # Test Case 2: Downtime Query with Time Range
        query2 = "Show me the downtime for machine OP-10 last week."
        parsed_query2 = llm_interface.parse_query(query2)
        print(f"\nUser Query 2: {query2}")
        print(f"Parsed Output 2: {json.dumps(parsed_query2, indent=2)}")

        # Test Case 3: Production Count Query
        query3 = "What was the production count for m001 today?"
        parsed_query3 = llm_interface.parse_query(query3)
        print(f"\nUser Query 3: {query3}")
        print(f"Parsed Output 3: {json.dumps(parsed_query3, indent=2)}")
        
        # Test Case 4: Query that might not parse well with mock (or to test fallback)
        query4 = "Tell me about the general status of the factory."
        parsed_query4 = llm_interface.parse_query(query4)
        print(f"\nUser Query 4: {query4}") # Should result in "unknown" intent with mock
        print(f"Parsed Output 4: {json.dumps(parsed_query4, indent=2)}")


        print("\n--- Testing Response Generation (with loaded prompt) ---")
        sample_sql_data = "Machine CNC-002 OEE: 85% on 2023-10-26. Cycle time: 5ms. Downtime: 15 minutes due to sensor calibration."
        sample_kg_context = "CNC-002 is a milling machine, part of Production Line A, manufactured by 'RoboCorp'."
        sample_vector_context = [
            "Log entry 2023-10-26: CNC-002 coolant levels checked and topped up during routine maintenance.",
            "Alert: CNC-002 reported minor vibration anomaly at 14:30 on 2023-10-26, resolved automatically."
        ]
        user_query_for_response = "What happened with CNC-002 yesterday (2023-10-26) and what's its OEE?"

        generated_response = llm_interface.generate_response(
            sql_data=sample_sql_data,
            kg_context=sample_kg_context,
            vector_context=sample_vector_context,
            user_query=user_query_for_response,
        )
        print(f"\nUser Query for Response Generation: {user_query_for_response}")
        print(f"Generated Response:\n{generated_response}")

        # Test with some missing context
        print("\n--- Testing Response Generation (Missing KG and Vector Context) ---")
        generated_response_partial = llm_interface.generate_response(
            sql_data=sample_sql_data,
            kg_context=None, # Missing
            vector_context=[],   # Empty
            user_query=user_query_for_response,
        )
        print(f"\nUser Query for Response Generation: {user_query_for_response}")
        print(f"Generated Response (Partial Context):\n{generated_response_partial}")
