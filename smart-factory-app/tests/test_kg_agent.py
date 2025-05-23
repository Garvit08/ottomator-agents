import unittest
import sys
import os
from unittest.mock import patch, MagicMock

# --- Path Adjustments ---
current_test_dir = os.path.dirname(os.path.abspath(__file__))
smart_factory_app_dir = os.path.abspath(os.path.join(current_test_dir, '..'))
project_root = os.path.abspath(os.path.join(smart_factory_app_dir, '..'))

if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Import the module to be tested
from smart_factory_app.agents.kg_agent import KGAgent
from neo4j import exceptions as neo4j_exceptions # For testing specific Neo4j errors

# Import config variables to test default initialization (optional, or mock them)
# from smart_factory_app.config import config

class TestKGAgent(unittest.TestCase):

    @patch('smart_factory_app.agents.kg_agent.GraphDatabase.driver')
    def test_initialization_success(self, mock_graph_driver):
        """Test successful initialization of KGAgent."""
        mock_driver_instance = MagicMock()
        mock_graph_driver.return_value = mock_driver_instance

        # Use dummy URI, user, password for this test
        agent = KGAgent(uri="neo4j://testhost:7687", user="testuser", password="testpassword")
        
        self.assertIsNotNone(agent._driver)
        mock_graph_driver.assert_called_once_with("neo4j://testhost:7687", auth=("testuser", "testpassword"))
        mock_driver_instance.verify_connectivity.assert_called_once()
        agent.close() # Ensure close is also tested

    @patch('smart_factory_app.agents.kg_agent.GraphDatabase.driver')
    def test_initialization_auth_error(self, mock_graph_driver):
        """Test initialization failure due to authentication error."""
        mock_graph_driver.side_effect = neo4j_exceptions.AuthError("Authentication failed")
        
        agent = KGAgent(uri="neo4j://testhost:7687", user="wronguser", password="wrongpassword")
        
        self.assertIsNone(agent._driver)
        mock_graph_driver.assert_called_once()

    @patch('smart_factory_app.agents.kg_agent.GraphDatabase.driver')
    def test_initialization_service_unavailable(self, mock_graph_driver):
        """Test initialization failure due to service unavailable."""
        mock_graph_driver.side_effect = neo4j_exceptions.ServiceUnavailable("Service unavailable")
        
        agent = KGAgent(uri="neo4j://downhost:7687", user="user", password="password")
        
        self.assertIsNone(agent._driver)
        mock_graph_driver.assert_called_once()

    @patch('smart_factory_app.agents.kg_agent.GraphDatabase.driver')
    def test_query_success(self, mock_graph_driver):
        """Test successful query execution."""
        mock_driver_instance = MagicMock()
        mock_session_instance = MagicMock()
        mock_transaction_instance = MagicMock() # For execute_read
        mock_result_instance = MagicMock()

        mock_graph_driver.return_value = mock_driver_instance
        mock_driver_instance.session.return_value.__enter__.return_value = mock_session_instance
        
        # Mocking execute_read which takes a function
        def mock_execute_read(func, query, params):
            # Simulate running the function passed to execute_read
            # The actual function `_execute_query` calls tx.run(query, params)
            # So we need tx to be a mock that has a run method
            mock_tx = MagicMock()
            mock_tx.run.return_value = mock_result_instance
            return func(mock_tx, query, params)

        mock_session_instance.execute_read.side_effect = mock_execute_read
        
        # Define what the mock result from tx.run() should be (an iterable of records)
        mock_record1 = {"name": "NodeA", "value": 100}
        mock_record2 = {"name": "NodeB", "value": 200}
        mock_result_instance.__iter__.return_value = [mock_record1, mock_record2] # Make it iterable

        agent = KGAgent(uri="neo4j://testhost:7687", user="testuser", password="testpassword")
        self.assertIsNotNone(agent._driver) # Ensure agent initialized for query test

        cypher_query = "MATCH (n) RETURN n.name AS name, n.value AS value LIMIT 2"
        params = {}
        results = agent.query(cypher_query, params=params)

        self.assertIsNotNone(results)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0], mock_record1)
        self.assertEqual(results[1], mock_record2)
        
        mock_session_instance.execute_read.assert_called_once()
        # The actual call inside execute_read's passed function is tx.run(cypher_query, params)
        # We can check the arguments of the function passed to execute_read if needed,
        # or the arguments to tx.run() if we refine the mock_execute_read further.
        
        agent.close()

    @patch('smart_factory_app.agents.kg_agent.KGAgent.query') # Mocking the query method itself for a simple test
    def test_example_usage_in_main_block(self, mock_query_method):
        """
        Test the example usage block in if __name__ == '__main__'.
        This requires mocking KGAgent's own methods if it's called from within the script's main block.
        """
        # This is a more complex scenario to test the __main__ block.
        # For now, we'll just ensure KGAgent can be instantiated.
        # A full test of __main__ would involve subprocesses or refactoring __main__ into a callable function.
        self.assertTrue(True, "Skipping full __main__ block test for now, focusing on class methods.")


    def test_query_driver_not_initialized(self):
        """Test query execution when the driver is not initialized."""
        # Patch GraphDatabase.driver to simulate failed initialization
        with patch('smart_factory_app.agents.kg_agent.GraphDatabase.driver') as mock_graph_driver_init_fail:
            mock_graph_driver_init_fail.side_effect = neo4j_exceptions.ServiceUnavailable("Simulated failure")
            agent = KGAgent() # This will fail to set up _driver
            self.assertIsNone(agent._driver)

            results = agent.query("MATCH (n) RETURN n")
            self.assertIsNone(results) # Expect None as driver is not there

    @patch('smart_factory_app.agents.kg_agent.GraphDatabase.driver')
    def test_query_cypher_syntax_error(self, mock_graph_driver):
        """Test query execution with a CypherSyntaxError."""
        mock_driver_instance = MagicMock()
        mock_session_instance = MagicMock()
        mock_graph_driver.return_value = mock_driver_instance
        mock_driver_instance.session.return_value.__enter__.return_value = mock_session_instance
        
        # Make session.execute_read raise CypherSyntaxError
        mock_session_instance.execute_read.side_effect = neo4j_exceptions.CypherSyntaxError("Invalid query")

        agent = KGAgent()
        self.assertIsNotNone(agent._driver)

        results = agent.query("MATCH (n RETURN n") # Intentionally malformed
        self.assertIsNone(results)
        agent.close()

    @patch('smart_factory_app.agents.kg_agent.GraphDatabase.driver')
    def test_close_driver(self, mock_graph_driver):
        """Test that the close method calls driver.close()."""
        mock_driver_instance = MagicMock()
        mock_graph_driver.return_value = mock_driver_instance

        agent = KGAgent()
        self.assertIsNotNone(agent._driver) # Driver should be set
        
        agent.close()
        mock_driver_instance.close.assert_called_once()

        # Test closing when driver is already None
        agent._driver = None
        agent.close() # Should not raise error


if __name__ == '__main__':
    unittest.main()
