# nl_to_sql_service/tests/test_db_schema_handler.py
import unittest
from unittest.mock import patch, MagicMock, PropertyMock
import time
import logging
import os # For path joining if needed

# Adjust path to import from the nl_to_sql_service package
import sys
PACKAGE_PARENT = os.path.join(os.path.dirname(__file__), '..', '..')
sys.path.insert(0, os.path.normpath(PACKAGE_PARENT))

from nl_to_sql_service.db_schema_handler import DBSchemaHandler

# Mock psycopg2 globally for all tests in this file
# This ensures that no real DB connection is attempted.
mock_psycopg2 = MagicMock()
# Mock the DictCursor to be a callable that returns a MagicMock
mock_psycopg2.extras.DictCursor = MagicMock(return_value=MagicMock())

# We need to control what `psycopg2.connect().cursor().fetchall()` returns,
# and what `cursor.description` contains.
# The cursor mock needs to be sophisticated or we mock _execute_query directly in tests.
# For simplicity in this pass, we will often patch _execute_query directly in tests
# as setting up the full chain of connect -> cursor -> execute -> fetchall -> description
# for every test case via a global mock is very complex.

# However, for testing _get_db_connection and parts of _execute_query, we need the connect mock.
mock_db_connection = MagicMock()
mock_db_cursor = MagicMock()
mock_db_connection.cursor.return_value.__enter__.return_value = mock_db_cursor # For 'with ... as cur:'

@patch.dict('sys.modules', {'psycopg2': mock_psycopg2, 'psycopg2.extras': mock_psycopg2.extras})
class TestDBSchemaHandler(unittest.TestCase):
    """
    Unit tests for the DBSchemaHandler class.
    Mocks psycopg2 to avoid actual database connections.
    """

    def setUp(self):
        """Set up for each test."""
        self.logger = logging.getLogger(__name__)
        logging.disable(logging.CRITICAL) # Disable logging during tests unless debugging a test

        self.db_config_dict = {
            "host": "testhost", "port": 1234, "username": "testuser",
            "password": "testpassword", "database_name": "testdb"
        }
        self.db_config_conn_str = {
            "connection_string": "postgresql://user:pass@host:port/db"
        }
        # Reset global mock_psycopg2 behavior for each test if needed, esp. for connect
        mock_psycopg2.connect.reset_mock(return_value=True, side_effect=True)
        mock_psycopg2.Error = Exception # Mock psycopg2.Error as a generic Exception for tests

        # Ensure PSYCOPG2_AVAILABLE is True for tests that rely on it being patched
        # The patch.dict should handle the import-time check if DBSchemaHandler re-evaluates it.
        # If DBSchemaHandler caches PSYCOPG2_AVAILABLE at module level, this might be tricky.
        # Assuming DBSchemaHandler checks PSYCOPG2_AVAILABLE when methods are called or at init.
        # Forcing the module variable if it's checked at import time by the class:
        self.patch_psycopg2_available = patch('nl_to_sql_service.db_schema_handler.PSYCOPG2_AVAILABLE', True)
        self.patch_psycopg2_available.start()


    def tearDown(self):
        """Clean up after each test."""
        logging.disable(logging.NOTSET)
        self.patch_psycopg2_available.stop()


    def test_init_success_and_psycopg2_available(self):
        """Test successful initialization when psycopg2 is available."""
        handler = DBSchemaHandler(self.db_config_dict, logger=self.logger)
        self.assertIsNotNone(handler)
        self.assertTrue(handler.PSYCOPG2_AVAILABLE if hasattr(handler, 'PSYCOPG2_AVAILABLE') else True)


    @patch('nl_to_sql_service.db_schema_handler.PSYCOPG2_AVAILABLE', False)
    def test_init_psycopg2_not_available(self):
        """Test initialization logs error if psycopg2 is not available."""
        with self.assertLogs(self.logger, level='ERROR') as log_cm:
            DBSchemaHandler(self.db_config_dict, logger=self.logger)
        self.assertIn("psycopg2 library is not available", log_cm.output[0])

    def test_get_db_connection_success_params(self):
        """Test successful DB connection using parameters."""
        mock_psycopg2.connect.return_value = mock_db_connection
        handler = DBSchemaHandler(self.db_config_dict, logger=self.logger)
        conn = handler._get_db_connection()
        self.assertIsNotNone(conn)
        mock_psycopg2.connect.assert_called_once_with(
            host="testhost", port=1234, user="testuser",
            password="testpassword", dbname="testdb"
        )

    def test_get_db_connection_success_conn_str(self):
        """Test successful DB connection using connection string."""
        mock_psycopg2.connect.return_value = mock_db_connection
        handler = DBSchemaHandler(self.db_config_conn_str, logger=self.logger)
        conn = handler._get_db_connection()
        self.assertIsNotNone(conn)
        mock_psycopg2.connect.assert_called_once_with("postgresql://user:pass@host:port/db")

    def test_get_db_connection_failure(self):
        """Test DB connection failure."""
        mock_psycopg2.connect.side_effect = mock_psycopg2.Error("Connection failed")
        handler = DBSchemaHandler(self.db_config_dict, logger=self.logger)
        with self.assertLogs(self.logger, level='ERROR') as log_cm:
            conn = handler._get_db_connection()
        self.assertIsNone(conn)
        self.assertIn("Database connection failed", log_cm.output[0])

    @patch.object(DBSchemaHandler, '_get_db_connection')
    def test_execute_query_success_select(self, mock_get_conn):
        """Test _execute_query with a successful SELECT."""
        mock_get_conn.return_value = mock_db_connection
        mock_db_cursor.fetchall.return_value = [{'col1': 'val1'}, {'col1': 'val2'}]
        # Mock cursor.description to indicate that columns were returned
        type(mock_db_cursor).description = PropertyMock(return_value=[('col1', None, None, None, None, None, None)])

        handler = DBSchemaHandler(self.db_config_dict, logger=self.logger)
        results = handler._execute_query("SELECT col1 FROM test_table")
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]['col1'], 'val1')
        mock_db_cursor.execute.assert_called_once()
        mock_db_connection.commit.assert_called_once() # Should be called even for SELECTs in current impl

    @patch.object(DBSchemaHandler, '_get_db_connection')
    def test_execute_query_success_no_results(self, mock_get_conn):
        """Test _execute_query with a successful command that returns no rows (like EXPLAIN)."""
        mock_get_conn.return_value = mock_db_connection
        mock_db_cursor.fetchall.return_value = []
        # If EXPLAIN returns rows (some formats do), description will be set.
        # If it doesn't, description might be None or empty.
        # Let's assume EXPLAIN might set description if it's a valid command.
        type(mock_db_cursor).description = PropertyMock(return_value=[('QUERY PLAN', None)])

        handler = DBSchemaHandler(self.db_config_dict, logger=self.logger)
        results = handler._execute_query("EXPLAIN SELECT col1 FROM test_table")
        self.assertEqual(len(results), 0) # Empty list for success, no rows
        mock_db_cursor.execute.assert_called_once()

    @patch.object(DBSchemaHandler, '_get_db_connection')
    def test_execute_query_db_error(self, mock_get_conn):
        """Test _execute_query when database raises an error."""
        mock_get_conn.return_value = mock_db_connection
        mock_db_cursor.execute.side_effect = mock_psycopg2.Error("DB error")

        handler = DBSchemaHandler(self.db_config_dict, logger=self.logger)
        with self.assertLogs(self.logger, level='ERROR') as log_cm:
            results = handler._execute_query("SELECT col1 FROM error_table")
        self.assertIsNone(results)
        self.assertIn("Error executing query", log_cm.output[0])
        mock_db_connection.rollback.assert_called_once()


    def test_get_table_ddl_simple_table(self):
        """Test DDL generation for a simple table."""
        handler = DBSchemaHandler(self.db_config_dict, logger=self.logger)
        mock_column_data = [
            {'column_name': 'id', 'data_type': 'integer', 'is_nullable': 'NO', 'column_default': None},
            {'column_name': 'name', 'data_type': 'text', 'is_nullable': 'YES', 'column_default': "'default_name'::text"}
        ]
        # Mock _execute_query: first call for view (returns no DDL), second for columns
        with patch.object(handler, '_execute_query', side_effect=[
            [{'ddl': None}], # For pg_get_viewdef
            mock_column_data  # For information_schema.columns
        ]) as mock_exec:
            ddl = handler._get_table_ddl("my_table")
            self.assertIn('CREATE TABLE "public"."my_table"', ddl)
            self.assertIn('"id" integer NOT NULL', ddl)
            self.assertIn('"name" text DEFAULT \'default_name\'::text', ddl)
            self.assertEqual(mock_exec.call_count, 2)

    def test_get_table_ddl_view(self):
        """Test DDL generation for a view."""
        handler = DBSchemaHandler(self.db_config_dict, logger=self.logger)
        mock_view_ddl = " SELECT col_a FROM some_other_table;"
        with patch.object(handler, '_execute_query', return_value=[{'ddl': mock_view_ddl}]) as mock_exec:
            ddl = handler._get_table_ddl("my_view")
            self.assertIn('CREATE VIEW "public"."my_view" AS', ddl)
            self.assertIn(mock_view_ddl, ddl)
            mock_exec.assert_called_once() # Should only call for view def

    @patch.object(DBSchemaHandler, '_execute_query')
    def test_get_timescaledb_object_types(self, mock_exec_query):
        """Test identification of TimescaleDB objects."""
        mock_exec_query.side_effect = [
            [{'schema_name': 'public', 'table_name': 'hyper_table'}], # Hypertables
            [{'schema_name': 'public', 'table_name': 'cagg_view'}]    # Continuous Aggregates
        ]
        handler = DBSchemaHandler(self.db_config_dict, logger=self.logger)
        ts_types = handler._get_timescaledb_object_types()
        self.assertEqual(ts_types.get('public.hyper_table'), 'HYPERTABLE')
        self.assertEqual(ts_types.get('public.cagg_view'), 'CONTINUOUS AGGREGATE')

    @patch.object(DBSchemaHandler, '_fetch_schema_data')
    def test_get_schema_representation_caching(self, mock_fetch_schema_data):
        """Test schema representation caching."""
        # Mock return value for _fetch_schema_data
        mock_fetch_schema_data.return_value = {
            "ddls": {"table1": "CREATE TABLE table1 (id INT);"},
            "object_types": {"public.table1": "BASE TABLE"},
            "timescale_types": {}
        }

        handler = DBSchemaHandler(self.db_config_dict, logger=self.logger, cache_ttl_seconds=10)

        # First call - should call _fetch_schema_data
        handler.get_schema_representation(table_names=["table1"], mode="create_table")
        mock_fetch_schema_data.assert_called_once()

        # Second call (within TTL) - should use cache
        mock_fetch_schema_data.reset_mock()
        handler.get_schema_representation(table_names=["table1"], mode="create_table")
        mock_fetch_schema_data.assert_not_called()

        # Third call (after TTL) - should call _fetch_schema_data again
        mock_fetch_schema_data.reset_mock()
        # Mock time.time() to simulate cache expiry
        with patch('time.time', return_value=time.time() + 15):
            handler.get_schema_representation(table_names=["table1"], mode="create_table")
            mock_fetch_schema_data.assert_called_once()

    # More tests for _fetch_schema_data to verify consolidation
    # More tests for get_schema_representation with different modes and filters

if __name__ == '__main__':
    unittest.main()
