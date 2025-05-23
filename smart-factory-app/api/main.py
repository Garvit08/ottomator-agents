import os
import sys
import json
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn

# --- Path Adjustments ---
# Ensure 'smart_factory_app' and its submodules can be found.
# If this script (main.py) is in smart-factory-app/api/,
# and other modules are in smart-factory-app/agents, smart-factory-app/config
# then we need to add the parent of 'smart_factory_app' to sys.path for `from smart_factory_app...` imports.
current_api_dir = os.path.dirname(os.path.abspath(__file__)) # .../api
smart_factory_app_root = os.path.abspath(os.path.join(current_api_dir, '..')) # .../smart-factory-app
project_root_dir = os.path.abspath(os.path.join(smart_factory_app_root, '..')) # Parent of smart_factory_app

if project_root_dir not in sys.path:
    sys.path.insert(0, project_root_dir) # Allows `from smart_factory_app.config import ...`

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


# --- Pydantic Models ---
class UserQuery(BaseModel):
    query: str
    user_id: str = "default_user" # Optional: for future use like personalization

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
    original_query = user_query.query
    print(f"\nReceived query: '{original_query}' from user: '{user_query.user_id}'")

    try:
        # 1. Parse Query using LLMInterface
        parsed_query_data = llm_interface.parse_query(original_query)
        intent = parsed_query_data.get("intent", "unknown")
        machine_id = parsed_query_data.get("machine_id")
        timestamp_info = parsed_query_data.get("timestamp") or parsed_query_data.get("timestamp_range")
        parameters = parsed_query_data.get("parameters")
        
        print(f"Parsed query intent: {intent}, Machine: {machine_id}, Time: {timestamp_info}, Params: {parameters}")

        # 2. Orchestration Logic (Simplified with placeholders for now)
        sql_data_str: str = "No SQL data fetched."
        kg_context_str: str = "No KG context fetched."
        vector_results_docs: list = []

        # --- Mocked/Placeholder Data Generation ---
        # This section will be replaced with actual agent calls in subsequent tasks.
        if intent == "fetch_oee" and machine_id:
            # Placeholder SQL query for OEE
            mock_sql_query = f"SELECT oee, timestamp FROM production_metrics WHERE machine_id = '{machine_id}' AND timestamp = '{timestamp_info}';"
            sql_data_str = f"Mock SQL Data: OEE for {machine_id} on {timestamp_info} is 85%. (Query: {mock_sql_query})"
            
            # Placeholder KG query for machine details
            mock_kg_query = f"MATCH (m:Machine {{id: '{machine_id}'}})-[:HAS_PARAMETER]->(p:Parameter {{name: 'OEE_target'}}) RETURN p.value;"
            kg_context_str = f"Mock KG Data: {machine_id} has an OEE target of 90%. (Query: {mock_kg_query})"
            
            # Placeholder Vector search for related documents
            vector_search_query = f"OEE issues and solutions for {machine_id}"
            vector_results = vector_agent.semantic_search(query_text=vector_search_query, n_results=1) # Using mock or real
            if vector_results and vector_results.get("documents") and vector_results["documents"][0]:
                vector_results_docs = vector_results["documents"][0]
            else:
                vector_results_docs = ["No relevant documents found in vector store for OEE of " + machine_id]


        elif intent == "get_downtime_summary" and machine_id:
            mock_sql_query = f"SELECT start_time, end_time, reason FROM downtime_logs WHERE machine_id = '{machine_id}' AND event_date = '{timestamp_info}';"
            sql_data_str = f"Mock SQL Data: {machine_id} had 2 downtimes on {timestamp_info}: 30m (sensor), 15m (jam). (Query: {mock_sql_query})"
            
            mock_kg_query = f"MATCH (m:Machine {{id: '{machine_id}'}})-[:EXPERIENCED_EVENT]->(e:DowntimeEvent {{timestamp: '{timestamp_info}'}})-[:CAUSED_BY]->(f:Fault) RETURN f.description, f.recommended_action;"
            kg_context_str = f"Mock KG Data: Downtime for {machine_id} linked to Fault F-102 (Sensor malfunction). (Query: {mock_kg_query})"
            
            vector_search_query = f"downtime reasons and troubleshooting for {machine_id}"
            vector_results = vector_agent.semantic_search(query_text=vector_search_query, n_results=1)
            if vector_results and vector_results.get("documents") and vector_results["documents"][0]:
                vector_results_docs = vector_results["documents"][0]
            else:
                vector_results_docs = ["No relevant documents found for downtime of " + machine_id]

        else: # General query or intent not specifically handled by mocks above
            sql_data_str = "Mock SQL: General factory status - All systems nominal."
            kg_context_str = "Mock KG: Factory has 3 production lines. Line A is for product X."
            vector_results = vector_agent.semantic_search(query_text=original_query, n_results=1)
            if vector_results and vector_results.get("documents") and vector_results["documents"][0]:
                vector_results_docs = vector_results["documents"][0]
            else:
                vector_results_docs = ["No specific documents found for this general query."]


        # 3. Generate Response using LLMInterface
        final_response_text = llm_interface.generate_response(
            sql_data=sql_data_str,
            kg_context=kg_context_str,
            vector_context=vector_results_docs,
            user_query=original_query
        )

        # 4. Return Response
        return QueryResponse(
            answer=final_response_text,
            parsed_intent=parsed_query_data,
            debug_info={
                "original_query": original_query,
                "retrieved_sql_data": sql_data_str,
                "retrieved_kg_context": kg_context_str,
                "retrieved_vector_docs": vector_results_docs,
                "api_forced_mocks_active": _api_forced_mock_active,
                "llm_interface_using_mock": getattr(llm_interface, 'use_mock', _api_forced_mock_active), # Check actual status of llm_interface
                "core_modules_imported": CORE_MODULES_IMPORTED
            }
        )

    except Exception as e:
        print(f"Error processing query: {e}")
        import traceback
        traceback.print_exc() # Print full traceback to console for debugging
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")


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
