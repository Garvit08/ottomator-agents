# smart_factory_app/api/api_utils.py
"""Initializes and configures shared services for the Smart Factory API.

This module handles the setup of various agents (LLM, KG, Vector, SQL)
and other utilities like conversation memory management and debug information
assembly. It centralizes service instantiation to be imported by other
API modules, primarily main.py.
"""

import os
import sys
import json
from langchain.memory import ConversationBufferWindowMemory
from typing import Dict, Optional, Any, List # Added List for build_debug_info

# --- Agent and Core Module Imports ---
# Attempt to import all necessary agent classes and configuration.
# Fallback mocks are defined if core components are unavailable.
try:
    from smart_factory_app.agents.llm_interface import LLMInterface
    from smart_factory_app.agents.sql_agent import run_sql_query as actual_run_sql_query
    from smart_factory_app.agents.kg_agent import KGAgent
    from smart_factory_app.agents.vector_agent import VectorAgent
    from smart_factory_app.config.config import (
        API_USE_MOCK_AGENTS,
        OLLAMA_MODEL, OLLAMA_BASE_URL,
        NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD,
        SENTENCE_TRANSFORMER_MODEL, VECTOR_COLLECTION_NAME, CHROMA_PERSIST_PATH
    )
    CORE_MODULES_IMPORTED = True
    """Flag indicating if essential application modules were successfully imported."""
except ImportError as e:
    print(f"Critical Error (api_utils): Failed to import core modules or config: {e}.")
    CORE_MODULES_IMPORTED = False
    API_USE_MOCK_AGENTS = True # Force mocks if imports failed

    # Fallback mock definitions for core components if imports fail
    class LLMInterface: # type: ignore
        """Fallback mock for LLMInterface."""
        def __init__(self, *args: Any, **kwargs: Any) -> None: print("Fallback Mock LLMInterface created (api_utils).")
        def parse_query(self, q: Any) -> Dict[str, Any]: return {"intent": "mock_fallback_intent"}
        def generate_response(self, *args: Any, **kwargs: Any) -> str: return "Fallback mock LLM response (api_utils)."

    def actual_run_sql_query(q: Any, parsed_query_dict: Optional[Dict[str, Any]] = None) -> Any: # type: ignore
        """Fallback mock for the actual run_sql_query function."""
        return "Fallback mock SQL response (api_utils)."

    class KGAgent: # type: ignore
        """Fallback mock for KGAgent."""
        def __init__(self, *args: Any, **kwargs: Any) -> None: print("Fallback Mock KGAgent created (api_utils).")
        def query(self, q: Any, p: Optional[Dict[str,Any]] = None) -> list: return []
        def close(self) -> None: pass

    class VectorAgent: # type: ignore
        """Fallback mock for VectorAgent."""
        def __init__(self, *args: Any, **kwargs: Any) -> None: print("Fallback Mock VectorAgent created (api_utils).")
        def semantic_search(self, q: Any, n_results: int =1) -> Dict[str, Any]: return {"documents": [["Fallback mock vector doc (api_utils)"]]}

# --- Service Initialization ---
# This section initializes agent instances based on configuration (real or mock).
# These instances are then imported by other modules (e.g., main.py, query_orchestrator.py).

_api_forced_mock_active: bool = False
"""Flag indicating if API-level mocks are forced via config or due to import failures."""

llm_interface: Optional[LLMInterface] = None
"""Instance of LLMInterface, responsible for LLM interactions (parsing, response generation)."""

kg_agent_instance: Optional[KGAgent] = None
"""Instance of KGAgent, responsible for Knowledge Graph interactions."""

vector_agent_instance: Optional[VectorAgent] = None
"""Instance of VectorAgent, responsible for Vector Database interactions."""

run_sql_query = actual_run_sql_query
"""
Function for executing SQL queries. Points to the actual `run_sql_query` from
`sql_agent.py` or a mock version if `API_USE_MOCK_AGENTS` is true.
"""

if API_USE_MOCK_AGENTS or not CORE_MODULES_IMPORTED:
    print("API Utils: Using MOCK agents (due to API_USE_MOCK_AGENTS=True or import failures).")
    _api_forced_mock_active = True
    llm_interface = LLMInterface(use_mock=True)

    def mock_run_sql_query_api_utils(query_text: str, parsed_query_dict: Optional[Dict[str, Any]] = None) -> Any:
        """Mock SQL query function for API testing."""
        return f"API Mock SQL result for query (from api_utils): {query_text}"
    run_sql_query = mock_run_sql_query_api_utils

    if not CORE_MODULES_IMPORTED:
        kg_agent_instance = KGAgent()
        vector_agent_instance = VectorAgent()
    else:
        if KGAgent is not None :
            kg_agent_instance = KGAgent(use_mock=True) if hasattr(KGAgent, 'use_mock') else KGAgent()
        if VectorAgent is not None :
            vector_agent_instance = VectorAgent(use_mock=True) if hasattr(VectorAgent, 'use_mock') else VectorAgent()
else:
    print("API Utils: Attempting to initialize REAL agents...")
    try:
        llm_interface = LLMInterface()
        kg_agent_instance = KGAgent()
        vector_agent_instance = VectorAgent()

        if 'smart_factory_app.agents.sql_agent' in sys.modules:
            sql_agent_module = sys.modules['smart_factory_app.agents.sql_agent']
            if hasattr(sql_agent_module, 'llm') and sql_agent_module.llm is None:
                print("API Utils: Warning - LLM for SQL Agent (OpenAI placeholder) is not initialized.")
        print("API Utils: REAL agents initialized successfully.")
    except Exception as e:
        print(f"API Utils: Error initializing REAL agents: {e}. Critical failure.")
        print("API Utils: Falling back to MOCK agents due to REAL initialization failure.")
        _api_forced_mock_active = True
        llm_interface = LLMInterface(use_mock=True)

        def failed_real_sql_run_sql_query(query_text: str, parsed_query_dict: Optional[Dict[str, Any]] = None) -> Any:
            return f"API Mock SQL result (due to real init fail in api_utils): {query_text}"
        run_sql_query = failed_real_sql_run_sql_query

        kg_agent_instance = KGAgent(use_mock=True) if KGAgent and hasattr(KGAgent, 'use_mock') else (KGAgent() if KGAgent else None)
        vector_agent_instance = VectorAgent(use_mock=True) if VectorAgent and hasattr(VectorAgent, 'use_mock') else (VectorAgent() if VectorAgent else None)

# --- Conversation Memory Management ---
conversation_memory_store: Dict[str, ConversationBufferWindowMemory] = {}
"""Global store for user-specific conversation memories."""

def get_user_memory(user_id: str) -> ConversationBufferWindowMemory:
    """
    Retrieves or creates a conversation memory instance for a given user.

    Args:
        user_id (str): The unique identifier for the user.

    Returns:
        ConversationBufferWindowMemory: The conversation memory object for the user.
    """
    if user_id not in conversation_memory_store:
        conversation_memory_store[user_id] = ConversationBufferWindowMemory(
            k=3, memory_key="history", input_key="input", output_key="output", return_messages=False
        )
    return conversation_memory_store[user_id]

# --- Debug Info Builder ---
def build_debug_info(
    original_query: str,
    chat_history_str: str,
    parsed_query_data: Dict[str, Any],
    orchestrator_context: Dict[str, Any],
    api_level_timings: Dict[str, float],
    api_forced_mock_active: bool,
    llm_interface_is_mock: bool,
    core_modules_imported: bool
) -> Dict[str, Any]:
    """Constructs the debug_info dictionary for the API response.

    This function consolidates all debugging information from various stages
    of query processing, including initial parsing, orchestration steps,
    and overall performance timings.

    Args:
        original_query: The original user query string.
        chat_history_str: The stringified chat history provided to the LLM.
        parsed_query_data: The structured output from the initial query parsing
                           step (e.g., from `llm_interface.parse_query`).
        orchestrator_context: A dictionary containing context and results from
                              the `QueryOrchestrator`'s processing flow. This includes
                              details of calls to SQL, KG, and Vector agents.
        api_level_timings: A dictionary of performance timings (float values)
                           recorded at the API endpoint level (e.g., `parse_query`
                           duration, `orchestration_flow` duration).
        api_forced_mock_active: Boolean flag indicating if API-level mocks were
                                 forced (e.g., by config or import failures).
        llm_interface_is_mock: Boolean flag indicating if the `llm_interface`
                               used for parsing was operating in mock mode.
        core_modules_imported: Boolean flag indicating if core application modules
                               were successfully imported.

    Returns:
        A dictionary containing comprehensive debug information suitable for
        inclusion in the API response.
    """

    formatted_api_timings = {k: f"{v:.3f}" for k, v in api_level_timings.items()}

    debug_info = {
        **orchestrator_context,
        "original_query": original_query,
        "parsed_intent_details": parsed_query_data, # From the initial parse_query call

        "api_forced_mocks_active": api_forced_mock_active,
        "llm_interface_parser_is_mock": llm_interface_is_mock,
        "core_modules_imported": core_modules_imported,
        "performance_timings_seconds": formatted_api_timings
    }

    # Standardize chat history representation in debug info
    # The orchestrator_context might have "chat_history_provided_to_llm_parse"
    # This function receives chat_history_str which is typically the one used for response generation.
    # For clarity, let's ensure a consistent key.
    debug_info["chat_history_snippet"] = chat_history_str[:1000] + "..." if len(chat_history_str) > 1000 else chat_history_str
    debug_info.pop("chat_history_provided_to_llm", None) # Remove if also passed in orchestrator_context under this name
    debug_info.pop("chat_history_provided_to_llm_parse", None) # Remove if also passed in orchestrator_context

    return debug_info
