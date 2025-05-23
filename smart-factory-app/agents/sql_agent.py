import os
import sys
from sqlalchemy import create_engine
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain_community.utilities import SQLDatabase
from langchain_openai import OpenAI # Placeholder LLM
from langchain.agents import create_sql_agent
from langchain.agents.agent_types import AgentType

# Adjust path to import config if necessary, assuming this script might be run directly
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
    sys.path.insert(0, os.path.dirname(project_root_sql_agent)) 

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
except ImportError:
    print("Error importing config. Ensure PYTHONPATH is set or paths are correct.")
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

def run_sql_query(query_text: str):
    """
    Runs a SQL query using the SQL agent.
    """
    if not agent_executor:
        return "SQL Agent not initialized. Cannot run query."
    if not llm:
        return "LLM not initialized. Cannot run query."

    try:
        # For Langchain versions that expect a dictionary input:
        # result = agent_executor.run({"input": query_text})
        # For Langchain versions that expect a direct string input for `run`:
        result = agent_executor.run(query_text)
        return result
    except Exception as e:
        return f"Error running query: {e}"

# Example Usage (optional, can be commented out or moved to a main script)
if __name__ == "__main__":
    # Path adjustments for direct run (already at the top of the file) should handle config import
    
    # Check if the agent was created
    if agent_executor:
        print("SQL Agent (with OpenAI LLM) Initialized Successfully.")
        # Example: List all tables
        # This requires a running PostgreSQL database specified by DATABASE_URI
        # and OPENAI_API_KEY for the llm to function.
        
        # Test query:
        test_query = "List all tables in the public schema." # More natural language for agent
        # Or a direct SQL if the agent is bypassed:
        # test_query_sql = "SELECT table_name FROM information_schema.tables WHERE table_schema='public';"

        print(f"\nAttempting to run query via SQL Agent: \"{test_query}\"")
        if llm: # Check if LLM was initialized
            query_result = run_sql_query(test_query)
            print(f"\nAgent Query Result:\n{query_result}")
        else:
            print("Cannot run query via agent as LLM is not initialized (OPENAI_API_KEY likely missing).")
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
