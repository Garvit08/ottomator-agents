import os
import json
from typing import Dict, List, Optional, Any

import sys # Ensure sys is imported for path adjustments
from langchain_core.pydantic_v1 import BaseModel, Field # For structured output schema

# Attempt to import Ollama. If not available, use a mock.
try:
    from langchain_community.llms import Ollama
    from langchain_community.chat_models import ChatOllama # For structured output
    OLLAMA_AVAILABLE = True
except ImportError:
    Ollama = None # Define Ollama as None if import fails
    ChatOllama = None # Define ChatOllama as None
    OLLAMA_AVAILABLE = False
    # print("Ollama or ChatOllama not found. Using MockOllama for LLM interactions.")

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

# --- Pydantic Models for Structured Output ---
class TimestampRange(BaseModel):
    start_date: Optional[str] = Field(None, description="The start date of a time range, if applicable.")
    end_date: Optional[str] = Field(None, description="The end date of a time range, if applicable.")
    # Adding specific time fields if the model can extract them
    start_time: Optional[str] = Field(None, description="The start time, if a specific time is mentioned with the start date.")
    end_time: Optional[str] = Field(None, description="The end time, if a specific time is mentioned with the end date.")


class ParsedQuery(BaseModel):
    intent: str = Field(description="The primary goal or intent of the user's query.")
    machine_id: Optional[List[str]] = Field(default=None, description="Specific equipment ID(s) or name(s) mentioned. Always return as a list of strings, or null if none.")
    timestamp: Optional[str] = Field(default=None, description="A specific single point in time, e.g., 'yesterday', '2023-10-26', 'today at 2 PM'. Use this if not a range.")
    timestamp_range: Optional[TimestampRange] = Field(default=None, description="A date or time range for the query. Use this if a range is specified or implied (e.g., 'last week').")
    parameters: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Other relevant parameters, filters, or specific data points. Example: {'oee_threshold': 85, 'kpi_name': 'production_rate'}")


# --- LLM Interface Class ---
class LLMInterface:
    def __init__(self, model_name: str = OLLAMA_MODEL, 
                 base_url: Optional[str] = OLLAMA_BASE_URL, 
                 use_mock: bool = not OLLAMA_AVAILABLE):
        
        self.model_name = model_name
        self.base_url = base_url
        self.use_mock = use_mock

        self.parse_query_prompt_template = load_prompt_template(PARSE_QUERY_PROMPT_FILE)
        self.generate_response_prompt_template = load_prompt_template(GENERATE_RESPONSE_PROMPT_FILE)

        self.basic_llm = None # For generate_response or fallback
        self.structured_llm = None # For parse_query with structured output

        if not self.parse_query_prompt_template or not self.generate_response_prompt_template:
            print("LLMInterface: Critical error - prompt templates could not be loaded. Forcing mock mode.")
            self.use_mock = True
            if not self.parse_query_prompt_template:
                self.parse_query_prompt_template = "New User Query: \"{user_query}\"\nChat History:\n{chat_history}\nJSON Output:" # Basic fallback
            if not self.generate_response_prompt_template:
                self.generate_response_prompt_template = "User Query: {user_query}\nChat History:\n{chat_history}\nSQL: {sql_data}\nKG: {kg_context}\nVector: {vector_context_str}\nAnswer:" # Basic fallback

        if self.use_mock or not OLLAMA_AVAILABLE or not ChatOllama: # Check ChatOllama too
            print(f"LLMInterface: Using MockOllama. (Ollama/ChatOllama available: {OLLAMA_AVAILABLE and bool(ChatOllama)}, use_mock flag: {self.use_mock})")
            self.basic_llm = MockOllama(model=self.model_name, base_url=self.base_url)
            # MockOllama will be used for both parse_query (with string parsing) and generate_response in mock mode.
            # structured_llm remains None in mock mode for now.
        else:
            try:
                print(f"LLMInterface: Initializing ChatOllama for structured output with model: {self.model_name}, base_url: {self.base_url}")
                chat_model_instance = ChatOllama(
                    model=self.model_name,
                    base_url=self.base_url,
                    format="json" # Crucial for .with_structured_output to work reliably
                )
                self.structured_llm = chat_model_instance.with_structured_output(ParsedQuery)
                print("LLMInterface: ChatOllama for structured output initialized successfully.")

                # Initialize basic Ollama for generate_response (or use ChatOllama if preferred for all)
                print(f"LLMInterface: Initializing basic Ollama for text generation with model: {self.model_name}, base_url: {self.base_url}")
                self.basic_llm = Ollama(model=self.model_name, base_url=self.base_url)
                # Test basic_llm (optional)
                # test_response = self.basic_llm.invoke("Hi") 
                # print(f"LLMInterface: Basic Ollama test response: '{test_response[:50]}...'")
                print("LLMInterface: Basic Ollama for text generation initialized successfully.")

            except Exception as e:
                print(f"LLMInterface: Failed to initialize Ollama/ChatOllama models: {e}")
                print("LLMInterface: Falling back to MockOllama for all operations.")
                self.basic_llm = MockOllama(model=self.model_name, base_url=self.base_url)
                self.use_mock = True # Ensure use_mock reflects this fallback state
                self.structured_llm = None


    def parse_query(self, user_query: str, chat_history: str = "") -> Dict[str, Any]:
        """
        Parses the user query to extract structured information using the LLM
        with schema enforcement via Pydantic models.
        """
        default_response = {"intent": "unknown", "machine_id": None, "timestamp": None, "timestamp_range": None, "parameters": None}

        if not self.parse_query_prompt_template:
            print("LLMInterface: Parse query prompt template not loaded. Cannot process query.")
            return default_response
        
        try:
            full_prompt_str = self.parse_query_prompt_template.format(
                user_query=user_query, 
                chat_history=chat_history if chat_history else "No history available."
            )
            # Remove the final "JSON Output: ..." guidance from the prompt if it exists,
            # as with_structured_output handles the JSON generation and schema adherence.
            if "JSON Output:" in full_prompt_str:
                full_prompt_str = full_prompt_str.split("JSON Output:")[0].strip()

        except KeyError as e:
            print(f"LLMInterface: Error formatting parse_query_prompt. Missing key: {e}. Using basic prompt.")
            full_prompt_str = f"New User Query: \"{user_query}\"\nChat History:\n{chat_history if chat_history else 'No history available.'}"


        if not self.use_mock and self.structured_llm:
            try:
                # Invoke the LLM expecting a Pydantic object (ParsedQuery)
                print(f"LLMInterface: Attempting structured output parse for query: {user_query[:50]}...")
                parsed_object: ParsedQuery = self.structured_llm.invoke(full_prompt_str)
                # Convert Pydantic model to dict for consistent return type
                return parsed_object.dict(exclude_none=True)
            except Exception as e:
                print(f"LLMInterface: Error invoking LLM with structured output: {e}. Falling back.")
                # Fallback path below will be used.
        
        # Fallback or Mock path (uses basic_llm which might be MockOllama or basic Ollama)
        print(f"LLMInterface: Using fallback/mock path for parse_query for query: {user_query[:50]}...")
        try:
            # The prompt for basic_llm should still end with an instruction for JSON if it's not the structured_llm
            # This means the original prompt with "JSON Output:" might be better here for the fallback.
            # Re-format with the original template if it was modified.
            fallback_prompt = self.parse_query_prompt_template.format(
                user_query=user_query, 
                chat_history=chat_history if chat_history else "No history available."
            )

            response_str = self.basic_llm.invoke(fallback_prompt)
            
            if "```json" in response_str:
                response_str = response_str.split("```json")[1].split("```")[0].strip()
            elif "```" in response_str:
                 response_str = response_str.split("```")[1].strip()

            parsed_json = json.loads(response_str)
            
            # Basic validation and structure filling
            validated_response = {
                "intent": parsed_json.get("intent", "unknown"),
                "machine_id": parsed_json.get("machine_id"),
                "timestamp": parsed_json.get("timestamp"),
                "timestamp_range": parsed_json.get("timestamp_range"),
                "parameters": parsed_json.get("parameters"),
            }
            # Ensure machine_id is a list if it's a string (for consistency with Pydantic model)
            if isinstance(validated_response["machine_id"], str):
                validated_response["machine_id"] = [validated_response["machine_id"]]
            
            return validated_response
            
        except json.JSONDecodeError as e_json:
            print(f"LLMInterface (fallback/mock): Error parsing JSON response: {e_json}")
            print(f"LLMInterface (fallback/mock): Raw Response was: {response_str if 'response_str' in locals() else 'N/A'}")
            return default_response 
        except Exception as e_gen:
            print(f"LLMInterface (fallback/mock): Error invoking LLM or processing response: {e_gen}")
            return default_response


    def generate_response(self, sql_data: Optional[str], kg_context: Optional[str], 
                          vector_context: Optional[List[str]], user_query: str, chat_history: str = "") -> str:
        """
        Generates a human-readable response using the basic LLM based on provided contexts and chat history.
        """
        if not self.generate_response_prompt_template:
            print("LLMInterface: Generate response prompt template not loaded. Cannot generate response.")
            return "Error: Response generation template is missing."

        llm_to_use = self.basic_llm # Use basic_llm (Ollama or MockOllama)
        if not llm_to_use:
            print("LLMInterface: No LLM available for generate_response (basic_llm is None).")
            return "Error: LLM for response generation is not available."

        vector_context_str = "\n".join([f"Document {i+1}: {item}" for i, item in enumerate(vector_context)]) if vector_context else "N/A"
        
        try:
            full_prompt = self.generate_response_prompt_template.format(
                user_query=user_query,
                sql_data=sql_data if sql_data else "N/A",
                kg_context=kg_context if kg_context else "N/A",
                vector_context_str=vector_context_str,
                chat_history=chat_history if chat_history else "No history available."
            )
        except KeyError as e:
            print(f"LLMInterface: Error formatting generate_response_prompt. Missing key: {e}. Using basic prompt.")
            full_prompt = (f"User Query: {user_query}\nChat History:\n{chat_history if chat_history else 'No history available.'}\n"
                           f"SQL: {sql_data if sql_data else 'N/A'}\nKG: {kg_context if kg_context else 'N/A'}\n"
                           f"Vector: {vector_context_str}\nAnswer:")

        try:
            llm_response = llm_to_use.invoke(full_prompt, temperature=0.1) # Keep temperature for generate_response
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
        parsed_query1 = llm_interface.parse_query(query1, chat_history="Human: Any issues with CNC machines?\nAI: CNC-002 had a brief stop.")
        print(f"User Query 1: {query1}")
        print(f"Parsed Output 1: {json.dumps(parsed_query1, indent=2)}")

        # Test Case 2: Downtime Query with Time Range
        query2 = "Show me the downtime for machine OP-10 last week."
        parsed_query2 = llm_interface.parse_query(query2) # No history
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
