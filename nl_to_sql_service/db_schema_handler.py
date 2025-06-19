# nl_to_sql_service/db_schema_handler.py
"""Handles fetching, caching, and formatting of database schema information.

This module provides the DBSchemaHandler class, which connects to a specified
PostgreSQL (and TimescaleDB-aware) database, retrieves schema details such as
table definitions, view definitions, and identifies TimescaleDB-specific objects
like hypertables and continuous aggregates. It supports caching of schema
representations to improve performance for repeated requests.
"""
import time
import logging
from typing import Dict, List, Optional, Any, Tuple, Union

# Attempt to import psycopg2 for PostgreSQL connectivity
try:
    import psycopg2
    import psycopg2.extras # For DictCursor, which returns rows as dictionaries
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False
    psycopg2 = None
    DictCursor = None

class DBSchemaHandler:
    """Manages database schema information retrieval and formatting.

    This class connects to a PostgreSQL database, fetches schema details
    (including DDLs for tables/views and specific TimescaleDB object types),
    caches these details, and provides them in various formats suitable for
    inclusion in LLM prompts for NL-to-SQL tasks.

    Attributes:
        db_config (Dict[str, Any]): Configuration for database connection.
        logger (logging.Logger): Logger for messages.
        cache_ttl_seconds (int): Time-to-live for schema cache.
        _schema_cache (Dict[str, Tuple[Any, float]]): Internal cache for schema data.
    """

    def __init__(self, db_config: Dict[str, Any],
                 logger: Optional[logging.Logger] = None,
                 cache_ttl_seconds: int = 3600):
        """Initializes the DBSchemaHandler."""
        self.db_config = db_config
        self.logger = logger if logger else self._get_default_logger()
        self.cache_ttl_seconds = cache_ttl_seconds
        self._schema_cache: Dict[str, Tuple[Any, float]] = {}

        if not PSYCOPG2_AVAILABLE:
            self.logger.error("psycopg2 library is not available. Database schema operations will be disabled.")
        else:
            self.logger.info("DBSchemaHandler initialized. psycopg2 library is available.")

    def _get_default_logger(self) -> logging.Logger:
        """Creates and configures a default logger if one is not provided."""
        logger = logging.getLogger(__name__)
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        return logger

    def _get_db_connection(self) -> Optional[psycopg2.extensions.connection]:
        """Establishes and returns a new database connection."""
        if not PSYCOPG2_AVAILABLE or psycopg2 is None:
            self.logger.error("Cannot get DB connection: psycopg2 library not available.")
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
            self.logger.debug("Database connection established successfully.")
            return conn
        except psycopg2.Error as e:
            self.logger.error(f"Database connection failed using psycopg2: {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"An unexpected error occurred during database connection: {e}", exc_info=True)
            return None

    def _execute_query(self, query: str, params: Optional[Union[Dict[str, Any], Tuple[Any, ...]]] = None) -> Optional[List[Dict[str, Any]]]:
        """Executes a SQL query and returns results as a list of dictionaries."""
        conn = self._get_db_connection()
        if not conn:
            self.logger.error("Query execution failed: No database connection.")
            return None

        results: Optional[List[Dict[str, Any]]] = None
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor if DictCursor else None) as cur:
                self.logger.debug(f"Executing query (first 100 chars): {query[:100]}...")
                cur.execute(query, params)
                if cur.description:
                    results = [dict(row) for row in cur.fetchall()]
                else:
                    results = []
            conn.commit()
        except psycopg2.Error as e:
            self.logger.error(f"Error executing query '{query[:100]}...': {e}", exc_info=True)
            if conn: conn.rollback()
        except Exception as e:
            self.logger.error(f"An unexpected error occurred during query execution: {e}", exc_info=True)
            if conn: conn.rollback()
        finally:
            if conn: conn.close()
        return results

    def _get_table_comments(self, schema: str = 'public') -> Dict[str, str]:
        """Fetches comments for all tables and views in the specified schema."""
        comments: Dict[str, str] = {}
        if not PSYCOPG2_AVAILABLE: return comments
        query = """
        SELECT c.relname AS name, pgd.description
        FROM pg_catalog.pg_class c
        JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
        LEFT JOIN pg_catalog.pg_description pgd ON pgd.objoid = c.oid AND pgd.objsubid = 0
        WHERE n.nspname = %s AND c.relkind IN ('r', 'v', 'm', 'p'); -- r=table, v=view, m=materialized view, p=partitioned table
        """
        results = self._execute_query(query, (schema,))
        if results:
            for row in results:
                if row['description']:
                    comments[row['name']] = row['description']
        return comments

    def _get_column_details(self, table_name: str, schema: str = 'public') -> List[Dict[str, Any]]:
        """Fetches detailed information for columns of a specific table."""
        columns: List[Dict[str, Any]] = []
        if not PSYCOPG2_AVAILABLE: return columns
        query = """
        SELECT
            c.column_name,
            c.data_type,
            c.is_nullable,
            c.column_default,
            pgd.description
        FROM information_schema.columns c
        LEFT JOIN pg_catalog.pg_class pc ON pc.relname = c.table_name
        LEFT JOIN pg_catalog.pg_namespace pn ON pn.oid = pc.relnamespace AND pn.nspname = c.table_schema
        LEFT JOIN pg_catalog.pg_description pgd ON pgd.objoid = pc.oid AND pgd.objsubid = c.ordinal_position
        WHERE c.table_schema = %s AND c.table_name = %s
        ORDER BY c.ordinal_position;
        """
        results = self._execute_query(query, (schema, table_name))
        if results:
            for row in results:
                columns.append({
                    "name": row["column_name"],
                    "type": row["data_type"],
                    "is_nullable": row["is_nullable"].upper() == "YES",
                    "default": row["column_default"],
                    "description": row["description"]
                })
        return columns

    def _get_primary_keys(self, table_name: str, schema: str = 'public') -> List[str]:
        """Fetches primary key columns for a specific table."""
        pks: List[str] = []
        if not PSYCOPG2_AVAILABLE: return pks
        query = """
        SELECT kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
        WHERE tc.constraint_type = 'PRIMARY KEY'
          AND tc.table_schema = %s AND tc.table_name = %s
        ORDER BY kcu.ordinal_position;
        """
        results = self._execute_query(query, (schema, table_name))
        if results:
            pks = [row['column_name'] for row in results]
        return pks

    def _get_foreign_keys(self, table_name: str, schema: str = 'public') -> List[Dict[str, str]]:
        """Fetches foreign key relationships for a specific table."""
        fks: List[Dict[str, str]] = []
        if not PSYCOPG2_AVAILABLE: return fks
        query = """
        SELECT
            kcu.column_name,
            ccu.table_schema AS foreign_table_schema,
            ccu.table_name AS foreign_table_name,
            ccu.column_name AS foreign_column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage ccu
            ON ccu.constraint_name = tc.constraint_name AND ccu.constraint_schema = tc.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_schema = %s AND tc.table_name = %s;
        """
        results = self._execute_query(query, (schema, table_name))
        if results:
            for row in results:
                fks.append({
                    "column": row["column_name"],
                    "references_table": f"{row['foreign_table_schema']}.{row['foreign_table_name']}", # Qualified name
                    "references_column": row["foreign_column_name"]
                })
        return fks

    def _get_timescaledb_details(self, schema: str = 'public') -> Dict[str, Any]:
        """Fetches TimescaleDB specific details like hypertables, dimensions, and cagg definitions."""
        ts_details: Dict[str, Any] = {"hypertables": {}, "continuous_aggregates": {}}
        if not PSYCOPG2_AVAILABLE: return ts_details

        # Hypertables and their dimensions
        hypertable_query = """
        SELECT
            h.schema_name AS hypertable_schema,
            h.table_name AS hypertable_name,
            d.column_name,
            d.column_type,
            d.dimension_type,
            d.num_partitions
        FROM timescaledb_information.hypertables h
        JOIN timescaledb_information.dimensions d ON h.hypertable_name = d.hypertable_name AND h.schema_name = d.hypertable_schema
        WHERE h.schema_name = %s;
        """
        hypertable_results = self._execute_query(hypertable_query, (schema,))
        if hypertable_results:
            for row in hypertable_results:
                ht_qualified_name = f"{row['hypertable_schema']}.{row['hypertable_name']}"
                if ht_qualified_name not in ts_details["hypertables"]:
                    ts_details["hypertables"][ht_qualified_name] = {"dimensions": []}
                ts_details["hypertables"][ht_qualified_name]["dimensions"].append({
                    "column_name": row["column_name"],
                    "column_type": row["column_type"],
                    "dimension_type": row["dimension_type"],
                    "num_partitions": row["num_partitions"]
                })

        # Continuous aggregates and their definitions
        cagg_query = """
        SELECT
            cv.viewschema AS cagg_schema,
            cv.viewname AS cagg_name,
            cv.definition AS cagg_definition
        FROM pg_catalog.pg_views cv -- CAGGs are implemented as views
        JOIN timescaledb_information.continuous_aggregates ca
            ON cv.viewschema = ca.user_view_schema AND cv.viewname = ca.user_view_name
        WHERE cv.viewschema = %s;
        """
        # Alternative: Use pg_matviews if CAGGs are strictly materialized views
        # cagg_query = """
        # SELECT schemaname as cagg_schema, matviewname as cagg_name, definition as cagg_definition
        # FROM pg_matviews
        # WHERE schemaname = %s AND matviewname IN (SELECT user_view_name FROM timescaledb_information.continuous_aggregates);
        # """
        cagg_results = self._execute_query(cagg_query, (schema,))
        if cagg_results:
            for row in cagg_results:
                cagg_qualified_name = f"{row['cagg_schema']}.{row['cagg_name']}"
                ts_details["continuous_aggregates"][cagg_qualified_name] = {
                    "definition": row["cagg_definition"]
                }

        self.logger.debug(f"Fetched TimescaleDB details for schema '{schema}': {ts_details}")
        return ts_details

    def _fetch_schema_data(self, table_names: Optional[List[str]] = None,
                            schema_name: str = 'public') -> Dict[str, Dict[str, Any]]:
        """Fetches detailed structured schema information for specified tables or all tables.

        Args:
            table_names: Optional list of table names to fetch. If None, fetches all.
            schema_name: The schema to inspect.

        Returns:
            A dictionary where keys are table names and values are dictionaries
            containing detailed schema information for that table.
        """
        self.logger.info(f"Fetching detailed schema data for tables: {table_names or 'all'} in schema '{schema_name}'")
        structured_schema_info: Dict[str, Dict[str, Any]] = {}

        if not PSYCOPG2_AVAILABLE:
            self.logger.error("psycopg2 not available, cannot fetch schema data.")
            return structured_schema_info

        # Get all tables and views if specific table_names are not provided
        db_objects_to_process: List[Dict[str, str]]
        if table_names is None:
            db_objects_to_process = self._get_all_tables_and_views(schema=schema_name)
        else:
            # If specific table names are given, we still need their types for context
            all_db_objects_map = {obj['table_name']: obj['table_type']
                                  for obj in self._get_all_tables_and_views(schema=schema_name)}
            db_objects_to_process = []
            for name in table_names:
                obj_type = all_db_objects_map.get(name)
                if obj_type:
                    db_objects_to_process.append({'table_name': name, 'table_type': obj_type})
                else:
                    self.logger.warning(f"Table or view '{name}' not found in schema '{schema_name}'.")

        if not db_objects_to_process:
            self.logger.warning(f"No tables or views found to process in schema '{schema_name}'.")
            return structured_schema_info

        table_comments = self._get_table_comments(schema=schema_name)
        timescale_details = self._get_timescaledb_details(schema=schema_name)

        for db_obj in db_objects_to_process:
            table_name_item = db_obj['table_name']
            base_table_type = db_obj['table_type'] # e.g. BASE TABLE, VIEW
            qualified_name_for_ts = f"{schema_name}.{table_name_item}"

            self.logger.debug(f"Processing schema for: {qualified_name_for_ts}")

            columns = self._get_column_details(table_name_item, schema=schema_name)
            primary_keys = self._get_primary_keys(table_name_item, schema=schema_name)
            foreign_keys = self._get_foreign_keys(table_name_item, schema=schema_name)

            # Mark PKs in column details
            for col in columns:
                col["is_pk"] = col["name"] in primary_keys

            table_info: Dict[str, Any] = {
                "table_type": base_table_type,
                "description": table_comments.get(table_name_item),
                "columns": columns,
                "primary_keys": primary_keys,
                "foreign_keys": foreign_keys,
                # Placeholder for sample enum values - to be implemented if needed
                "sample_enum_values": {}
            }

            # Add TimescaleDB specific info
            if qualified_name_for_ts in timescale_details["hypertables"]:
                table_info["table_type"] = "HYPERTABLE" # Override base type
                table_info["timescale_dimensions"] = timescale_details["hypertables"][qualified_name_for_ts]["dimensions"]
            if qualified_name_for_ts in timescale_details["continuous_aggregates"]:
                table_info["table_type"] = "CONTINUOUS AGGREGATE" # Override base type (likely VIEW)
                table_info["continuous_aggregate_definition"] = timescale_details["continuous_aggregates"][qualified_name_for_ts]["definition"]

            structured_schema_info[table_name_item] = table_info

        return structured_schema_info

    def get_schema_representation(self,
                                  table_names: Optional[List[str]] = None,
                                  mode: str = "create_table", # "create_table" or "structured_dict" or "table_list_with_types"
                                  schema_name: str = 'public') -> Union[str, List[str], Dict[str, Dict[str, Any]]]:
        """Retrieves and formats database schema, using caching.

        Args:
            table_names: Optional list of table/view names. If None, all are used.
            mode: Format of the schema.
                - "create_table": Returns simplified DDL string.
                - "table_list_with_types": Returns List[str] like "name: TYPE (TS_TYPE)".
                - "structured_dict": Returns the rich dictionary from `_fetch_schema_data`.
            schema_name: Database schema to inspect.

        Returns:
            Schema representation based on mode, or error string.
        """
        if not PSYCOPG2_AVAILABLE:
            self.logger.error("Schema retrieval failed: psycopg2 not available.")
            return "Error: Database connector (psycopg2) not available."

        sorted_table_names_key = "_".join(sorted(table_names)) if table_names else "all"
        cache_key = f"{schema_name}_{mode}_{sorted_table_names_key}"

        cached_entry = self._schema_cache.get(cache_key)
        if cached_entry and (time.time() - cached_entry[1] < self.cache_ttl_seconds):
            self.logger.info(f"Returning cached schema for key: {cache_key}")
            return cached_entry[0]

        self.logger.info(f"Fetching fresh schema (mode: {mode}) for key: {cache_key}")

        # For "create_table" and "table_list_with_types", we need the structured data first
        # then format it. For "structured_dict", we return it directly.
        # The _fetch_schema_data is now the primary source of detailed info.

        # Fetch detailed structured data first, regardless of mode (unless mode is simple list without details)
        # The `table_names` argument to _fetch_schema_data will limit what's fetched.
        structured_data = self._fetch_schema_data(table_names=table_names, schema_name=schema_name)

        if not structured_data:
             self.logger.warning(f"No schema data fetched for schema '{schema_name}', tables '{table_names}'.")
             representation: Union[str, List[str], Dict[str, Dict[str, Any]]]
             if mode == "create_table": representation = "-- No tables found or schema could not be retrieved."
             elif mode == "table_list_with_types": representation = ["-- No tables or views found --"]
             else: representation = {} # structured_dict
             self._schema_cache[cache_key] = (representation, time.time())
             return representation

        representation: Union[str, List[str], Dict[str, Dict[str, Any]]]
        if mode == "structured_dict":
            representation = structured_data
        elif mode == "create_table":
            all_ddls = []
            for table_name_item, table_info_dict in structured_data.items():
                # Construct a simplified DDL from structured_info for consistency
                # This can reuse parts of the old _get_table_ddl or be a new formatter.
                # For now, let's use the existing _get_table_ddl which is simpler.
                # A more robust way would be to build DDL from table_info_dict.
                ddl_str = self._get_table_ddl(table_name_item, schema=schema_name) # This is an approximation
                if ddl_str:
                    # Prepend TimescaleDB object type if available from structured_data
                    final_ddl_str = ddl_str
                    if table_info_dict.get("table_type") == "HYPERTABLE" and not ddl_str.startswith("-- Object Type: HYPERTABLE"):
                        final_ddl_str = f"-- Object Type: HYPERTABLE\n{ddl_str}"
                    elif table_info_dict.get("table_type") == "CONTINUOUS AGGREGATE" and not ddl_str.startswith("-- Object Type: CONTINUOUS AGGREGATE"):
                         final_ddl_str = f"-- Object Type: CONTINUOUS AGGREGATE\n{ddl_str}"
                    # Add table description
                    if table_info_dict.get("description"):
                        final_ddl_str += f"\nCOMMENT ON TABLE \"{schema_name}\".\"{table_name_item}\" IS '{table_info_dict['description'].replace(\"'\", \"''\")}';"
                    # Add column descriptions
                    for col_info in table_info_dict.get("columns", []):
                        if col_info.get("description"):
                            final_ddl_str += f"\nCOMMENT ON COLUMN \"{schema_name}\".\"{table_name_item}\".\"{col_info['name']}\" IS '{col_info['description'].replace(\"'\", \"''\")}';"
                    all_ddls.append(final_ddl_str)
            representation = "\n\n".join(all_ddls) if all_ddls else "-- No DDLs generated --"

        elif mode == "table_list_with_types":
            object_list = []
            for table_name_item, table_info_dict in structured_data.items():
                type_str = table_info_dict.get("table_type", "UNKNOWN")
                # More specific Timescale types were already set in table_type by _fetch_schema_data
                object_list.append(f"{table_name_item}: {type_str}")
            representation = object_list if object_list else ["-- No tables or views found --"]

        else:
            self.logger.error(f"Unsupported schema representation mode: '{mode}'")
            representation = f"Error: Unsupported schema representation mode '{mode}'."

        self._schema_cache[cache_key] = (representation, time.time())
        return representation

# Example Usage:
if __name__ == "__main__":
    if not PSYCOPG2_AVAILABLE:
        print("psycopg2 is not installed. Skipping DBSchemaHandler example.")
    else:
        print("Running DBSchemaHandler example (ensure test DB is configured and running)...")
        test_db_config = {
            "host": os.getenv("NLSQL_DB_HOST_TEST", "localhost"),
            "port": int(os.getenv("NLSQL_DB_PORT_TEST", 5432)),
            "username": os.getenv("NLSQL_DB_USER_TEST", "postgres"),
            "password": os.getenv("NLSQL_DB_PASSWORD_TEST", "password"),
            "database_name": os.getenv("NLSQL_DB_NAME_TEST", "smart_factory_db")
        }

        example_logger = logging.getLogger("DBSchemaHandlerExample")
        if not example_logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            example_logger.addHandler(handler)
        example_logger.setLevel(logging.DEBUG)

        schema_handler = DBSchemaHandler(db_config=test_db_config, logger=example_logger, cache_ttl_seconds=60)

        print("\n--- Test 1: Fetch structured data for all tables/views in 'public' schema ---")
        structured_all = schema_handler.get_schema_representation(schema_name='public', mode="structured_dict")
        if isinstance(structured_all, dict):
            for table_name, details in structured_all.items():
                print(f"\nTable/View: {table_name} (Type: {details.get('table_type')})")
                if details.get("description"): print(f"  Description: {details['description']}")
                if details.get("timescale_dimensions"): print(f"  Timescale Dimensions: {details['timescale_dimensions']}")
                if details.get("continuous_aggregate_definition"): print(f"  CA Def (snippet): {details['continuous_aggregate_definition'][:100]}...")
                print(f"  Primary Keys: {details.get('primary_keys')}")
                print(f"  Foreign Keys: {details.get('foreign_keys')}")
                for col in details.get("columns", []):
                    print(f"    Col: {col['name']} ({col['type']}) "
                          f"Nullable: {col['is_nullable']} PK: {col.get('is_pk', False)} "
                          f"Desc: {col.get('description')}")
        else:
            print(f"Unexpected type for structured_all: {type(structured_all)}")
            print(structured_all)

        # Test DDL generation (now potentially richer with comments from structured data)
        print("\n--- Test 2: DDL for all tables/views in 'public' schema (using new structured data) ---")
        ddl_all_new = schema_handler.get_schema_representation(schema_name='public', mode="create_table")
        print(ddl_all_new)

        print("\nTo fully test TimescaleDB object identification, ensure your test DB has hypertables and/or continuous aggregates.")

```
