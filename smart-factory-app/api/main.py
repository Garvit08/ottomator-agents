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
        search_query_for_vector_db = original_query # Default
        query_keywords_for_vector_db = []


        # --- Step 1: Initial SQL Agent Call (if applicable) ---
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
                # Generic question formulation for other intents needing SQL
                question_for_sql_agent = f"Regarding user query '{original_query}', provide relevant information from SQL tables. Focus on intent '{intent}'"
                if machine_id: question_for_sql_agent += f", machine '{machine_id}'"
                if timestamp_info: question_for_sql_agent += f", around time '{timestamp_info}'"
                if parameters: question_for_sql_agent += f", with parameters: {json.dumps(parameters)}"
            else: # General query or intent that might not directly map to a structured SQL query via agent
                question_for_sql_agent = f"Investigate based on user query: {original_query}. Parsed intent: {intent}, machine: {machine_id}, time: {timestamp_info}, params: {parameters}."

            if question_for_sql_agent != "N/A": # Check if a question was actually formulated
                log_message(f"Constructed question for SQL Agent: {question_for_sql_agent}")
                try:
                    sql_data_result = run_sql_query(question_for_sql_agent)
                    sql_data_str = str(sql_data_result) if sql_data_result else "No specific data found from SQL for this query."
                    log_message(f"SQL Agent Result: {sql_data_str[:300]}...") 
                    
                    # --- Simple example of extracting info from SQL for conditional KG call ---
                    # This is a placeholder for actual parsing of sql_data_str.
                    # In a real scenario, sql_agent might return structured data or LLM would parse its output.
                    if "fault_code = 'FC-123'" in sql_data_str or (parameters and parameters.get("fault_code") == 'FC-123'): # Example check
                        intermediate_data["fault_code_from_sql"] = 'FC-123'
                    elif "alarm_code: ALM001" in sql_data_str: # Another example
                        intermediate_data["fault_code_from_sql"] = 'ALM001' # Assuming alarm code is a fault code

                except Exception as e:
                    log_message(f"Error calling SQL Agent: {e}")
                    sql_data_str = "Error retrieving data from SQL database."
        elif _api_forced_mock_active:
            sql_data_str = "Mock SQL: CNC-001 had alarm with fault_code = 'FC-123' yesterday (API mock)."
            if "CNC-001" in original_query and "yesterday" in original_query and ("stop" in original_query or "downtime" in original_query or "analyze_downtime" == intent):
                 intermediate_data["fault_code_from_sql"] = 'FC-123' # Simulate finding fault code for mock scenario


        # --- Step 2: Conditional KG Agent Call ---
        # Based on intent or data from SQL (e.g., a fault_code)
        extracted_fault_code = intermediate_data.get("fault_code_from_sql")
        
        if not _api_forced_mock_active and \
           (intent == "find_error_cause" or extracted_fault_code or (parameters and parameters.get("fault_code"))):
            
            code_to_query = extracted_fault_code or (parameters.get("fault_code") if parameters else None)
            query_params = {}

            if code_to_query:
                cypher_query_for_kg = "MATCH (f:Fault {code: $code})-[:CAUSED_BY|LINKED_TO_RECOMMENDATION*1..2]->(related) RETURN f.code AS fault_code, related.description AS related_info, labels(related) as related_type"
                query_params = {'code': code_to_query}
            elif intent == "find_error_cause" and machine_id: 
                cypher_query_for_kg = "MATCH (m:Machine {id: $machine_id})-[:HAD_ALARM|EXPERIENCED_STATUS*1..2]->(event)-[:ASSOCIATED_WITH|SUGGESTS_CAUSE*0..1]->(cause) RETURN event.type AS event_type, event.description AS event_desc, cause.description AS possible_cause ORDER BY event.timestamp DESC LIMIT 5"
                query_params = {'machine_id': machine_id}
            
            if cypher_query_for_kg != "N/A":
                log_message(f"Constructed Cypher query for KG Agent: {cypher_query_for_kg} with params {query_params}")
                try:
                    kg_results = kg_agent.query(cypher_query_for_kg, params=query_params)
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
             kg_context_str = "Mock KG: Fault FC-123 is caused by 'Sensor Malfunction' (API mock)."
        else:
            kg_context_str = "No KG query needed or conditions not met."


        # --- Step 3: Refined Vector Agent Call ---
        # Augment search query with insights from SQL/KG if available
        if not _api_forced_mock_active:
            refined_search_terms = []
            if sql_data_str and "No specific data" not in sql_data_str and "Error retrieving" not in sql_data_str:
                # Simple refinement: just append non-empty SQL string.
                # A more advanced method would be to summarize SQL output here if it's too long.
                refined_search_terms.append(f"Context from SQL: {sql_data_str[:500]}") # Limit length
            if kg_context_str and "No specific information" not in kg_context_str and "Error retrieving" not in kg_context_str:
                refined_search_terms.append(f"Context from KG: {kg_context_str[:300]}")

            if refined_search_terms:
                search_query_for_vector_db = f"{original_query} {' '.join(refined_search_terms)}"
            else: # Fallback to original query
                search_query_for_vector_db = original_query
            
            # Keywords: machine_id, key parameters, parts of intent.
            query_keywords_for_vector_db = [kw for kw in intent.split('_') if kw not in ["get", "fetch", "find"]]
            if machine_id: query_keywords_for_vector_db.append(machine_id)
            if parameters:
                for k,v in parameters.items():
                    if isinstance(v, str): query_keywords_for_vector_db.append(v)
                    # Add specific important keys like 'fault_code', 'kpi_name'
                    if k in ["fault_code", "alarm_code", "kpi_name", "sensor_id"]: 
                        if isinstance(v, str): query_keywords_for_vector_db.append(v)
            if intermediate_data.get("fault_code_from_sql"):
                query_keywords_for_vector_db.append(intermediate_data["fault_code_from_sql"])
            
            query_keywords_for_vector_db = list(set(kw for kw in query_keywords_for_vector_db if kw and len(kw)>1)) # Basic filtering
            
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
                # Inputs to Agents
                "question_to_sql_agent": question_for_sql_agent,
                "cypher_query_to_kg_agent": cypher_query_for_kg,
                "params_for_kg_agent": query_params if 'query_params' in locals() and cypher_query_for_kg != "N/A" else "N/A",
                "refined_query_to_vector_agent": search_query_for_vector_db[:500] + "..." if len(search_query_for_vector_db) > 500 else search_query_for_vector_db,
                "keywords_for_vector_agent": query_keywords_for_vector_db,
                # Outputs from Agents (or error/default messages)
                "sql_agent_response_snippet": sql_data_str[:1000] + "..." if len(sql_data_str) > 1000 else sql_data_str,
                "kg_agent_response_snippet": kg_context_str[:1000] + "..." if len(kg_context_str) > 1000 else kg_context_str,
                "vector_agent_response_docs": vector_results_docs, # Already a list of docs, usually snippets
                # Intermediate data for context
                "fault_code_from_sql_for_kg": intermediate_data.get("fault_code_from_sql", "N/A"),
                # Status Flags
                "api_forced_mocks_active": _api_forced_mock_active,
                "llm_interface_is_mock": getattr(llm_interface, 'use_mock', _api_forced_mock_active),
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
