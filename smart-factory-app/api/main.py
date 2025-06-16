# smart_factory_app/api/main.py
"""FastAPI application for the Smart Factory AI Assistant.

This module defines the main FastAPI application, including API endpoints
for processing user queries. It orchestrates calls to various backend services
(LLM, SQL, KG, Vector DB) via the QueryOrchestrator and manages conversation
history. Shared service initializations (agents, memory store) are imported
from api_utils.py.
"""

import json
import time
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field # Added Field for Pydantic model descriptions
import uvicorn

from langchain.memory import ConversationBufferWindowMemory # Used in api_utils, but type hint here is fine
from typing import Optional, Dict, Any # Added Any for parsed_intent

# --- Pydantic Models ---
class UserQuery(BaseModel):
    """Represents a user's query to the API.

    Attributes:
        query: The natural language query string from the user.
        user_id: A unique identifier for the user, used for session management
                 and retrieving conversation history. Defaults to "default_user".
    """
    query: str = Field(..., description="The natural language query from the user.")
    user_id: str = Field("default_user", description="Identifier for the user, for session and history.")
    # session_id: Optional[str] = None # Example for future extension

class QueryResponse(BaseModel):
    """Represents the API's response to a user query.

    Attributes:
        answer: The final, synthesized natural language answer from the LLM.
        parsed_intent: A dictionary containing the structured information
                       extracted from the user's query by the LLM (e.g., intent,
                       entities, parameters).
        debug_info: A dictionary containing detailed information about the
                    query processing steps, including intermediate data from
                    agents, timings, and status flags.
    """
    answer: str = Field(..., description="The final, synthesized answer from the LLM.")
    parsed_intent: Dict[str, Any] = Field(..., description="Structured information extracted from the user's query.")
    debug_info: Dict[str, Any] = Field(..., description="Detailed debug information about the request processing.")


# --- FastAPI App Instance ---
app = FastAPI(
    title="Smart Factory AI Assistant API",
    description="API for processing natural language queries related to factory operations, "
                "integrating various data sources and AI agents.",
    version="0.1.1" # Updated version
)
"""The main FastAPI application instance."""

# --- Imports from api_utils ---
# These services (agents, memory functions) are initialized in api_utils.py
# to keep this main file cleaner and focus on endpoint logic.
from smart_factory_app.api.api_utils import (
    llm_interface,
    kg_agent_instance as kg_agent,
    vector_agent_instance as vector_agent,
    run_sql_query,
    get_user_memory,
    _api_forced_mock_active,
    CORE_MODULES_IMPORTED,
    build_debug_info
)
from smart_factory_app.api.query_orchestrator import QueryOrchestrator

# --- Instantiate Query Orchestrator ---
# The orchestrator handles the logic of calling different agents (SQL, KG, Vector)
# based on the parsed query.
orchestrator = QueryOrchestrator(
    llm_interface=llm_interface, # Used by orchestrator for its internal response generation step
    sql_agent_func=run_sql_query,
    kg_agent=kg_agent,
    vector_agent=vector_agent,
    api_forced_mock_active=_api_forced_mock_active
)
"""Global instance of the QueryOrchestrator."""

# --- API Endpoints ---
@app.post("/process-query/", response_model=QueryResponse)
async def process_query_endpoint(user_query: UserQuery):
    """Processes a user's natural language query.

    This endpoint takes a user's query, retrieves conversation history,
    parses the query to understand intent and entities, then uses the
    QueryOrchestrator to gather context from various data sources (SQL, KG,
    Vector DB). Finally, it generates a synthesized natural language response
    and returns it along with debug information.

    Args:
        user_query: An instance of `UserQuery` containing the user's query
                    string and user ID.

    Returns:
        QueryResponse: An object containing the answer, parsed intent, and
                       detailed debug information.

    Raises:
        HTTPException: If any critical error occurs during processing.
    """
    endpoint_start_time = time.time()
    timings = {} # For API-level timings

    original_query = user_query.query
    user_id = user_query.user_id
    log_message(f"\nReceived query: '{original_query}' from user: '{user_id}'")

    try:
        # 1. Load Conversation History
        user_memory = get_user_memory(user_id)
        loaded_memory_vars = user_memory.load_memory_variables({})
        chat_history_str = loaded_memory_vars.get(user_memory.memory_key, "")
        log_message(f"Loaded chat history for user '{user_id}':\n{chat_history_str if chat_history_str else 'No history available.'}")

        # 2. Parse Query (using llm_interface from api_utils)
        t_parse_start = time.time()
        # This llm_interface is primarily for parsing the query here.
        # The orchestrator uses its own llm_interface instance for response generation.
        parsed_query_data = llm_interface.parse_query(original_query, chat_history=chat_history_str)
        timings["parse_query"] = time.time() - t_parse_start
        log_message(f"Time for llm_interface.parse_query: {timings['parse_query']:.3f} seconds")
        log_message(f"Parsed query data (main.py): {parsed_query_data}")

        # 3. Orchestrate Agent Calls and Generate Response
        orchestration_start_time = time.time()
        final_response_text, collected_orchestrator_debug_info = orchestrator.process_query_flow(
            parsed_query_data=parsed_query_data,
            original_query=original_query,
            chat_history=chat_history_str
        )
        timings["orchestration_flow"] = time.time() - orchestration_start_time
        log_message(f"Time for orchestrator.process_query_flow: {timings['orchestration_flow']:.3f} seconds")

        # 4. Save context to memory
        user_memory.save_context(
            {user_memory.input_key: original_query},
            {user_memory.output_key: final_response_text}
        )
        log_message(f"Saved context for user '{user_id}'.")

        timings["total_endpoint_duration"] = time.time() - endpoint_start_time
        log_message(f"Total time for process_query_endpoint: {timings['total_endpoint_duration']:.3f} seconds")

        # 5. Construct and Return Response
        final_debug_info = build_debug_info(
            original_query=original_query,
            chat_history_str=chat_history_str,
            parsed_query_data=parsed_query_data,
            orchestrator_context=collected_orchestrator_debug_info,
            api_level_timings=timings,
            api_forced_mock_active=_api_forced_mock_active,
            llm_interface_is_mock=getattr(llm_interface, 'use_mock', _api_forced_mock_active),
            core_modules_imported=CORE_MODULES_IMPORTED
        )

        return QueryResponse(
            answer=final_response_text,
            parsed_intent=parsed_query_data,
            debug_info=final_debug_info
        )

    except Exception as e:
        log_message(f"Error processing query: {e}")
        import traceback
        traceback.print_exc()
        # Add timings to error response if available
        if timings:
            timings["total_endpoint_duration_on_error"] = time.time() - endpoint_start_time
            log_message(f"Timings before error: {timings}")
            log_message(f"Total time for process_query_endpoint before error: {timings['total_endpoint_duration_on_error']:.3f} seconds")
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}. Timings (if available): {timings}")


@app.get("/")
async def root():
    """Root endpoint for basic API health check."""
    return {"message": "Welcome to the Smart Factory AI Assistant API. Use the /process-query/ endpoint to ask questions."}

# --- Uvicorn Runner ---
if __name__ == "__main__":
    # This block allows running the app directly using `python main.py`
    # Uvicorn will serve the FastAPI app at http://0.0.0.0:8000
    print("Starting FastAPI server with Uvicorn...")
    uvicorn.run(app, host="0.0.0.0", port=8000)

# --- Helper for logging within the endpoint ---
def log_message(message: str):
    """Prints a formatted log message to the console from the API endpoint.

    Args:
        message: The message string to log.
    """
    print(f"[API Endpoint Log] {message}")
