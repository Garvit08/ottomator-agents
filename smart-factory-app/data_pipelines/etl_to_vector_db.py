import os
import sys
import pandas as pd
from sqlalchemy import create_engine, text as sql_text
from datetime import datetime, timedelta

# --- Path Adjustments for Imports ---
# Assuming script is in smart-factory-app/data_pipelines/
# Add parent of 'smart_factory_app' to sys.path to allow `from smart_factory_app. ...`
current_dir_etl = os.path.dirname(os.path.abspath(__file__))
# smart_factory_app_dir is .../smart-factory-app
smart_factory_app_dir_etl = os.path.abspath(os.path.join(current_dir_etl, '..'))
# project_root_etl is the parent of .../smart-factory-app (e.g., /app)
project_root_etl = os.path.abspath(os.path.join(smart_factory_app_dir_etl, '..'))

if project_root_etl not in sys.path:
    sys.path.insert(0, project_root_etl)

# --- Import VectorAgent and Configuration ---
try:
    from smart_factory_app.agents.vector_agent import VectorAgent
    from smart_factory_app.config.config import DATABASE_URI, ETL_USE_MOCK_DB
    CONFIG_LOADED = True
except ImportError as e:
    print(f"Error importing VectorAgent or config: {e}. Using fallback configurations.")
    VectorAgent = None # Critical dependency
    CONFIG_LOADED = False
    # Fallback DB URI if config fails (not ideal)
    DB_HOST_FALLBACK = os.getenv("DB_HOST", "localhost")
    DB_PORT_FALLBACK = os.getenv("DB_PORT", "5432")
    DB_USER_FALLBACK = os.getenv("DB_USER", "postgres")
    DB_PASSWORD_FALLBACK = os.getenv("DB_PASSWORD", "password")
    DB_NAME_FALLBACK = os.getenv("DB_NAME", "smart_factory_db")
    DATABASE_URI = f"postgresql+psycopg2://{DB_USER_FALLBACK}:{DB_PASSWORD_FALLBACK}@{DB_HOST_FALLBACK}:{DB_PORT_FALLBACK}/{DB_NAME_FALLBACK}"
    ETL_USE_MOCK_DB = os.getenv("ETL_USE_MOCK_DB", "true").lower() == "true"


# --- Logging Helper ---
def log_message(message):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")

# --- Data Fetching ---
def fetch_data_from_sql(engine, table_name: str, columns: list[str], 
                        time_window_column: str = None, days_to_fetch: int = None) -> pd.DataFrame:
    """
    Fetches data from a specified SQL table, optionally filtering by a time window.
    """
    log_message(f"Fetching data from table '{table_name}'. Columns: {columns}.")
    cols_str = ", ".join(columns)
    query = f"SELECT {cols_str} FROM {table_name}"

    params = {}
    if time_window_column and days_to_fetch is not None and days_to_fetch > 0:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_to_fetch)
        query += f" WHERE {time_window_column} >= :start_date AND {time_window_column} <= :end_date"
        params = {"start_date": start_date, "end_date": end_date}
        log_message(f"Applying time window: {time_window_column} >= {start_date} and <= {end_date}")

    try:
        with engine.connect() as connection:
            df = pd.read_sql_query(sql=sql_text(query), con=connection, params=params)
        log_message(f"Successfully fetched {len(df)} rows from '{table_name}'.")
        return df
    except Exception as e:
        log_message(f"Error fetching data from '{table_name}': {e}")
        return pd.DataFrame() # Return empty DataFrame on error

# --- Text Summary Generation ---
def generate_production_log_summary(row: pd.Series) -> tuple[str, dict]:
    """Generates text summary and metadata for a production_logs row."""
    # Assuming columns like: timestamp, machine_id, factory_id, part_count, oee_percentage, status
    # Handle potential missing columns gracefully for placeholder data
    ts = row.get('timestamp', 'N/A')
    machine_id = row.get('machine_id', 'Unknown Machine')
    factory_id = row.get('factory_id', 'Unknown Factory')
    part_count = row.get('part_count', 0)
    oee = row.get('oee_percentage', 0.0)
    status = row.get('status', 'N/A')

    summary = (f"On {ts}, machine {machine_id} in factory {factory_id} produced {part_count} parts. "
               f"Operational status was '{status}' with an OEE of {oee}%.")
    
    metadata = {
        "table_origin": "production_logs",
        "timestamp": str(ts), # Ensure datetime is serialized
        "machine_id": machine_id,
        "factory_id": factory_id,
        "part_count": part_count,
        "oee_percentage": oee,
        "status": status,
        **row.to_dict() # Include all original columns in metadata
    }
    return summary, metadata

def generate_downtime_log_summary(row: pd.Series) -> tuple[str, dict]:
    """Generates text summary and metadata for a downtime_logs row."""
    # Assuming columns: machine_id, factory_id, start_time, end_time, fault_code, downtime_details, duration_minutes
    machine_id = row.get('machine_id', 'Unknown Machine')
    factory_id = row.get('factory_id', 'Unknown Factory')
    start_time = row.get('start_time', 'N/A')
    fault_code = row.get('fault_code', 'N/A')
    details = row.get('downtime_details', 'No details provided')
    duration = row.get('duration_minutes', 0)

    summary = (f"Machine {machine_id} in factory {factory_id} experienced downtime starting at {start_time} "
               f"due to fault code '{fault_code}' (Details: {details}). Downtime lasted for {duration} minutes.")
    
    metadata = {
        "table_origin": "downtime_logs",
        "start_time": str(start_time),
        "machine_id": machine_id,
        "factory_id": factory_id,
        "fault_code": fault_code,
        "downtime_details": details,
        "duration_minutes": duration,
        **row.to_dict()
    }
    return summary, metadata

def generate_text_summaries(df: pd.DataFrame, table_name: str) -> tuple[list[str], list[dict]]:
    """
    Generates text summaries and metadatas from a DataFrame based on table_name.
    """
    summaries = []
    metadatas = []

    if df.empty:
        log_message(f"No data to summarize for table '{table_name}'.")
        return summaries, metadatas

    log_message(f"Generating summaries for {len(df)} rows from '{table_name}'...")
    for _, row in df.iterrows():
        summary, meta = None, None
        if table_name == "production_logs":
            summary, meta = generate_production_log_summary(row)
        elif table_name == "downtime_logs":
            summary, meta = generate_downtime_log_summary(row)
        # Add more elif conditions here for other tables
        else:
            log_message(f"No summary generation logic defined for table: {table_name}. Skipping row.")
            # Generic summary as a fallback
            generic_summary = f"Data from table '{table_name}': {row.to_dict()}"
            generic_meta = {"table_origin": table_name, **row.to_dict()}
            summary, meta = generic_summary, generic_meta
            
        if summary and meta:
            summaries.append(summary)
            metadatas.append(meta)
    
    log_message(f"Generated {len(summaries)} summaries for '{table_name}'.")
    return summaries, metadatas

# --- Main ETL Process ---
def run_etl():
    """
    Main ETL process to fetch data from SQL, generate summaries, and load into VectorDB.
    """
    log_message("Starting ETL process...")

    # Initialize Database Engine
    # DATABASE_URI is now from config
    if not DATABASE_URI:
        log_message("Database URI not configured. Aborting ETL.")
        return
        
    try:
        engine = create_engine(DATABASE_URI)
        with engine.connect() as connection: # Test connection
            log_message(f"Successfully connected to PostgreSQL database via: {DATABASE_URI.split('@')[-1]}.") # Hide creds
    except Exception as e:
        log_message(f"Failed to connect to PostgreSQL ({DATABASE_URI.split('@')[-1]}): {e}")
        return

    # Initialize VectorAgent
    if VectorAgent is None: # Check if import failed earlier
        log_message("VectorAgent module could not be imported. ETL cannot proceed.")
        sys.exit(1) # Critical, so exit
    
    try:
        # VectorAgent now uses its defaults from config.py
        vector_agent = VectorAgent() 
        log_message(f"VectorAgent initialized with model: {vector_agent.model_name}, collection: {vector_agent.collection_name}.")
    except Exception as e:
        log_message(f"Failed to initialize VectorAgent: {e}. Aborting ETL.")
        sys.exit(1)


    # Define tables and their processing configurations
    # In a real scenario, this could come from a config file
    tables_to_process = [
        {
            "table_name": "production_logs",
            "columns": ["timestamp", "machine_id", "factory_id", "part_count", "oee_percentage", "status"],
            "time_window_column": "timestamp", # Filter by this column
            "days_to_fetch": 7 # Fetch data from the last 7 days
        },
        {
            "table_name": "downtime_logs",
            "columns": ["machine_id", "factory_id", "start_time", "end_time", "fault_code", "downtime_details", "duration_minutes"],
            "time_window_column": "start_time",
            "days_to_fetch": 30 
        },
        # Example: A table that might not have a time window or uses all columns
        {
            "table_name": "maintenance_records",
            "columns": ["record_id", "machine_id", "maintenance_date", "description", "technician"],
            # No time_window_column or days_to_fetch means fetch all data
        }
    ]

    for table_config in tables_to_process:
        table_name = table_config["table_name"]
        log_message(f"--- Processing table: {table_name} ---")

        # 1. Fetch data
        # For testing without a live DB, we can mock this part or ensure tables exist with some data
        df = fetch_data_from_sql(
            engine, 
            table_name, 
            table_config["columns"],
            table_config.get("time_window_column"),
            table_config.get("days_to_fetch")
        )

        if df.empty:
            log_message(f"No data fetched for '{table_name}'. Skipping to next table.")
            continue

        # 2. Generate text summaries and metadatas
        texts, metadatas = generate_text_summaries(df, table_name)

        if not texts:
            log_message(f"No text summaries generated for '{table_name}'. Skipping to next table.")
            continue

        # 3. Load into VectorDB
        # Generate unique IDs for vector DB entries, e.g., from primary key or hash of content
        # For now, VectorAgent's add_texts will generate IDs if not provided.
        # We could create more meaningful IDs like f"{table_name}_{row_primary_key}"
        log_message(f"Adding {len(texts)} text summaries from '{table_name}' to VectorDB.")
        try:
            vector_agent.add_texts(texts=texts, metadatas=metadatas)
            log_message(f"Successfully added data from '{table_name}' to VectorDB.")
        except Exception as e:
            log_message(f"Error adding texts from '{table_name}' to VectorDB: {e}")

    log_message("ETL process completed.")

# --- Main Execution ---
if __name__ == "__main__":
    # This part is crucial: it allows the script to find the 'smart_factory_app' package
    # Path adjustments for config import are at the top.
    # Check if VectorAgent and config were loaded.
    if not CONFIG_LOADED:
        log_message("ETL script cannot run due to failed configuration or VectorAgent import.")
        sys.exit(1)
    if VectorAgent is None: # Should be caught by CONFIG_LOADED check too if VectorAgent is None
        log_message("VectorAgent is None even after import attempts. Critical error. Aborting.")
        sys.exit(1)

    # --- Mocking Database for Testing (controlled by config.ETL_USE_MOCK_DB) ---
    original_fetch_data_from_sql = fetch_data_from_sql # Keep a reference

    if ETL_USE_MOCK_DB:
        log_message("Using MOCK database for ETL process as configured.")
        
        def mock_fetch_data_from_sql_etl(engine, table_name: str, columns: list[str], 
                                     time_window_column: str = None, days_to_fetch: int = None) -> pd.DataFrame:
            log_message(f"[MOCK ETL] Fetching data for table '{table_name}'.")
            if table_name == "production_logs":
                data = {
                    'timestamp': [datetime.now() - timedelta(days=x) for x in range(5)],
                    'machine_id': [f'M00{x}' for x in range(1, 6)], 'factory_id': ['F01'] * 5,
                    'part_count': [100, 110, 105, 98, 112],
                    'oee_percentage': [85.5, 88.0, 86.2, 83.1, 89.5],
                    'status': ['Normal'] * 4 + ['Maintenance Required']
                }
                for col in columns: 
                    if col not in data: data[col] = [None] * 5 
                return pd.DataFrame(data)
            elif table_name == "downtime_logs":
                data = {
                    'machine_id': ['M002', 'M004'], 'factory_id': ['F01'] * 2,
                    'start_time': [datetime.now() - timedelta(hours=x*5) for x in range(1,3)],
                    'end_time': [datetime.now() - timedelta(hours=x*5-1) for x in range(1,3)],
                    'fault_code': ['ERR-1024', 'ERR-512'],
                    'downtime_details': ['Sensor failure on axis X.', 'Overload protection triggered.'],
                    'duration_minutes': [60, 30]
                }
                for col in columns:
                    if col not in data: data[col] = [None] * 2
                return pd.DataFrame(data)
            elif table_name == "maintenance_records":
                data = {
                    'record_id': [101, 102, 103], 'machine_id': ['M001', 'M003', 'M001'],
                    'maintenance_date': [datetime.now() - timedelta(days=x*10) for x in range(3)],
                    'description': ['Annual checkup', 'Filter replacement', 'Software update'],
                    'technician': ['Tech Alice', 'Tech Bob', 'Tech Alice']
                }
                for col in columns:
                    if col not in data: data[col] = [None] * 3
                return pd.DataFrame(data)
            return pd.DataFrame()

        # Monkey-patch the real function with the mock version for this run
        globals()['fetch_data_from_sql'] = mock_fetch_data_from_sql_etl
    else:
        log_message("Using REAL database for ETL process as configured. Ensure DB is running and accessible.")
        # Ensure the original function is used if not mocking
        globals()['fetch_data_from_sql'] = original_fetch_data_from_sql
        
    run_etl()
