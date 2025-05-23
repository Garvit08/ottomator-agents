import os
import sys
from neo4j import GraphDatabase, exceptions

# Path adjustments for config import
current_dir_kg_agent = os.path.dirname(os.path.abspath(__file__))
project_root_kg_agent = os.path.abspath(os.path.join(current_dir_kg_agent, '..', '..'))
if project_root_kg_agent not in sys.path:
    # Add parent of smart_factory_app to path for `from smart_factory_app.config...`
    sys.path.insert(0, os.path.dirname(project_root_kg_agent))

try:
    from smart_factory_app.config.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
except ImportError:
    print("Error importing config for KGAgent. Using fallback environment variables.")
    NEO4J_URI = os.getenv("NEO4J_URI", "neo4j://localhost:7687")
    NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
    NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")


class KGAgent:
    def __init__(self, uri: str = NEO4J_URI, user: str = NEO4J_USER, password: str = NEO4J_PASSWORD):
        """
        Initializes the KG Agent and establishes a connection to Neo4j using configuration.
        """
        self.uri = uri
        self.user = user
        self.password = password # Storing for clarity, though driver uses it directly
        self._driver = None
        
        if not self.uri or not self.user: # Password can sometimes be optional depending on Neo4j setup
            print("Neo4j URI or User not provided. KGAgent cannot be initialized.")
            return

        try:
            self._driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
            self._driver.verify_connectivity()
            print(f"Successfully connected to Neo4j at {self.uri} with user {self.user}.")
        except exceptions.AuthError as e:
            print(f"Neo4j authentication failed for user '{self.user}' at {self.uri}: {e}")
            self._driver = None
        except exceptions.ServiceUnavailable as e:
            print(f"Neo4j service unavailable at {self.uri}: {e}")
            self._driver = None
        except Exception as e:
            print(f"An unexpected error occurred during Neo4j connection to {self.uri}: {e}")
            self._driver = None

    def close(self):
        """
        Closes the Neo4j driver connection.
        """
        if self._driver is not None:
            try:
                self._driver.close()
                print("Neo4j connection closed.")
            except Exception as e:
                print(f"Error closing Neo4j connection: {e}")

    def query(self, cypher_query, params=None):
        """
        Executes a Cypher query against the Neo4j database.

        :param cypher_query: The Cypher query string.
        :param params: A dictionary of parameters for the query.
        :return: A list of records, or None if an error occurs.
        """
        if self._driver is None:
            print("Neo4j driver not initialized. Cannot execute query.")
            return None

        records_list = []
        summary = None
        
        # Using try-with-resources for session management
        try:
            with self._driver.session() as session:
                # Using execute_read for read-only queries. 
                # For write queries, use session.execute_write.
                # For simplicity in this example, we'll use a generic approach
                # that works for read, but for specific read/write, use appropriate transaction.
                
                # A more generic way if you don't know if it's read/write,
                # but it's better to use specific transaction functions.
                # For read-only queries, session.read_transaction is preferred.
                def _execute_query(tx, cypher_query, params):
                    result = tx.run(cypher_query, params)
                    # Consume results before transaction closes if necessary
                    # Or process them directly. Here we convert to a list of records.
                    return [record for record in result]

                records_list = session.execute_read(_execute_query, cypher_query, params)
                # To get summary information (e.g., query type, counters)
                # summary = result.summary() # This would need `result` from `tx.run`
                # For now, we'll just return the records.

        except exceptions.CypherSyntaxError as e:
            print(f"Cypher syntax error: {e}")
            return None
        except exceptions.TransientError as e:
            # Errors like database unavailable, leader switch, etc.
            # These might be worth retrying.
            print(f"Neo4j transient error (retry may be appropriate): {e}")
            return None
        except Exception as e:
            print(f"An error occurred while executing query: {e}")
            return None
        
        return records_list

# Example Usage
if __name__ == "__main__":
    # Path adjustments for config are at the top.
    # KGAgent now uses default arguments from imported config.
    print("Attempting to initialize KG Agent using configuration...")
    kg_agent = KGAgent() # Uses NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD from config by default

    if kg_agent._driver: # Check if driver was successfully initialized
        print(f"\nKG Agent initialized with URI: {kg_agent.uri}, User: {kg_agent.user}.")
        
        # Example Cypher query
        # This query attempts to match any node and return it, limiting to 1.
        # It's a good basic test to see if querying works.
        sample_query = "MATCH (n) RETURN n LIMIT 1"
        print(f"Executing sample query: {sample_query}")
        
        results = kg_agent.query(sample_query)

        if results is not None:
            if results:
                print("\nQuery Results:")
                for record in results:
                    print(record)
            else:
                print("\nQuery executed successfully, but returned no results (database might be empty or query matched nothing).")
        else:
            print("\nQuery execution failed.")

        # Close the connection
        kg_agent.close()
    else:
        print("\nKG Agent initialization failed. Check Neo4j connection details and server status.")
