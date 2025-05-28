import os
import sys
import json
import time # Added for performance timing
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn

import json # Already present, just noting for context
from fastapi import FastAPI, HTTPException # Already present
from pydantic import BaseModel # Already present
import uvicorn # Already present
from langchain.memory import ConversationBufferWindowMemory # Added for chat history
from typing import Optional, Dict # For Pydantic optional fields and Dict type hint

# --- Agent and Config Imports ---
try:
    from smart_factory_app.agents.llm_interface import LLMInterface
    from smart_factory_app.agents.sql_agent import run_sql_query # sql_agent's own config handles its LLM and DB
    from smart_factory_app.agents.kg_agent import KGAgent
    from smart_factory_app.agents.vector_agent import VectorAgent
    from smart_factory_app.config.config import (
        API_USE_MOCK_AGENTS, # Controls if API layer forces mocks
        OLLAMA_MODEL, OLLAMA_BASE_URL, # For LLMInterface if not using its internal mock decision
        NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, # For KGAgent
        SENTENCE_TRANSFORMER_MODEL, VECTOR_COLLECTION_NAME, CHROMA_PERSIST_PATH # For VectorAgent
    )
    # This flag indicates if the essential modules *could* be imported.
    # It doesn't guarantee the services (Ollama, DBs) are up.
    CORE_MODULES_IMPORTED = True 
except ImportError as e:
    print(f"Critical Error: Failed to import core modules or config: {e}. API cannot start correctly.")
    # Define mock classes here if we want the API to run in a super-degraded mode for structure testing.
    # For now, let's assume if these fail, it's a setup issue.
    CORE_MODULES_IMPORTED = False
    # Fallback for API_USE_MOCK_AGENTS if config itself couldn't be loaded
    API_USE_MOCK_AGENTS = True 
    # Define minimal mocks so the rest of the script doesn't crash if CORE_MODULES_IMPORTED is false
    # and we still attempt to run.
    class LLMInterface:
        def __init__(self, *args, **kwargs): print("Fallback Mock LLMInterface created.")
        def parse_query(self, q): return {"intent": "mock_fallback_intent"}
        def generate_response(self, *args, **kwargs): return "Fallback mock LLM response."
    def run_sql_query(q): return "Fallback mock SQL response."
    class KGAgent:
        def __init__(self, *args, **kwargs): print("Fallback Mock KGAgent created.")
        def query(self, q, p=None): return []
        def close(self): pass
    class VectorAgent:
        def __init__(self, *args, **kwargs): print("Fallback Mock VectorAgent created.")
        def semantic_search(self, q, n_results=1): return {"documents": [["Fallback mock vector doc"]]}

if not CORE_MODULES_IMPORTED:
    print("Warning: API running in a severely degraded mode due to import errors. Only mock fallbacks active.")

# --- Initialize Agents ---
# Agents will use their own default configurations from config.py if not overridden here.
# The API_USE_MOCK_AGENTS from config.py can force the API layer to use its own mocks,
# regardless of whether agent modules themselves could initialize.

# Global flag to track if we are using the API layer's forced mocks
# This is different from LLMInterface's internal `use_mock` which depends on Ollama's availability.
_api_forced_mock_active = False

if API_USE_MOCK_AGENTS or not CORE_MODULES_IMPORTED:
    print("API Main: Using MOCK agents (due to API_USE_MOCK_AGENTS=True or import failures).")
    _api_forced_mock_active = True
    llm_interface = LLMInterface(use_mock=True) # Force LLMInterface's mock
    # Define API-level mock functions/classes if not already defined by import failure
    if 'run_sql_query' not in locals() or CORE_MODULES_IMPORTED : # if modules imported but we still want api mock
        def run_sql_query(query_text: str): return f"API Mock SQL result for query: {query_text}"
    if 'KGAgent' not in locals() or CORE_MODULES_IMPORTED :
        _KGAgentOriginal = KGAgent if 'KGAgent' in locals() else None # Store original if exists
        class KGAgent: # API Mock KGAgent
            def __init__(self, **kwargs): print("API Mock KGAgent initialized.")
            def query(self, c, p=None): return [{"api_mock_kg_node": "API Mock KG Data"}]
            def close(self): pass
            def ensure_original_close(self): # If we had a real instance
                 if _KGAgentOriginal and hasattr(self, '_real_instance') and self._real_instance:
                      self._real_instance.close()
    if 'VectorAgent' not in locals() or CORE_MODULES_IMPORTED :
        class VectorAgent: # API Mock VectorAgent
            def __init__(self, **kwargs): print("API Mock VectorAgent initialized.")
            def semantic_search(self, q, n_results=1): return {"documents": [["API Mock vector semantic search."]]}
    
    # Instantiate mocks if they were redefined in this block
    kg_agent = KGAgent() 
    vector_agent = VectorAgent()

else:
    print("API Main: Attempting to initialize REAL agents using configurations from config.py...")
    try:
        # LLMInterface decides its own mock status based on Ollama availability unless use_mock is forced.
        # Its defaults (model, base_url) are already from config.py.
        llm_interface = LLMInterface() 
        
        # KGAgent and VectorAgent are initialized using parameters from config.py by default
        # (as their __init__ methods now load defaults from config)
        kg_agent = KGAgent() # Uses NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD from config
        vector_agent = VectorAgent() # Uses SENTENCE_TRANSFORMER_MODEL, etc. from config
        
        # run_sql_query is imported directly and uses its own config.
        # We can do a simple check here if the SQL agent's LLM (placeholder OpenAI) is available
        if 'smart_factory_app.agents.sql_agent' in sys.modules:
            sql_agent_module = sys.modules['smart_factory_app.agents.sql_agent']
            if sql_agent_module.llm is None:
                print("API Main: Warning - LLM for SQL Agent (OpenAI placeholder) is not initialized. SQL queries via agent might fail.")
        
        print("API Main: REAL agents initialized successfully (or they fell back to their own internal mocks if services are down).")
    except Exception as e:
        print(f"API Main: Error initializing REAL agents: {e}. Critical failure. Check agent configurations and services.")
        # This is a critical state. The API might not function as expected.
        # Depending on policy, we might re-raise, or force full API mocks if possible.
        # For now, if this block fails, it implies a setup issue beyond just services being down.
        # The initial CORE_MODULES_IMPORTED check should catch module load issues.
        # This would be an unexpected runtime error during init of correctly imported modules.
        raise RuntimeError(f"Failed to initialize agents: {e}") from e

# --- Initialize Conversation Memory ---
# Global for this example; in a real app, this might be session-based or user-specific.
# For `ConversationBufferWindowMemory`:
# `memory_key` is where the history string will be stored when `load_memory_variables` is called.
# `input_key` and `ai_prefix/human_prefix` define how `save_context` formats and stores interactions.
# Let's use standard "input" for user's turn and "output" for AI's turn for save_context.
# The history will be formatted with "Human:" and "AI:" prefixes by default.
conversation_memory_store: Dict[str, ConversationBufferWindowMemory] = {} # User-specific memory

def get_user_memory(user_id: str) -> ConversationBufferWindowMemory:
    if user_id not in conversation_memory_store:
        conversation_memory_store[user_id] = ConversationBufferWindowMemory(
            k=3, # Remember last 3 interactions
            memory_key="history", # Key for the formatted history string when loading
            input_key="input",    # Key for user's query for saving context
            output_key="output",  # Key for AI's response for saving context
            return_messages=False # Return history as a single string
        )
    return conversation_memory_store[user_id]


# --- Pydantic Models ---
class UserQuery(BaseModel):
    query: str
    user_id: str = "default_user" 
    # session_id: Optional[str] = None # Can be added for more robust session management

class QueryResponse(BaseModel):
    answer: str
    parsed_intent: dict
    debug_info: dict


# --- FastAPI App Instance ---
app = FastAPI(
    title="Smart Factory AI Assistant API",
    description="API for processing natural language queries related to factory operations.",
    version="0.1.0"
)

# --- API Endpoints ---
@app.post("/process-query/", response_model=QueryResponse)
async def process_query_endpoint(user_query: UserQuery):
    """
    Processes a user's natural language query about factory operations.
    """
    endpoint_start_time = time.time() # Total endpoint time
    timings = {} # To store durations

    original_query = user_query.query
    user_id = user_query.user_id # Use user_id for memory key
    print(f"\nReceived query: '{original_query}' from user: '{user_id}'")

    try:
        # 1. Load Conversation History for the user
        user_memory = get_user_memory(user_id)
        # `load_memory_variables` takes an empty dict if the memory doesn't require specific inputs to load.
        loaded_memory_vars = user_memory.load_memory_variables({})
        chat_history_str = loaded_memory_vars.get(user_memory.memory_key, "") # Default to empty string
        
        log_message(f"Loaded chat history for user '{user_id}':\n{chat_history_str if chat_history_str else 'No history available.'}")

        # 2. Parse Query using LLMInterface, now with chat history
        t_parse_start = time.time()
        parsed_query_data = llm_interface.parse_query(original_query, chat_history=chat_history_str)
        timings["parse_query"] = time.time() - t_parse_start
        print(f"Time for parse_query: {timings['parse_query']:.3f} seconds")
        
        intent = parsed_query_data.get("intent", "unknown")
        machine_id = parsed_query_data.get("machine_id")
        timestamp_info = parsed_query_data.get("timestamp") or parsed_query_data.get("timestamp_range")
        parameters = parsed_query_data.get("parameters")
        
        print(f"Parsed query intent: {intent}, Machine: {machine_id}, Time: {timestamp_info}, Params: {parameters}")

        # 2. Orchestration Logic: Call Agents
        sql_data_str: Optional[str] = None
        kg_context_str: Optional[str] = None
        vector_results_docs: list = [] # List of document strings

        print(f"Parsed query intent: {intent}, Machine: {machine_id}, Time: {timestamp_info}, Params: {parameters}")

        # 2. Orchestration Logic: Call Agents
        sql_data_str: Optional[str] = "No SQL data retrieved or query not applicable."
        kg_context_str: Optional[str] = "No KG data retrieved or query not applicable."
        vector_results_docs: list = []
        
        # Intermediate data store for multi-step logic
        intermediate_data = {}
        question_for_sql_agent = "N/A" # For debug info
        cypher_query_for_kg = "N/A" # For debug info
        query_params_for_kg = {} # For debug info for KG params
        search_query_for_vector_db = original_query # Default
        query_keywords_for_vector_db = []


        # --- Step 1: Initial SQL Agent Call (if applicable) ---
        t_sql_start = time.time()
        if not _api_forced_mock_active:
            # Formulate a more targeted initial question for the SQL Agent
            if intent == "analyze_downtime" and machine_id and timestamp_info:
                question_for_sql_agent = f"What were the alarms and operational status for machine {machine_id} around {timestamp_info} that might explain a stop or downtime?"
            elif intent == "fetch_oee" and machine_id and timestamp_info:
                question_for_sql_agent = f"What was the OEE for machine {machine_id} around {timestamp_info}?"
                if parameters and "oee_threshold" in parameters:
                    question_for_sql_agent += f" Specifically, was it above {parameters['oee_threshold']}?"
            elif intent == "get_alarms" and machine_id and timestamp_info:
                question_for_sql_agent = f"List alarms for machine {machine_id} around {timestamp_info}."
                if parameters and "alarm_code" in parameters:
                     question_for_sql_agent += f" Filter by alarm code {parameters['alarm_code']}."
            elif intent == "get_hourly_data" and machine_id and timestamp_info:
                kpi = parameters.get('kpi_name', 'all relevant KPIs') if parameters else 'all relevant KPIs'
                question_for_sql_agent = f"Retrieve hourly data for machine {machine_id} concerning {kpi} on {timestamp_info}."
            elif intent in ["get_status", "get_equipment_details", "get_production_goals", "get_minute_data", "get_production_count", "summarize_production"]:
                question_for_sql_agent = f"Regarding user query '{original_query}', provide relevant information from SQL tables. Focus on intent '{intent}'"
                if machine_id: question_for_sql_agent += f", machine '{machine_id}'"
                if timestamp_info: question_for_sql_agent += f", around time '{timestamp_info}'"
                if parameters: question_for_sql_agent += f", with parameters: {json.dumps(parameters)}"
            else: 
                question_for_sql_agent = f"Investigate based on user query: {original_query}. Parsed intent: {intent}, machine: {machine_id}, time: {timestamp_info}, params: {parameters}."

            if question_for_sql_agent != "N/A":
                log_message(f"Constructed question for SQL Agent: {question_for_sql_agent}")
                sql_examples_used_info = [] 
                try:
                    sql_data_result, sql_examples_used_info = run_sql_query(
                        natural_language_query=question_for_sql_agent,
                        parsed_query_dict=parsed_query_data 
                    )
                    sql_data_str = str(sql_data_result) if sql_data_result else "No specific data found from SQL for this query."
                    log_message(f"SQL Agent Result: {sql_data_str[:300]}...")
                    if sql_examples_used_info:
                        log_message(f"SQL Agent used few-shot examples: {sql_examples_used_info}")
                    if "fault_code = 'FC-123'" in sql_data_str or (parameters and parameters.get("fault_code") == 'FC-123'):
                        intermediate_data["fault_code_from_sql"] = 'FC-123'
                    elif "alarm_code: ALM001" in sql_data_str:
                        intermediate_data["fault_code_from_sql"] = 'ALM001'
                except Exception as e:
                    log_message(f"Error calling SQL Agent: {e}")
                    sql_data_str = "Error retrieving data from SQL database."
            else: # No specific SQL question formulated
                 sql_data_str = "No SQL query was formulated for this request."
        elif _api_forced_mock_active:
            sql_data_str = "Mock SQL: CNC-001 had alarm with fault_code = 'FC-123' yesterday (API mock)."
            if "CNC-001" in original_query and "yesterday" in original_query and ("stop" in original_query or "downtime" in original_query or "analyze_downtime" == intent):
                 intermediate_data["fault_code_from_sql"] = 'FC-123'
        timings["sql_agent_run"] = time.time() - t_sql_start
        print(f"Time for sql_agent.run_sql_query: {timings['sql_agent_run']:.3f} seconds")


        # --- Step 2: Conditional KG Agent Call ---
        t_kg_start = time.time()
        kg_called = False
        extracted_fault_code = intermediate_data.get("fault_code_from_sql")
        
        if not _api_forced_mock_active and \
           (intent == "find_error_cause" or extracted_fault_code or (parameters and parameters.get("fault_code"))):
            
            code_to_query = extracted_fault_code or (parameters.get("fault_code") if parameters else None)
            
            if code_to_query:
                cypher_query_for_kg = "MATCH (f:Fault {code: $code})-[:CAUSED_BY|LINKED_TO_RECOMMENDATION*1..2]->(related) RETURN f.code AS fault_code, related.description AS related_info, labels(related) as related_type"
                query_params_for_kg = {'code': code_to_query}
            elif intent == "find_error_cause" and machine_id: 
                cypher_query_for_kg = "MATCH (m:Machine {id: $machine_id})-[:HAD_ALARM|EXPERIENCED_STATUS*1..2]->(event)-[:ASSOCIATED_WITH|SUGGESTS_CAUSE*0..1]->(cause) RETURN event.type AS event_type, event.description AS event_desc, cause.description AS possible_cause ORDER BY event.timestamp DESC LIMIT 5"
                query_params_for_kg = {'machine_id': machine_id}
            
            if cypher_query_for_kg != "N/A":
                kg_called = True
                log_message(f"Constructed Cypher query for KG Agent: {cypher_query_for_kg} with params {query_params_for_kg}")
                try:
                    kg_results = kg_agent.query(cypher_query_for_kg, params=query_params_for_kg)
                    if kg_results:
                        kg_context_str = f"Knowledge Graph found: {json.dumps(kg_results)}"
                    else:
                        kg_context_str = "No specific information found in Knowledge Graph for this query."
                    log_message(f"KG Agent Result: {kg_context_str[:200]}...")
                except Exception as e:
                    log_message(f"Error calling KG Agent: {e}")
                    kg_context_str = "Error retrieving data from Knowledge Graph."
            else:
                kg_context_str = "No specific KG query formulated for this intent/data."
        elif _api_forced_mock_active and extracted_fault_code == 'FC-123':
             kg_called = True # Simulate call for mock
             kg_context_str = "Mock KG: Fault FC-123 is caused by 'Sensor Malfunction' (API mock)."
        else:
            kg_context_str = "No KG query needed or conditions not met."
        
        if kg_called:
            timings["kg_agent_query"] = time.time() - t_kg_start
            print(f"Time for kg_agent.query: {timings['kg_agent_query']:.3f} seconds")
        else:
            timings["kg_agent_query"] = 0.0 # Not called


        # --- Step 3: Refined Vector Agent Call ---
        t_vector_start = time.time()
        if not _api_forced_mock_active:
            refined_search_terms = []
            if sql_data_str and "No specific data" not in sql_data_str and "Error retrieving" not in sql_data_str and "No SQL query was formulated" not in sql_data_str :
                refined_search_terms.append(f"Context from SQL: {sql_data_str[:500]}")
            if kg_context_str and "No specific information" not in kg_context_str and "Error retrieving" not in kg_context_str and "No KG query needed" not in kg_context_str:
                refined_search_terms.append(f"Context from KG: {kg_context_str[:300]}")

            if refined_search_terms:
                search_query_for_vector_db = f"{original_query} {' '.join(refined_search_terms)}"
            else:
                search_query_for_vector_db = original_query
            
            query_keywords_for_vector_db = [kw for kw in intent.split('_') if kw not in ["get", "fetch", "find"]]
            if machine_id: query_keywords_for_vector_db.append(machine_id)
            if parameters:
                for k,v in parameters.items():
                    if isinstance(v, str): query_keywords_for_vector_db.append(v)
                    if k in ["fault_code", "alarm_code", "kpi_name", "sensor_id"]: 
                        if isinstance(v, str): query_keywords_for_vector_db.append(v)
            if intermediate_data.get("fault_code_from_sql"):
                query_keywords_for_vector_db.append(intermediate_data["fault_code_from_sql"])
            
            query_keywords_for_vector_db = list(set(kw for kw in query_keywords_for_vector_db if kw and len(kw)>1))
            
            log_message(f"Refined search query for Vector Agent: '{search_query_for_vector_db[:300]}...', Keywords: {query_keywords_for_vector_db}")
            try:
                vector_search_results = vector_agent.hybrid_search(
                    query_text=search_query_for_vector_db, 
                    keywords=query_keywords_for_vector_db,
                    n_results=3
                )
                if vector_search_results and vector_search_results.get("documents") and vector_search_results["documents"][0]:
                    vector_results_docs = vector_search_results["documents"][0]
                    log_message(f"Vector Agent found {len(vector_results_docs)} documents.")
                else:
                    vector_results_docs = ["No relevant documents found in vector database for the refined query."]
                    log_message("No documents found by Vector Agent with refined query.")
            except Exception as e:
                log_message(f"Error calling Vector Agent: {e}")
                vector_results_docs = ["Error retrieving documents from vector database."]
        elif _api_forced_mock_active:
            vector_results_docs = ["Mock Vector DB: Found past issue log for FC-123 on CNC-001 (API mock)."]
        timings["vector_agent_search"] = time.time() - t_vector_start
        print(f"Time for vector_agent.hybrid_search: {timings['vector_agent_search']:.3f} seconds")


        # 4. Generate Response using LLMInterface, now with chat history
        t_gen_response_start = time.time()
        final_response_text = llm_interface.generate_response(
            sql_data=sql_data_str,
            kg_context=kg_context_str,
            vector_context=vector_results_docs,
            user_query=original_query,
            chat_history=chat_history_str
        )
        timings["llm_generate_response"] = time.time() - t_gen_response_start
        print(f"Time for llm_interface.generate_response: {timings['llm_generate_response']:.3f} seconds")

        # 5. Save context to memory
        user_memory.save_context(
            {user_memory.input_key: original_query}, 
            {user_memory.output_key: final_response_text}
        )
        log_message(f"Saved context for user '{user_id}'.")
        
        timings["total_endpoint_duration"] = time.time() - endpoint_start_time
        print(f"Total time for process_query_endpoint: {timings['total_endpoint_duration']:.3f} seconds")

        # 6. Return Response
        return QueryResponse(
            answer=final_response_text,
            parsed_intent=parsed_query_data,
            debug_info={
                "original_query": original_query,
                "chat_history_provided_to_llm": chat_history_str[:1000] + "..." if len(chat_history_str) > 1000 else chat_history_str,
                "question_to_sql_agent": question_for_sql_agent,
                "sql_agent_few_shot_examples_used": sql_examples_used_info if 'sql_examples_used_info' in locals() and question_for_sql_agent != "N/A" else "N/A",
                "cypher_query_to_kg_agent": cypher_query_for_kg,
                "params_for_kg_agent": query_params_for_kg if cypher_query_for_kg != "N/A" else "N/A",
                "refined_query_to_vector_agent": search_query_for_vector_db[:500] + "..." if len(search_query_for_vector_db) > 500 else search_query_for_vector_db,
                "keywords_for_vector_agent": query_keywords_for_vector_db,
                "sql_agent_response_snippet": sql_data_str[:1000] + "..." if len(sql_data_str) > 1000 else sql_data_str,
                "kg_agent_response_snippet": kg_context_str[:1000] + "..." if len(kg_context_str) > 1000 else kg_context_str,
                "vector_agent_response_docs": vector_results_docs, 
                "fault_code_from_sql_for_kg": intermediate_data.get("fault_code_from_sql", "N/A"),
                "api_forced_mocks_active": _api_forced_mock_active,
                "llm_interface_is_mock": getattr(llm_interface, 'use_mock', _api_forced_mock_active),
                "core_modules_imported": CORE_MODULES_IMPORTED,
                "performance_timings_seconds": {k: f"{v:.3f}" for k, v in timings.items()}
            }
        )

    except Exception as e:
        print(f"Error processing query: {e}")
        import traceback
        traceback.print_exc() 
        # Add timings to error response if available
        if timings: 
            print(f"Timings before error: {timings}")
        timings["total_endpoint_duration_on_error"] = time.time() - endpoint_start_time
        print(f"Total time for process_query_endpoint before error: {timings['total_endpoint_duration_on_error']:.3f} seconds")
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}. Timings: {timings}")


@app.get("/")
async def root():
    return {"message": "Welcome to the Smart Factory AI Assistant API. Use the /process-query/ endpoint to ask questions."}

# --- Uvicorn Runner ---
if __name__ == "__main__":
    # This block allows running the app directly using `python main.py`
    # Uvicorn will serve the FastAPI app at http://0.0.0.0:8000
    # Note: sys.path adjustments at the top are crucial for this to work smoothly if agents are in a sub-package.
    print("Starting FastAPI server with Uvicorn...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
    # Alternatively, to run with reload for development:
    # uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, reload_dirs=[os.path.dirname(os.path.abspath(__file__)), os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "agents")])
    # The reload_dirs would need careful path setup. For now, basic run.

# To run this app:
# 1. Ensure all dependencies are installed (fastapi, uvicorn, pydantic, and agent dependencies like langchain, neo4j, chromadb, etc.)
# 2. Navigate to the `smart-factory-app/api/` directory in your terminal.
# 3. Run the command: `python main.py`
#    or for development with auto-reload: `uvicorn main:app --reload`
#    (Ensure your terminal's working directory is `smart-factory-app/api/` for `uvicorn main:app --reload` to work directly,
#     or specify the app path like `uvicorn smart_factory_app.api.main:app --reload` from the project root if PYTHONPATH is set up)

# --- Helper for logging within the endpoint ---
def log_message(message: str):
    """Utility function to print log messages from the endpoint."""
    print(f"[API Endpoint Log] {message}")
