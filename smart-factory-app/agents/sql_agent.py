import os
import sys
import time # Added for performance timing
from sqlalchemy import create_engine
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain_community.utilities import SQLDatabase
from langchain_openai import OpenAI # Placeholder LLM
from langchain.agents import create_sql_agent
from langchain.agents.agent_types import AgentType
from typing import Optional, Dict, Any # For type hinting

# Adjust path to import config and utils if necessary
# For package execution, this might not be needed if PYTHONPATH is set correctly
# or the calling script handles paths.
current_dir_sql_agent = os.path.dirname(os.path.abspath(__file__))
project_root_sql_agent = os.path.abspath(os.path.join(current_dir_sql_agent, '..', '..')) 
# Example: /app/smart-factory-app if script is in /app/smart-factory-app/agents
# Add project_root_sql_agent to sys.path if smart_factory_app is the top-level package
# If smart_factory_app is in /app, then add /app to sys.path
# Let's assume 'smart_factory_app' is the package name, and its parent should be in path
# For direct script run:
if project_root_sql_agent not in sys.path:
    # This makes `from smart_factory_app.config...` work
    sys.path.insert(0, project_root_sql_agent) 

try:
    from smart_factory_app.config.config import DATABASE_URI, OLLAMA_MODEL, OLLAMA_BASE_URL # Using Ollama for consistency, though OpenAI was placeholder
    # Note: The original SQL agent used OpenAI. We'll switch to Ollama for consistency with llm_interface
    # or ideally, the LLM choice itself should be part of config. For now, let's use Ollama details.
    # If a specific OpenAI key is needed, that should also come from config.
    # For this example, we will use the OLLAMA_MODEL and BASE_URL for the placeholder LLM,
    # assuming it's compatible or that the LLM used here is also configurable.
    # The original OpenAI() call needs OPENAI_API_KEY. Let's keep it simple and assume
    # the LLM below (OpenAI) is a placeholder that doesn't strictly need the key for this structure.
    # Or better, we should use the Ollama instance from config for the agent too.
    # For now, we keep OpenAI() as it was, but acknowledge this discrepancy.
    # Ideal: llm_choice = config.SQL_AGENT_LLM_TYPE; if llm_choice == "openai": llm = OpenAI(...) etc.
    # For this refactor, we focus on DATABASE_URI. LLM part is more complex.
    from smart_factory_app.agents.sql_agent_utils import get_relevant_sql_examples # Added import
except ImportError:
    print("Error importing config or sql_agent_utils. Ensure PYTHONPATH is set or paths are correct.")
    # Fallback for DATABASE_URI if config import fails (not ideal for production)
    DB_HOST_FALLBACK = os.getenv("DB_HOST", "localhost")
    DB_PORT_FALLBACK = os.getenv("DB_PORT", "5432")
    DB_USER_FALLBACK = os.getenv("DB_USER", "postgres")
    DB_PASSWORD_FALLBACK = os.getenv("DB_PASSWORD", "password")
    DB_NAME_FALLBACK = os.getenv("DB_NAME", "smart_factory_db")
    DATABASE_URI = f"postgresql+psycopg2://{DB_USER_FALLBACK}:{DB_PASSWORD_FALLBACK}@{DB_HOST_FALLBACK}:{DB_PORT_FALLBACK}/{DB_NAME_FALLBACK}"
    OLLAMA_MODEL = "mistral" # Fallback
    # OPENAI_API_KEY_FALLBACK = os.getenv("OPENAI_API_KEY") # if using OpenAI


# Initialize LLM (Placeholder - as it was in original)
# This part remains a bit problematic as it's not using the Ollama from config directly
# like llm_interface.py does. This implies sql_agent might use a different LLM.
# For a truly unified setup, this LLM should also be configured via config.py.
try:
    # If OPENAI_API_KEY is not set, this will fail.
    # To make it runnable without an API key for now (like other mocks):
    # One option is to use a MockLLM if the key is not present, or rely on Ollama.
    # Given the task is about config centralization, we'll leave this as is but note it.
    if os.getenv("OPENAI_API_KEY"):
        llm = OpenAI(temperature=0)
    else:
        print("OPENAI_API_KEY not found. SQL Agent's LLM will be None. Agent may not function.")
        llm = None
except Exception as e:
    print(f"Error initializing LLM for SQL Agent (OpenAI): {e}")
    llm = None # Set llm to None if initialization fails

db = None
toolkit = None
agent_executor = None

try:
    # Initialize SQLDatabase object
    db_engine = create_engine(DATABASE_URI)
    db = SQLDatabase(engine=db_engine) # DATABASE_URI is used here

    if llm: # llm is the OpenAI placeholder
        # Initialize SQLDatabaseToolkit
        toolkit = SQLDatabaseToolkit(db=db, llm=llm) 

        # Create SQL agent
        agent_executor = create_sql_agent(
            llm=llm, # The OpenAI llm
            toolkit=toolkit,
            verbose=True,
            agent_type=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
        )
        print("SQL Agent created with placeholder LLM (OpenAI).")
    else:
        print("LLM for SQL Agent (OpenAI) not initialized. SQL Agent creation skipped.")

except Exception as e:
    print(f"Error connecting to the database ({DATABASE_URI}) or initializing SQL agent: {e}")
    # Optionally, re-raise the exception or handle it as appropriate
    # raise

def run_sql_query(natural_language_query: str, parsed_query_dict: Optional[Dict[str, Any]] = None) -> tuple[str, list[str]]:
    """
    Runs a natural language query against the SQL database using the SQL agent,
    optionally prepending few-shot examples if parsed_query_dict is provided.

    Returns:
        A tuple containing:
        - The SQL agent's result string.
        - A list of IDs/names of the few-shot examples used (empty if none).
    """
    total_function_start_time = time.time()

    if not agent_executor:
        return "SQL Agent (agent_executor) not initialized. Cannot run query.", []
    if not llm: # llm is the OpenAI placeholder instance for the agent
        return "LLM for SQL Agent not initialized. Cannot run query.", []

    augmented_query = natural_language_query
    few_shot_examples_str = ""
    selected_example_info: list[str] = [] # To store IDs/names of used examples

    if parsed_query_dict:
        try:
            get_examples_start_time = time.time()
            relevant_examples, suggested_tables = get_relevant_sql_examples(parsed_query_dict, max_examples=2)
            get_examples_duration = time.time() - get_examples_start_time
            print(f"Time for get_relevant_sql_examples: {get_examples_duration:.3f} seconds")
            
            if relevant_examples:
                example_prompts = ["Here are some examples of how a user question maps to an SQL query:"]
                for ex in relevant_examples:
                    nl_equiv = ex.get("natural_language_equivalent", 
                                      ex.get("description", f"Example for intent: {ex.get('expected_intent')}"))
                    example_prompts.append(f"---\nUser Question: {nl_equiv}\nSQL Query:\n{ex['query_template']}\n---")
                    selected_example_info.append(ex.get('id', ex.get('name', 'Unknown Example')))
                few_shot_examples_str = "\n".join(example_prompts)
                print(f"Selected {len(selected_example_info)} few-shot SQL examples: {selected_example_info}")
            else:
                print("No relevant few-shot SQL examples found for the parsed query.")

            table_hint_str = ""
            if suggested_tables:
                table_hint_str = f"Hint: For the following question, consider using tables such as: {', '.join(sorted(list(suggested_tables)))}.\n"

            if few_shot_examples_str or table_hint_str:
                augmented_query = (
                    f"{few_shot_examples_str}\n\n"
                    f"{table_hint_str}" # table_hint_str includes \n if not empty
                    f"Based on these examples and the database schema, please answer the following question by generating and executing SQL:\n"
                    f"{natural_language_query}"
                )
                print(f"--- Augmented SQL query with few-shot examples and table hints for agent ---\n{augmented_query}\n---------------------------------------------------------")
            # If no examples and no table hints, augmented_query remains natural_language_query (already set as default)

        except Exception as e:
            print(f"Error retrieving or formatting SQL few-shot examples/hints: {e}")
            # Proceed with the original query if example/hint generation fails
            # Ensure duration is still printed if an error occurs after timing starts but before it ends
            if 'get_examples_start_time' in locals() and 'get_examples_duration' not in locals():
                 get_examples_duration = time.time() - get_examples_start_time
                 print(f"Time for get_relevant_sql_examples (until error): {get_examples_duration:.3f} seconds")


    try:
        agent_run_start_time = time.time()
        # The agent_executor.run method takes the final query string.
        print(f"Sending to SQL Agent: {augmented_query[:500]}...") # Log snippet of what's sent
        result = agent_executor.run(augmented_query)
        agent_run_duration = time.time() - agent_run_start_time
        print(f"Time for agent_executor.run: {agent_run_duration:.3f} seconds")
        
        total_function_duration = time.time() - total_function_start_time
        print(f"Total time for run_sql_query function: {total_function_duration:.3f} seconds")
        return str(result), selected_example_info
    except Exception as e:
        print(f"Error running query with SQL Agent: {e}")
        if 'agent_run_start_time' in locals() and 'agent_run_duration' not in locals():
            agent_run_duration = time.time() - agent_run_start_time
            print(f"Time for agent_executor.run (until error): {agent_run_duration:.3f} seconds")
        
        total_function_duration = time.time() - total_function_start_time
        print(f"Total time for run_sql_query function (until error): {total_function_duration:.3f} seconds")
        return f"Error running SQL query: {e}", selected_example_info

# Example Usage (optional, can be commented out or moved to a main script)
if __name__ == "__main__":
    # Path adjustments for direct run (already at the top of the file) should handle config import
    
    # Check if the agent was created
    if agent_executor:
        print("SQL Agent (with OpenAI LLM) Initialized Successfully.")
        # Example: List all tables
        # This requires a running PostgreSQL database specified by DATABASE_URI
        # and OPENAI_API_KEY for the llm to function.
        
        # Test query 1 (without parsed_query_dict):
        test_query_1 = "List all tables in the public schema."
        print(f"\nAttempting to run query 1 (no few-shot) via SQL Agent: \"{test_query_1}\"")
        if llm:
            query_result_1, examples_used_1 = run_sql_query(test_query_1)
            print(f"\nAgent Query Result 1:\n{query_result_1}")
            print(f"Examples used for Query 1: {examples_used_1}")
        else:
            print("Cannot run query 1 via agent as LLM is not initialized (OPENAI_API_KEY likely missing).")

        # Test query 2 (with parsed_query_dict to trigger few-shot examples)
        # This requires SQL_QUERY_EXAMPLES to be populated and accessible,
        # and each example to have 'natural_language_equivalent', 'query_template', etc.
        # Also, the get_relevant_sql_examples function needs to work correctly.
        print("\n--- Testing with Few-Shot Examples ---")
        # Example: Simulating a parsed query that should match 'daily_summary_report'
        # from sql_query_examples.py
        mock_parsed_query_for_daily_summary = {
            "intent": "get_daily_summary",
            "machine_id": "CNC-001", # This would be extracted by LLMInterface
            "timestamp": "yesterday", # This would be extracted
            "parameters": { 
                "equipment_id": "CNC-001", # These might be filled by API layer or LLM
                "start_date": "2023-01-10", 
                "end_date": "2023-01-10",
                "shift_id": "SHIFT_A" 
            }
        }
        # A natural language query that would correspond to this parsed dict
        test_query_2_nl = "Get the daily summary report for CNC-001 for yesterday's shift A (Jan 10, 2023)."
        
        print(f"\nAttempting to run query 2 (with few-shot) via SQL Agent: \"{test_query_2_nl}\"")
        if llm:
            # Call run_sql_query with the parsed dictionary
            query_result_2, examples_used_2 = run_sql_query(test_query_2_nl, parsed_query_dict=mock_parsed_query_for_daily_summary)
            print(f"\nAgent Query Result 2 (Few-Shot):\n{query_result_2}")
            print(f"Examples used for Query 2: {examples_used_2}")
        else:
            print("Cannot run query 2 via agent as LLM is not initialized.")
            
        # Example for machine speed (assuming 'machine_speed' example exists)
        mock_parsed_query_for_speed = {
            "intent": "get_machine_speed",
            "machine_id": "PRESS-002",
            "parameters": {
                "equipment_id": "PRESS-002", 
                "start_date": "2023-11-15", # Example date
                "zoned_current_time": "2023-11-15T14:30:00Z" # Example time
            }
        }
        test_query_3_nl = "What is the current speed of machine PRESS-002 on Nov 15, 2023 around 2:30 PM?"
        print(f"\nAttempting to run query 3 (with few-shot) via SQL Agent: \"{test_query_3_nl}\"")
        if llm:
            query_result_3, examples_used_3 = run_sql_query(test_query_3_nl, parsed_query_dict=mock_parsed_query_for_speed)
            print(f"\nAgent Query Result 3 (Few-Shot):\n{query_result_3}")
            print(f"Examples used for Query 3: {examples_used_3}")
        else:
            print("Cannot run query 3 via agent as LLM is not initialized.")

    elif not llm:
        print("SQL Agent could not be initialized because its LLM (OpenAI) is missing (OPENAI_API_KEY likely not set).")
            print("You can test the database connection directly if needed.")

    elif not llm:
        print("SQL Agent could not be initialized because its LLM (OpenAI) is missing (OPENAI_API_KEY likely not set).")
    else:
        print("SQL Agent could not be initialized, likely due to a database connection error.")
    
    print(f"\n--- SQL Agent Configuration ---")
    print(f"Using Database URI: {DATABASE_URI}")
    if llm:
        print(f"Using LLM: OpenAI (temperature=0)")
    else:
        print(f"LLM for SQL Agent: Not initialized (OPENAI_API_KEY required).")
    print(f"--- End SQL Agent Configuration ---")
