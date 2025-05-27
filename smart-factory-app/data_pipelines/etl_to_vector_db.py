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
    from smart_factory_app.config.config import DATABASE_URI, ETL_USE_MOCK_DB, TABLE_CONFIGS
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

# --- Text Summary Generation Functions for New Schema ---

def generate_equipment_summary(row: pd.Series) -> tuple[str, dict]:
    """Generates text summary and metadata for 'equipment' table row."""
    machine_id = row.get('machine_id', 'N/A')
    name = row.get('machine_name', 'Unknown Name')
    m_type = row.get('machine_type', 'N/A')
    location = row.get('location', 'N/A')
    manufacturer = row.get('manufacturer', 'N/A')
    install_date = row.get('install_date', 'N/A')
    summary = (f"Equipment Record: Machine ID {machine_id} (Name: {name}, Type: {m_type}) is located at {location}. "
               f"Manufactured by {manufacturer}, installed on {install_date}.")
    metadata = {"table_origin": "equipment", **row.to_dict()}
    return summary, metadata

def generate_equipment_data_minute_summary(row: pd.Series) -> tuple[str, dict]:
    """Generates summary for 'equipment_data_minute'."""
    ts = row.get('timestamp', 'N/A')
    machine_id = row.get('machine_id', 'N/A')
    sensor_id = row.get('sensor_id', 'N/A')
    param_name = row.get('parameter_name', 'N/A')
    param_value = row.get('parameter_value', 'N/A')
    unit = row.get('unit', '')
    summary = (f"Minute Data: At {ts}, machine {machine_id} sensor {sensor_id} reported parameter '{param_name}' "
               f"as {param_value} {unit}.")
    metadata = {"table_origin": "equipment_data_minute", "timestamp": str(ts), **row.to_dict()}
    return summary, metadata

def generate_equipment_data_hourly_summary(row: pd.Series) -> tuple[str, dict]:
    """Generates summary for 'equipment_data_hourly'."""
    ts = row.get('timestamp', 'N/A')
    machine_id = row.get('machine_id', 'N/A')
    kpi_name = row.get('kpi_name', 'N/A')
    kpi_value = row.get('kpi_value', 'N/A')
    quality = row.get('quality_score', 'N/A')
    summary = (f"Hourly Data: At {ts}, machine {machine_id} had KPI '{kpi_name}' with value {kpi_value}. "
               f"Quality score was {quality}.")
    metadata = {"table_origin": "equipment_data_hourly", "timestamp": str(ts), **row.to_dict()}
    return summary, metadata

def generate_equipment_data_daily_summary(row: pd.Series) -> tuple[str, dict]:
    """Generates summary for 'equipment_data_daily'."""
    date = row.get('date', 'N/A')
    machine_id = row.get('machine_id', 'N/A')
    avg_oee = row.get('avg_oee', 'N/A')
    total_prod = row.get('total_production', 'N/A')
    total_downtime = row.get('total_downtime_minutes', 'N/A')
    summary = (f"Daily Summary for {date}: Machine {machine_id} had an average OEE of {avg_oee}%, "
               f"produced {total_prod} units, and experienced {total_downtime} minutes of downtime.")
    metadata = {"table_origin": "equipment_data_daily", "date": str(date), **row.to_dict()}
    return summary, metadata

def generate_generic_equipment_timeseries_summary(row: pd.Series, table_name: str, period_col: str, oee_col: str, prod_col: str) -> tuple[str, dict]:
    """Generic summary for monthly/quarterly equipment data."""
    period_val = row.get(period_col, 'N/A')
    machine_id = row.get('machine_id', 'N/A')
    avg_oee = row.get(oee_col, 'N/A')
    total_prod = row.get(prod_col, 'N/A')
    period_name = table_name.split('_')[-1].capitalize() # Monthly, Quarterly
    
    summary = (f"{period_name} Summary for {period_val}: Machine {machine_id} had an average OEE of {avg_oee}% "
               f"and produced {total_prod} units.")
    metadata = {"table_origin": table_name, period_col: str(period_val), **row.to_dict()}
    return summary, metadata


def generate_equipment_status_summary(row: pd.Series) -> tuple[str, dict]:
    """Generates summary for 'equipment_status'."""
    ts = row.get('timestamp', 'N/A')
    machine_id = row.get('machine_id', 'N/A')
    status_code = row.get('status_code', 'N/A')
    status_desc = row.get('status_description', 'N/A')
    duration = row.get('duration_seconds', 'N/A')
    summary = (f"Status Update: At {ts}, machine {machine_id} reported status '{status_desc}' (Code: {status_code}). "
               f"This status lasted for {duration} seconds.")
    metadata = {"table_origin": "equipment_status", "timestamp": str(ts), **row.to_dict()}
    return summary, metadata

def generate_equipment_alarm_summary(row: pd.Series) -> tuple[str, dict]:
    """Generates summary for 'equipment_alarm'."""
    alarm_id = row.get('alarm_id', 'N/A')
    machine_id = row.get('machine_id', 'N/A')
    start_ts = row.get('start_timestamp', 'N/A')
    end_ts = row.get('end_timestamp', 'N/A')
    alarm_code = row.get('alarm_code', 'N/A')
    alarm_desc = row.get('alarm_description', 'N/A')
    severity = row.get('severity', 'N/A')
    summary = (f"Alarm Event: Alarm ID {alarm_id} (Code: {alarm_code}, Severity: {severity}) occurred on machine {machine_id}. "
               f"Started: {start_ts}, Ended: {end_ts}. Description: {alarm_desc}.")
    metadata = {"table_origin": "equipment_alarm", "start_timestamp": str(start_ts), **row.to_dict()}
    return summary, metadata

def generate_equipment_product_goal_summary(row: pd.Series) -> tuple[str, dict]:
    """Generates summary for 'equipment_product_goal'."""
    goal_id = row.get('goal_id', 'N/A')
    machine_id = row.get('machine_id', 'N/A')
    product_id = row.get('product_id', 'N/A')
    target_rate = row.get('target_production_rate', 'N/A')
    target_quality = row.get('target_quality_rate', 'N/A')
    start_date = row.get('start_date', 'N/A')
    end_date = row.get('end_date', 'N/A')
    summary = (f"Production Goal ID {goal_id}: For machine {machine_id} and product {product_id}, the target production rate "
               f"is {target_rate} units/hour with a quality rate of {target_quality}%. Goal active from {start_date} to {end_date}.")
    metadata = {"table_origin": "equipment_product_goal", **row.to_dict()}
    return summary, metadata


# --- Main Summary Dispatcher ---
SUMMARY_GENERATORS = {
    "equipment": generate_equipment_summary,
    "equipment_data_minute": generate_equipment_data_minute_summary,
    "equipment_data_hourly": generate_equipment_data_hourly_summary,
    "equipment_data_daily": generate_equipment_data_daily_summary,
    "equipment_data_monthly": lambda row: generate_generic_equipment_timeseries_summary(row, "equipment_data_monthly", "month_year", "monthly_avg_oee", "monthly_total_production"),
    "equipment_data_quarterly": lambda row: generate_generic_equipment_timeseries_summary(row, "equipment_data_quarterly", "quarter_year", "quarterly_avg_oee", "quarterly_total_production"),
    "equipment_status": generate_equipment_status_summary,
    "equipment_alarm": generate_equipment_alarm_summary,
    "equipment_product_goal": generate_equipment_product_goal_summary,
    # Add old ones if still needed, or remove if schema fully changed
    # "production_logs": generate_production_log_summary, # Example if keeping old
    # "downtime_logs": generate_downtime_log_summary,     # Example if keeping old
}

def generate_text_summaries(df: pd.DataFrame, table_name: str) -> tuple[list[str], list[dict]]:
    """
    Generates text summaries and metadatas from a DataFrame based on table_name, using SUMMARY_GENERATORS.
    """
    summaries = []
    metadatas = []

    if df.empty:
        log_message(f"No data to summarize for table '{table_name}'.")
        return summaries, metadatas

    generator_func = SUMMARY_GENERATORS.get(table_name)

    log_message(f"Generating summaries for {len(df)} rows from '{table_name}'...")
    for _, row in df.iterrows():
        if generator_func:
            summary, meta = generator_func(row)
        else:
            log_message(f"No specific summary generation logic defined for table: {table_name}. Creating generic summary.")
            summary = f"Generic summary for table '{table_name}': {row.to_dict()}"
            meta = {"table_origin": table_name, **row.to_dict()}
            
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


    # Define tables to process using TABLE_CONFIGS from config.py
    if not CONFIG_LOADED or not TABLE_CONFIGS:
        log_message("TABLE_CONFIGS not loaded from config. Aborting ETL.")
        return

    # Default days_to_fetch if not specified per table, can be overridden in TABLE_CONFIGS
    default_days_to_fetch = 7 

    for table_name, table_spec in TABLE_CONFIGS.items():
        log_message(f"--- Processing table: {table_name} ---")

        columns_to_fetch = table_spec["columns_to_fetch"]
        time_window_column = table_spec.get("time_window_column")
        # Allow days_to_fetch to be specified per table in config, else use default
        days_to_fetch_for_table = table_spec.get("days_to_fetch", default_days_to_fetch if time_window_column else None)

        # 1. Fetch data
        df = fetch_data_from_sql(
            engine, 
            table_name, 
            columns_to_fetch,
            time_window_column,
            days_to_fetch_for_table 
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
            log_message(f"[MOCK ETL] Fetching data for table '{table_name}'. Columns: {columns}")
            mock_data = {}
            num_rows = 2 # Default number of mock rows

            if table_name == "equipment":
                mock_data = {
                    'machine_id': [f'EQP-{i}' for i in range(num_rows)],
                    'machine_name': [f'Equipment Name {i}' for i in range(num_rows)],
                    'machine_type': ['Type A', 'Type B'][:num_rows],
                    'location': ['Shopfloor 1', 'Shopfloor 2'][:num_rows],
                    'manufacturer': ['ManuCorp', 'GlobalManu'][:num_rows],
                    'install_date': [datetime(2022, 1, 1+i) for i in range(num_rows)]
                }
            elif table_name == "equipment_data_minute":
                mock_data = {
                    'timestamp': [datetime.now() - timedelta(minutes=x) for x in range(num_rows)],
                    'machine_id': [f'EQP-{x%2}' for x in range(num_rows)], # Cycle through EQP-0, EQP-1
                    'sensor_id': [f'Sensor{x}' for x in range(num_rows)],
                    'parameter_name': ['Temperature', 'Pressure'][:num_rows] if num_rows <=2 else ['Temperature'] * num_rows,
                    'parameter_value': [70.5 + x, 101.2 + x for x in range(num_rows)],
                    'unit': ['C', 'kPa'][:num_rows] if num_rows <=2 else ['C'] * num_rows
                }
            elif table_name == "equipment_data_hourly":
                 mock_data = {
                    'timestamp': [datetime.now() - timedelta(hours=x) for x in range(num_rows)],
                    'machine_id': [f'EQP-{x%2}' for x in range(num_rows)],
                    'kpi_name': ['OEE', 'Availability'][:num_rows] if num_rows <=2 else ['OEE'] * num_rows,
                    'kpi_value': [85.0 + x, 95.0 - x for x in range(num_rows)],
                    'quality_score': [99.1 - x for x in range(num_rows)]
                }
            elif table_name == "equipment_data_daily":
                mock_data = {
                    'date': [datetime.now().date() - timedelta(days=x) for x in range(num_rows)],
                    'machine_id': [f'EQP-{x%2}' for x in range(num_rows)],
                    'avg_oee': [80.0 + x for x in range(num_rows)],
                    'total_production': [1000 + 50*x for x in range(num_rows)],
                    'total_downtime_minutes': [30 - 5*x for x in range(num_rows)]
                }
            elif table_name == "equipment_status":
                mock_data = {
                    'timestamp': [datetime.now() - timedelta(hours=x) for x in range(num_rows)],
                    'machine_id': [f'EQP-{x%2}' for x in range(num_rows)],
                    'status_code': ['RUNNING', 'STOPPED'][:num_rows] if num_rows <=2 else ['RUNNING'] * num_rows,
                    'status_description': ['Machine is running normally.', 'Machine is stopped for maintenance.'][:num_rows] if num_rows <=2 else ['Machine is running normally.'] * num_rows,
                    'duration_seconds': [3600 - 100*x for x in range(num_rows)]
                }
            elif table_name == "equipment_alarm":
                mock_data = {
                    'alarm_id': [f'ALM-{1000+i}' for i in range(num_rows)],
                    'machine_id': [f'EQP-{i%2}' for i in range(num_rows)],
                    'start_timestamp': [datetime.now() - timedelta(minutes=30+i*10) for i in range(num_rows)],
                    'end_timestamp': [datetime.now() - timedelta(minutes=10+i*5) for i in range(num_rows)],
                    'alarm_code': [f'CODE_A{i}' for i in range(num_rows)],
                    'alarm_description': ['High temperature warning', 'Pressure out of range'][:num_rows] if num_rows <=2 else ['Generic Alarm'] * num_rows,
                    'severity': [1, 2][:num_rows] if num_rows <=2 else [1] * num_rows
                }
            # Add other tables from TABLE_CONFIGS if needed for full mock coverage
            # For equipment_data_monthly, equipment_data_quarterly, equipment_product_goal - similar simple mocks
            else: # Default empty if no specific mock
                log_message(f"[MOCK ETL] No specific mock data for table '{table_name}'. Returning empty DataFrame.")
                return pd.DataFrame(columns=columns)

            # Ensure all requested columns are present, fill with None if not in mock_data
            final_mock_data = {}
            for col in columns:
                final_mock_data[col] = mock_data.get(col, [None]*num_rows)
            
            return pd.DataFrame(final_mock_data)

        # Monkey-patch the real function with the mock version for this run
        globals()['fetch_data_from_sql'] = mock_fetch_data_from_sql_etl
    else:
        log_message("Using REAL database for ETL process as configured. Ensure DB is running and accessible.")
        # Ensure the original function is used if not mocking
        globals()['fetch_data_from_sql'] = original_fetch_data_from_sql
        
    run_etl()
