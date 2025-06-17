# nl_to_sql_service/examples/basic_usage.py
import sys
import os
import json # For creating dummy examples file
import logging

# Ensure the nl_to_sql_service package can be imported
# This is for running the example script directly from the 'examples' folder
# or from the 'nl_to_sql_service' folder.
PACKAGE_PARENT = '..'
SCRIPT_DIR = os.path.dirname(os.path.realpath(os.path.join(os.getcwd(), os.path.expanduser(__file__))))
# Add the parent directory of `nl_to_sql_service` to sys.path
# This makes `from nl_to_sql_service...` imports work
# The root of the import should be the directory containing `nl_to_sql_service`
sys.path.append(os.path.normpath(os.path.join(SCRIPT_DIR, PACKAGE_PARENT)))


try:
    from nl_to_sql_service.nl_to_sql_processor import NLToSQLProcessor
    from nl_to_sql_service.config_manager import NLToSQLConfig, LLMConfig, DBSchemaHandlerConfig
except ImportError as e:
    print(f"Could not import NLToSQLProcessor or NLToSQLConfig: {e}")
    print("Ensure PYTHONPATH is set correctly or run from appropriate directory (e.g., project root as 'python -m nl_to_sql_service.examples.basic_usage').")
    sys.exit(1)

BASE_PROMPT_TEXT_CONTENT = """
You are an expert Natural Language to SQL converter. Your primary task is to translate the user's question into an accurate and executable SQL query for the {sql_dialect} database system.
You must adhere strictly to the provided schema and examples. If the question is ambiguous or cannot be converted to SQL based on the provided schema, return only the text "ERROR: Cannot convert query due to ambiguity or missing schema information." instead of guessing.

### Database Schema Context:
{schema_representation}

{few_shot_examples_string}

### User Question to Convert to SQL:
{natural_language_query}

### SQL Query:
"""

def setup_dummy_files(examples_path, prompt_path, base_prompt_content):
    """Helper to create dummy files needed for the example to run."""
    # Create dummy examples file
    examples_dir = os.path.dirname(examples_path)
    if not os.path.exists(examples_dir):
        os.makedirs(examples_dir, exist_ok=True)

    if not os.path.exists(examples_path):
        print(f"Creating dummy examples file: {examples_path}")
        dummy_examples_content = [
            {"id": "ex1", "nl_query": "List all active users", "sql_query": "SELECT * FROM users WHERE status = 'active';", "description": "Simple active user query"},
            {"id": "ex2", "nl_query": "How many products in electronics category?", "sql_query": "SELECT COUNT(*) FROM products WHERE category = 'electronics';", "description": "Count products in category"}
        ]
        with open(examples_path, 'w', encoding='utf-8') as f:
            json.dump(dummy_examples_content, f, indent=4)

    # Create dummy prompt file
    prompts_dir = os.path.dirname(prompt_path)
    if not os.path.exists(prompts_dir):
        os.makedirs(prompts_dir, exist_ok=True)
    if not os.path.exists(prompt_path):
        print(f"Creating dummy prompt file: {prompt_path}")
        with open(prompt_path, 'w', encoding='utf-8') as f:
            f.write(base_prompt_content)

def cleanup_dummy_files(examples_path, prompt_path):
    """Helper to clean up dummy files."""
    examples_dir = os.path.dirname(examples_path)
    prompts_dir = os.path.dirname(prompt_path)

    if os.path.exists(examples_path) and "dummy_examples_for_basic_usage.json" in examples_path :
        os.remove(examples_path)
        print(f"Cleaned up {examples_path}")
        if not os.listdir(examples_dir): os.rmdir(examples_dir) # Remove dir if empty

    if os.path.exists(prompt_path) and "dummy_prompt_for_basic_usage.txt" in prompt_path:
        os.remove(prompt_path)
        print(f"Cleaned up {prompt_path}")
        if not os.listdir(prompts_dir): os.rmdir(prompts_dir) # Remove dir if empty


def main():
    print("Running NL-to-SQL Processor basic usage example...")

    # Configure basic logging for the example run
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    # You can set logging.DEBUG for more verbose output from NLToSQLProcessor and its components

    # Define paths for dummy files specifically for this example
    # Place dummy files relative to the nl_to_sql_service package root for this example
    package_root = os.path.dirname(SCRIPT_DIR) # This should be the directory containing nl_to_sql_service/

    # To avoid writing into the source package 'prompts' or root, let's use a temp examples location
    # For a real scenario, these paths come from config and would point to actual files.
    # For this example, we create them in the 'examples' folder itself.
    example_script_dir = os.path.dirname(os.path.abspath(__file__))
    dummy_examples_file = os.path.join(example_script_dir, "dummy_examples_for_basic_usage.json")
    dummy_prompts_dir = os.path.join(example_script_dir, "temp_prompts_for_example") # Temp dir for prompt
    dummy_prompt_file = os.path.join(dummy_prompts_dir, "dummy_base_nl_to_sql_prompt.txt")

    setup_dummy_files(dummy_examples_file, dummy_prompt_file, BASE_PROMPT_TEXT_CONTENT)

    # Configuration for the example:
    config = NLToSQLConfig(
        llm=LLMConfig(
            model_provider="ollama", # Assuming an Ollama instance is running for the example
            model_name=os.getenv("NLSQL_BASIC_EXAMPLE_LLM_MODEL", "mistral"), # Default, can be overridden by env
            base_url=os.getenv("NLSQL_BASIC_EXAMPLE_LLM_URL", "http://localhost:11434"),
            temperature=0.0
        ),
        few_shot_examples_path=dummy_examples_file,
        base_prompt_template_path=dummy_prompt_file,
        use_dynamic_schema_handling=False,
        db_schema_handler=None, # Explicitly None as use_dynamic_schema_handling is False
        log_level="INFO" # Set desired log level for the processor
    )

    print("Initializing NLToSQLProcessor...")
    try:
        # NLToSQLProcessor's __init__ will log its own messages.
        # Set a higher log level for its components if too verbose.
        processor = NLToSQLProcessor(config=config)
        if not processor.llm: # Check if LLM initialized
             print("LLM could not be initialized in NLToSQLProcessor. Ensure Ollama is running or ChatOllama is available.")
             print("The example will proceed but LLM calls will fail, likely returning an error message.")
             # Depending on strictness, you might want to sys.exit(1) here.
    except Exception as e:
        print(f"Failed to initialize NLToSQLProcessor: {e}")
        cleanup_dummy_files(dummy_examples_file, dummy_prompt_file)
        sys.exit(1)

    print(f"NLToSQLProcessor initialized.")
    if processor.llm:
         print(f"Using LLM: {processor.llm.__class__.__name__} with model {config.llm.model_name}")
    else:
        print("LLM is NOT available to the processor.")


    # Example NL query
    nl_query = "How many active users are there?"
    custom_schema = "CREATE TABLE users (user_id INT PRIMARY KEY, name VARCHAR(100), status VARCHAR(20), email TEXT);\n" \
                    "CREATE TABLE orders (order_id INT PRIMARY KEY, user_id INT, order_date DATE, total_amount DECIMAL(10,2));"

    print(f"\nConverting NL Query: '{nl_query}'")
    print(f"With Custom Schema:\n{custom_schema}")

    # Call the processor
    result = processor.convert_nl_to_sql(
        natural_language_query=nl_query,
        custom_schema_info=custom_schema
    )

    print(f"\n--- Result from NL-to-SQL Processor ---")
    print(f"  Generated SQL: {result.get('sql_query')}")
    print(f"  Error Message: {result.get('error_message')}")
    # print(f"  LLM Reasoning: {result.get('llm_reasoning')}") # Placeholder
    # print(f"  Tables Used (tentative): {result.get('tables_used')}") # Placeholder
    # print(f"  Confidence: {result.get('confidence_score')}") # Placeholder
    # print(f"  Full Prompt Used (debug):\n{result.get('prompt_used')}")


    # Another example
    nl_query_2 = "List projects that are overdue."
    custom_schema_2 = "CREATE TABLE projects (id INT, name VARCHAR, due_date DATE, status VARCHAR);"
    print(f"\nConverting NL Query: '{nl_query_2}'")
    print(f"With Custom Schema:\n{custom_schema_2}")
    result_2 = processor.convert_nl_to_sql(
        natural_language_query=nl_query_2,
        custom_schema_info=custom_schema_2
    )
    print(f"\n--- Result 2 from NL-to-SQL Processor ---")
    print(f"  Generated SQL: {result_2.get('sql_query')}")
    print(f"  Error Message: {result_2.get('error_message')}")


    cleanup_dummy_files(dummy_examples_file, dummy_prompt_file)
    print("\nBasic usage example finished.")

if __name__ == "__main__":
    main()
