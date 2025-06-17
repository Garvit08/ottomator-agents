# nl_to_sql_service/db_schema_handler.py
import time
import logging
from typing import Dict, List, Optional, Any, Tuple, Union

# Attempt to import psycopg2
try:
    import psycopg2
    import psycopg2.extras # For DictCursor
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False
    psycopg2 = None # Ensure psycopg2 is None if not available
    DictCursor = None # Placeholder

class DBSchemaHandler:
    """
    Handles fetching and formatting database schema information,
    with specific support for PostgreSQL and TimescaleDB.
    Includes caching for schema representations.
    """

    def __init__(self, db_config: Dict[str, Any],
                 logger: Optional[logging.Logger] = None,
                 cache_ttl_seconds: int = 3600):
        """
        Initializes the DBSchemaHandler.

        Args:
            db_config (Dict[str, Any]): Database connection configuration.
                Expected keys: 'host', 'port', 'username', 'password', 'database_name'.
                Alternatively, a 'connection_string' can be provided.
            logger (Optional[logging.Logger]): An optional logger instance.
            cache_ttl_seconds (int): Time-to-live for the schema cache in seconds.
        """
        self.db_config = db_config
        self.logger = logger if logger else self._get_default_logger()
        self.cache_ttl_seconds = cache_ttl_seconds
        self._schema_cache: Dict[str, Tuple[Any, float]] = {} # Cache key: (data, timestamp)

        if not PSYCOPG2_AVAILABLE:
            self.logger.error("psycopg2 library is not available. Database schema operations will be disabled.")
        else:
            self.logger.info("DBSchemaHandler initialized. psycopg2 is available.")
            # Test connection on init (optional, or defer to first actual use)
            # try:
            #     conn = self._get_db_connection()
            #     if conn:
            #         self.logger.info("Successfully connected to the database for initial check.")
            #         conn.close()
            #     else:
            #         self.logger.warning("Initial database connection test failed.")
            # except Exception as e:
            #     self.logger.error(f"Initial database connection test failed: {e}")


    def _get_default_logger(self) -> logging.Logger:
        logger = logging.getLogger(__name__)
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        return logger

    def _get_db_connection(self) -> Optional[psycopg2.extensions.connection]:
        """Establishes and returns a database connection."""
        if not PSYCOPG2_AVAILABLE:
            self.logger.error("Cannot get DB connection: psycopg2 not available.")
            return None
        try:
            if "connection_string" in self.db_config and self.db_config["connection_string"]:
                conn = psycopg2.connect(self.db_config["connection_string"])
            else:
                conn = psycopg2.connect(
                    host=self.db_config.get("host", "localhost"),
                    port=self.db_config.get("port", 5432),
                    user=self.db_config.get("username"),
                    password=self.db_config.get("password"),
                    dbname=self.db_config.get("database_name")
                )
            return conn
        except Exception as e:
            self.logger.error(f"Database connection failed: {e}")
            return None

    def _execute_query(self, query: str, params: Optional[Union[Dict, Tuple]] = None) -> Optional[List[Dict[str, Any]]]:
        """Executes a SQL query and returns results as a list of dictionaries."""
        conn = self._get_db_connection()
        if not conn:
            return None

        results: Optional[List[Dict[str, Any]]] = None
        try:
            # Use DictCursor to get results as dictionaries
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute(query, params)
                if cur.description: # Check if the query returns rows (e.g., SELECT)
                    results = [dict(row) for row in cur.fetchall()]
                else: # For queries like INSERT/UPDATE/DELETE that don't return rows by default
                    results = []
            conn.commit() # Important for any DML, though mostly SELECTs here
        except Exception as e:
            self.logger.error(f"Error executing query '{query[:100]}...': {e}")
            if conn: conn.rollback() # Rollback on error
        finally:
            if conn: conn.close()
        return results

    def _get_table_ddl(self, table_name: str, schema: str = 'public') -> Optional[str]:
        """
        Fetches an approximate DDL for a table or view using pg_get_tabledef
        or pg_get_viewdef for views. This is simpler than reconstructing from
        information_schema for basic use.
        """
        # Check if it's a view first
        view_def_query = """
        SELECT pg_get_viewdef(%s::regclass, true) AS ddl;
        """
        # Check if it's a table
        table_def_query = """
        SELECT pg_get_tabledef(%s::regclass, true) AS ddl;
        """
        # Fallback for more general DDL generation if specific functions are not available
        # or for more complex scenarios (not implemented here for brevity).
        # This simplified version relies on PostgreSQL specific functions.

        qualified_name = f'"{schema}"."{table_name}"'

        # Try view definition
        view_ddl_result = self._execute_query(view_def_query, (qualified_name,))
        if view_ddl_result and view_ddl_result[0]['ddl']:
            return f"CREATE VIEW {qualified_name} AS\n{view_ddl_result[0]['ddl']};"

        # Try table definition
        # Note: pg_get_tabledef might not be available or suitable for all needs.
        # A more robust approach would be to construct DDL from information_schema,
        # but that's significantly more complex.
        # For simplicity, we'll use a placeholder if pg_get_tabledef isn't used or fails.
        # A common approach is to query information_schema.columns.

        # Simplified column listing for tables if pg_get_tabledef is not preferred:
        columns_query = """
        SELECT column_name, data_type, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema = %s AND table_name = %s
        ORDER BY ordinal_position;
        """
        columns_info = self._execute_query(columns_query, (schema, table_name))
        if not columns_info:
            self.logger.warning(f"Could not retrieve column information for table {qualified_name}.")
            return f"-- Could not retrieve DDL for table {qualified_name}\n"

        ddl_parts = [f"CREATE TABLE {qualified_name} ("]
        for col in columns_info:
            col_def = f"    \"{col['column_name']}\" {col['data_type']}"
            if col['is_nullable'].upper() == 'NO':
                col_def += " NOT NULL"
            if col['column_default'] is not None:
                col_def += f" DEFAULT {col['column_default']}"
            ddl_parts.append(col_def + ",")

        if ddl_parts[-1].endswith(","): # Remove last comma
            ddl_parts[-1] = ddl_parts[-1][:-1]
        ddl_parts.append(");")
        return "\n".join(ddl_parts)


    def _get_timescaledb_object_types(self) -> Dict[str, str]:
        """
        Identifies TimescaleDB hypertables and continuous aggregates.
        Returns a dictionary mapping 'schema.table_name' to its TimescaleDB type.
        """
        ts_objects = {}
        if not PSYCOPG2_AVAILABLE: return ts_objects # Guard

        # Query for hypertables
        hypertable_query = """
        SELECT h.schema_name, h.table_name
        FROM timescaledb_information.hypertables h;
        """
        hypertables = self._execute_query(hypertable_query)
        if hypertables:
            for ht in hypertables:
                ts_objects[f"{ht['schema_name']}.{ht['table_name']}"] = "HYPERTABLE"

        # Query for continuous aggregates
        cagg_query = """
        SELECT c.user_view_schema AS schema_name, c.user_view_name AS table_name
        FROM timescaledb_information.continuous_aggregates c;
        """
        caggs = self._execute_query(cagg_query)
        if caggs:
            for ca in caggs:
                # If it was already identified as a hypertable (some caggs might be),
                # prioritize the CAGG designation or append. For now, CAGG takes precedence.
                ts_objects[f"{ca['schema_name']}.{ca['table_name']}"] = "CONTINUOUS AGGREGATE"

        self.logger.debug(f"Found TimescaleDB objects: {ts_objects}")
        return ts_objects

    def _get_all_tables_and_views(self, schema: str = 'public') -> List[Dict[str, str]]:
        """
        Gets a list of all tables and views from a given schema.
        Returns a list of dicts with 'table_name' and 'table_type' (VIEW or BASE TABLE).
        """
        query = """
        SELECT table_name, table_type
        FROM information_schema.tables
        WHERE table_schema = %s;
        """
        results = self._execute_query(query, (schema,))
        return results if results else []

    def _fetch_schema_data(self, table_names: Optional[List[str]] = None,
                            schema_name: str = 'public') -> Dict[str, Any]:
        """
        Fetches schema data, including DDLs and object types.
        If table_names is None, fetches for all tables and views in the schema.
        """
        self.logger.info(f"Fetching schema data for tables: {table_names or 'all'} in schema '{schema_name}'")
        schema_info: Dict[str, Any] = {"ddls": {}, "object_types": {}}

        if not PSYCOPG2_AVAILABLE:
            self.logger.error("psycopg2 not available, cannot fetch schema data.")
            return schema_info

        # Get TimescaleDB specific object types first
        ts_object_types = self._get_timescaledb_object_types()
        schema_info["timescale_types"] = ts_object_types

        if table_names is None: # Fetch all tables and views in the schema
            all_db_objects = self._get_all_tables_and_views(schema=schema_name)
            tables_to_process = [obj['table_name'] for obj in all_db_objects]
            # Store standard table types (VIEW or BASE TABLE)
            for obj in all_db_objects:
                full_name = f"{schema_name}.{obj['table_name']}"
                if full_name not in schema_info["object_types"]: # Prioritize TimescaleDB type if exists
                     schema_info["object_types"][full_name] = obj['table_type']
        else:
            tables_to_process = table_names
            # If specific tables are requested, we might need to query their base types
            # For simplicity, this is omitted here but could be added by querying information_schema.tables

        for table_name_item in tables_to_process:
            ddl = self._get_table_ddl(table_name_item, schema=schema_name)
            if ddl:
                full_name = f"{schema_name}.{table_name_item}"
                # Prepend TimescaleDB type if applicable
                ts_type = ts_object_types.get(full_name)
                if ts_type:
                    ddl = f"-- Object Type: {ts_type}\n{ddl}"
                schema_info["ddls"][table_name_item] = ddl

        return schema_info

    def get_schema_representation(self,
                                  table_names: Optional[List[str]] = None,
                                  mode: str = "create_table",
                                  schema_name: str = 'public') -> Union[str, Dict[str, str], List[str]]:
        """
        Retrieves and formats the database schema representation.

        Args:
            table_names (Optional[List[str]]): A list of specific table/view names
                to include. If None, all tables/views in the schema are included.
            mode (str): The desired format of the schema representation.
                Supported modes:
                - "create_table": Returns a string of DDL CREATE TABLE/VIEW statements.
                - "table_list_with_types": Returns a list of strings like
                  "table_name: STANDARD_TYPE (TIMESCALE_TYPE_IF_SPECIFIC)".
            schema_name (str): The database schema to inspect (e.g., 'public').

        Returns:
            Union[str, Dict[str, str], List[str]]: The schema representation in the
            specified mode. Type depends on mode. Returns an error message string
            if schema retrieval fails.
        """
        if not PSYCOPG2_AVAILABLE:
            return "Error: Database connector (psycopg2) not available."

        cache_key = f"{schema_name}_{mode}_{','.join(sorted(table_names)) if table_names else 'all'}"
        cached_data = self._schema_cache.get(cache_key)
        if cached_data and (time.time() - cached_data[1] < self.cache_ttl_seconds):
            self.logger.info(f"Returning cached schema representation for key: {cache_key}")
            return cached_data[0]

        self.logger.info(f"Fetching fresh schema representation (mode: {mode}) for key: {cache_key}")
        schema_data = self._fetch_schema_data(table_names=table_names, schema_name=schema_name)

        if not schema_data["ddls"] and mode == "create_table": # Check if DDLs were actually fetched
            self.logger.warning(f"No DDLs found for schema '{schema_name}' and tables '{table_names}'.")
            # Cache this empty result to avoid re-fetching immediately
            self._schema_cache[cache_key] = ("-- No tables found or DDLs could not be retrieved.", time.time())
            return self._schema_cache[cache_key][0]

        representation: Any
        if mode == "create_table":
            # Concatenate all DDLs, ensuring TimescaleDB comments are included
            all_ddls = []
            for table_name_item, ddl_str in schema_data["ddls"].items():
                full_name = f"{schema_name}.{table_name_item}"
                ts_type_comment = ""
                if schema_data["timescale_types"].get(full_name):
                    ts_type_comment = f"-- Object Type: {schema_data['timescale_types'][full_name]}\n"

                # Check if ddl_str already contains this comment from _fetch_schema_data
                if not ddl_str.startswith("-- Object Type:"):
                     all_ddls.append(ts_type_comment + ddl_str)
                else:
                    all_ddls.append(ddl_str)
            representation = "\n\n".join(all_ddls) if all_ddls else "-- No tables found or DDLs could not be retrieved."

        elif mode == "table_list_with_types":
            # Use all_tables_and_views if table_names was None, or filter based on provided table_names
            # This mode needs a list of all tables if table_names is None.
            object_list = []

            tables_to_describe = schema_data["ddls"].keys() if table_names is None else table_names
            # We need the base types (TABLE/VIEW) for these as well.
            # _fetch_schema_data stores base types in schema_data["object_types"]
            # and Timescale types in schema_data["timescale_types"]

            for name in tables_to_describe:
                full_name = f"{schema_name}.{name}"
                base_type = schema_data["object_types"].get(full_name, "UNKNOWN TYPE") # From information_schema.tables
                ts_type = schema_data["timescale_types"].get(full_name) # HYPERTABLE or CONTINUOUS AGGREGATE

                type_str = base_type
                if ts_type and ts_type != base_type : # e.g. base_type might be VIEW for a CAGG
                    if base_type == "VIEW" and ts_type == "CONTINUOUS AGGREGATE":
                        type_str = "CONTINUOUS AGGREGATE VIEW"
                    elif base_type == "BASE TABLE" and ts_type == "HYPERTABLE":
                        type_str = "HYPERTABLE"
                    else:
                        type_str = f"{base_type} ({ts_type})"
                object_list.append(f"{name}: {type_str}")
            representation = object_list if object_list else ["No tables or views found."]
        else:
            representation = f"Error: Unsupported schema representation mode '{mode}'."

        self._schema_cache[cache_key] = (representation, time.time())
        return representation

# Example Usage:
if __name__ == "__main__":
    # This example assumes a running PostgreSQL/TimescaleDB instance.
    # Replace with your actual database configuration.
    # Ensure PSYCOPG2_AVAILABLE is True (psycopg2 installed) for this to run.

    if not PSYCOPG2_AVAILABLE:
        print("psycopg2 is not installed. Skipping DBSchemaHandler example.")
    else:
        print("Running DBSchemaHandler example...")
        # Load from environment variables or use hardcoded defaults for testing
        test_db_config = {
            "host": os.getenv("NLSQL_DB_HOST_TEST", "localhost"),
            "port": int(os.getenv("NLSQL_DB_PORT_TEST", 5432)),
            "username": os.getenv("NLSQL_DB_USER_TEST", "postgres"),
            "password": os.getenv("NLSQL_DB_PASSWORD_TEST", "password"),
            "database_name": os.getenv("NLSQL_DB_NAME_TEST", "smart_factory_db") # Use your test DB
        }

        # Setup basic logging for the example
        example_logger = logging.getLogger("DBSchemaHandlerExample")
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        example_logger.addHandler(handler)
        example_logger.setLevel(logging.DEBUG)

        schema_handler = DBSchemaHandler(db_config=test_db_config, logger=example_logger, cache_ttl_seconds=5)

        # Test 1: Get DDL for all tables in public schema
        print("\n--- Test 1: DDL for all tables/views in 'public' schema ---")
        ddl_all = schema_handler.get_schema_representation(schema_name='public', mode="create_table")
        if isinstance(ddl_all, str):
            print(ddl_all)
        else:
            print(f"Unexpected type for DDL: {type(ddl_all)}")


        # Test 2: Get DDL for specific tables (if they exist in your test DB)
        # Replace with actual table names from your test DB
        # specific_tables = ["equipment", "equipment_alarm"]
        # print(f"\n--- Test 2: DDL for specific tables {specific_tables} ---")
        # ddl_specific = schema_handler.get_schema_representation(table_names=specific_tables, schema_name='public', mode="create_table")
        # if isinstance(ddl_specific, str):
        #      print(ddl_specific)


        # Test 3: Get table list with types
        print("\n--- Test 3: Table list with types for 'public' schema ---")
        list_types_all = schema_handler.get_schema_representation(schema_name='public', mode="table_list_with_types")
        if isinstance(list_types_all, list):
            for item in list_types_all:
                print(item)
        else:
             print(f"Unexpected type for list_types: {type(list_types_all)}")

        # Test caching (call again, should be faster and log cache hit)
        # print("\n--- Test 4: Cached DDL for all tables (should be faster) ---")
        # time.sleep(1) # Ensure timestamp is different enough for a theoretical check
        # ddl_all_cached = schema_handler.get_schema_representation(schema_name='public', mode="create_table")
        # print("Second call for DDL (cached) done. Check logs for cache hit message.")

        # print("\n--- Test 5: Expired Cache (wait for TTL+1 seconds) ---")
        # time.sleep(schema_handler.cache_ttl_seconds + 1)
        # ddl_all_expired = schema_handler.get_schema_representation(schema_name='public', mode="create_table")
        # print("Third call for DDL (after cache expiry) done. Check logs for fresh fetch message.")

        # Test with a non-existent schema (or one without permissions)
        # print("\n--- Test 6: Non-existent schema ---")
        # ddl_non_existent_schema = schema_handler.get_schema_representation(schema_name='non_existent_schema', mode="create_table")
        # print(ddl_non_existent_schema)

        # Note: To fully test TimescaleDB features, you'd need a TimescaleDB instance
        # with hypertables and continuous aggregates defined. The queries for these
        # would run but return empty if those objects don't exist.
        print("\nTo fully test TimescaleDB object identification, ensure your test DB has hypertables and/or continuous aggregates.")
