import unittest
import sys
import os
from unittest.mock import patch, MagicMock, ANY

# --- Path Adjustments ---
current_test_dir = os.path.dirname(os.path.abspath(__file__))
smart_factory_app_dir = os.path.abspath(os.path.join(current_test_dir, '..'))
project_root = os.path.abspath(os.path.join(smart_factory_app_dir, '..'))

if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Import the module to be tested
from smart_factory_app.agents.vector_agent import VectorAgent
# Import config to verify defaults or override for testing
from smart_factory_app.config import config 

class TestVectorAgent(unittest.TestCase):

    @patch('smart_factory_app.agents.vector_agent.SentenceTransformer')
    @patch('smart_factory_app.agents.vector_agent.chromadb.Client') # Mock in-memory client
    @patch('smart_factory_app.agents.vector_agent.chromadb.PersistentClient') # Mock persistent client
    def test_initialization_in_memory(self, mock_persistent_client, mock_in_memory_client, mock_sentence_transformer):
        """Test VectorAgent initialization for in-memory ChromaDB."""
        mock_model_instance = MagicMock()
        mock_sentence_transformer.return_value = mock_model_instance
        
        mock_chroma_client_instance = MagicMock()
        mock_collection_instance = MagicMock()
        mock_in_memory_client.return_value = mock_chroma_client_instance
        mock_chroma_client_instance.get_or_create_collection.return_value = mock_collection_instance

        # Explicitly pass None for chroma_path for in-memory
        agent = VectorAgent(model_name="test-model", chroma_path=None, collection_name="test_collection")

        mock_sentence_transformer.assert_called_once_with("test-model")
        self.assertEqual(agent.model, mock_model_instance)
        
        mock_in_memory_client.assert_called_once() # In-memory client should be called
        mock_persistent_client.assert_not_called() # Persistent client should not be called
        self.assertEqual(agent.client, mock_chroma_client_instance)
        
        mock_chroma_client_instance.get_or_create_collection.assert_called_once_with(name="test_collection")
        self.assertEqual(agent.collection, mock_collection_instance)

    @patch('smart_factory_app.agents.vector_agent.SentenceTransformer')
    @patch('smart_factory_app.agents.vector_agent.chromadb.PersistentClient') # Mock persistent client
    @patch('smart_factory_app.agents.vector_agent.chromadb.Client') # Mock in-memory client
    def test_initialization_persistent(self, mock_in_memory_client, mock_persistent_client, mock_sentence_transformer):
        """Test VectorAgent initialization for persistent ChromaDB."""
        mock_model_instance = MagicMock()
        mock_sentence_transformer.return_value = mock_model_instance
        
        mock_chroma_client_instance = MagicMock()
        mock_collection_instance = MagicMock()
        mock_persistent_client.return_value = mock_chroma_client_instance
        mock_chroma_client_instance.get_or_create_collection.return_value = mock_collection_instance

        agent = VectorAgent(model_name="test-model", chroma_path="./test_chroma_path", collection_name="test_collection_persist")

        mock_sentence_transformer.assert_called_once_with("test-model")
        self.assertEqual(agent.model, mock_model_instance)
        
        mock_persistent_client.assert_called_once_with(path="./test_chroma_path")
        mock_in_memory_client.assert_not_called()
        self.assertEqual(agent.client, mock_chroma_client_instance)
        
        mock_chroma_client_instance.get_or_create_collection.assert_called_once_with(name="test_collection_persist")
        self.assertEqual(agent.collection, mock_collection_instance)

    @patch('smart_factory_app.agents.vector_agent.VectorAgent._init_chromadb') # Mock internal helper if it exists
    @patch('smart_factory_app.agents.vector_agent.SentenceTransformer')
    def test_add_texts(self, mock_sentence_transformer, mock_init_chromadb):
        """Test the add_texts method."""
        # Setup VectorAgent instance with mocked model and collection
        agent = VectorAgent() # Uses default config values which should be fine for this test
        agent.model = mock_sentence_transformer.return_value # Assign mocked model
        agent.collection = MagicMock() # Assign mocked collection

        sample_texts = ["doc1 text", "doc2 text"]
        sample_embeddings = [[0.1, 0.2], [0.3, 0.4]]
        sample_metadatas = [{"source": "doc1"}, {"source": "doc2"}]
        sample_ids = ["id1", "id2"]

        agent.model.encode.return_value.tolist.return_value = sample_embeddings

        agent.add_texts(texts=sample_texts, metadatas=sample_metadatas, ids=sample_ids)

        agent.model.encode.assert_called_once_with(sample_texts)
        agent.collection.add.assert_called_once_with(
            embeddings=sample_embeddings,
            documents=sample_texts,
            metadatas=sample_metadatas,
            ids=sample_ids
        )
        
    @patch('uuid.uuid4')
    @patch('smart_factory_app.agents.vector_agent.VectorAgent._init_chromadb') # Mock internal helper if it exists
    @patch('smart_factory_app.agents.vector_agent.SentenceTransformer')
    def test_add_texts_generate_ids(self, mock_sentence_transformer, mock_init_chromadb, mock_uuid):
        """Test add_texts when IDs are not provided and should be generated."""
        agent = VectorAgent()
        agent.model = mock_sentence_transformer.return_value
        agent.collection = MagicMock()

        mock_uuid.side_effect = [MagicMock(hex='testid1'), MagicMock(hex='testid2')] # Mock uuid.uuid4().hex if that's used, or just str()
        
        sample_texts = ["text A", "text B"]
        expected_ids = [str(MagicMock(hex='testid1')), str(MagicMock(hex='testid2'))] # Match how VectorAgent creates string IDs from UUIDs.
                                                                                      # If it's just str(uuid.uuid4()), then mock str(uuid.uuid4())
        # Adjusting if VectorAgent directly uses str(uuid.uuid4())
        mock_uuid.side_effect = [MagicMock(name="uuid1"), MagicMock(name="uuid2")]
        # If str(uuid.uuid4()) is called:
        # Need to mock str() for specific uuid objects, or ensure uuid.uuid4() returns objects whose str() is predictable
        # A simpler way: have uuid.uuid4 return predictable string-like objects if str() is the final step.
        # For this test, let's assume VectorAgent does str(uuid.uuid4())
        mock_uuid.side_effect = ["testid1_str", "testid2_str"] # If str() is not explicitly called on a uuid object in agent.
                                                               # The code is `ids = [str(uuid.uuid4()) for _ in texts]`
                                                               # So, uuid.uuid4() should return objects, and str() is called on them.
        # Let's re-mock uuid.uuid4 to return objects that have a predictable str() representation
        uuid_obj1 = MagicMock(); uuid_obj1.__str__ = MagicMock(return_value="testid1_from_str")
        uuid_obj2 = MagicMock(); uuid_obj2.__str__ = MagicMock(return_value="testid2_from_str")
        mock_uuid.side_effect = [uuid_obj1, uuid_obj2]
        expected_ids_generated = ["testid1_from_str", "testid2_from_str"]


        agent.add_texts(texts=sample_texts) # No IDs or metadatas

        agent.collection.add.assert_called_once()
        call_args = agent.collection.add.call_args[1] # Get kwargs
        self.assertEqual(call_args['ids'], expected_ids_generated)
        self.assertEqual(len(call_args['metadatas']), len(sample_texts)) # Should create empty metadatas


    @patch('smart_factory_app.agents.vector_agent.VectorAgent._init_chromadb')
    @patch('smart_factory_app.agents.vector_agent.SentenceTransformer')
    def test_semantic_search(self, mock_sentence_transformer, mock_init_chromadb):
        """Test the semantic_search method."""
        agent = VectorAgent()
        agent.model = mock_sentence_transformer.return_value
        agent.collection = MagicMock()

        query_text = "find similar documents"
        query_embedding = [0.5, 0.5, 0.5]
        search_results = {"documents": [["result doc1"]], "metadatas": [[{"src": "s1"}]], "distances": [[0.2]]}

        agent.model.encode.return_value.tolist.return_value = query_embedding
        agent.collection.query.return_value = search_results

        results = agent.semantic_search(query_text=query_text, n_results=1, where_filter={"type": "test"})

        agent.model.encode.assert_called_once_with(query_text)
        agent.collection.query.assert_called_once_with(
            query_embeddings=[query_embedding],
            n_results=1,
            include=['metadatas', 'documents', 'distances'],
            where={"type": "test"}
        )
        self.assertEqual(results, search_results)

    @patch('smart_factory_app.agents.vector_agent.VectorAgent._init_chromadb')
    @patch('smart_factory_app.agents.vector_agent.SentenceTransformer')
    def test_keyword_search(self, mock_sentence_transformer, mock_init_chromadb):
        """Test the keyword_search method using where_document."""
        agent = VectorAgent()
        # No model needed for pure keyword search as implemented
        agent.collection = MagicMock()

        keywords = ["error", "CNC"]
        # Expected filter for ChromaDB based on current VectorAgent implementation:
        # {"$or": [{"$contains": "error"}, {"$contains": "CNC"}]}
        expected_where_document_filter = {"$or": [{"$contains": "error"}, {"$contains": "CNC"}]}
        
        mock_get_results = {
            "ids": ["id1", "id2"], 
            "documents": ["CNC error log", "Error report for CNC machine"],
            "metadatas": [{"source": "log1"}, {"source": "report2"}]
            # No distances in 'get'
        }
        # Expected formatted output (wrapped in lists, placeholder distances)
        expected_formatted_results = {
            "ids": [["id1", "id2"]],
            "documents": [["CNC error log", "Error report for CNC machine"]],
            "metadatas": [[{"source": "log1"}, {"source": "report2"}]],
            "distances": [[0.0, 0.0]] 
        }

        agent.collection.get.return_value = mock_get_results

        results = agent.keyword_search(keywords=keywords, n_results=2)
        
        agent.collection.get.assert_called_once_with(
            where_document=expected_where_document_filter,
            n_results=2,
            include=['metadatas', 'documents']
        )
        self.assertEqual(results, expected_formatted_results)


    @patch('smart_factory_app.agents.vector_agent.VectorAgent.semantic_search')
    @patch('smart_factory_app.agents.vector_agent.VectorAgent.keyword_search')
    def test_hybrid_search(self, mock_keyword_search, mock_semantic_search):
        """Test the hybrid_search method, focusing on combination logic."""
        agent = VectorAgent() # Initialization mocks are not strictly needed if sub-methods are mocked

        mock_semantic_results = {
            "ids": [["sem_id1", "shared_id2"]],
            "documents": [["semantic doc1", "shared document two"]],
            "metadatas": [[{"src": "sem1"}, {"src": "shared"}]],
            "distances": [[0.1, 0.2]] # Lower distance = better
        }
        mock_keyword_results = { # Keyword search mock already returns formatted
            "ids": [["key_id3", "shared_id2"]],
            "documents": [["keyword doc3", "shared document two"]],
            "metadatas": [[{"src": "key3"}, {"src": "shared"}]],
            "distances": [[0.0, 0.0]] # Placeholder distances
        }

        mock_semantic_search.return_value = mock_semantic_results
        mock_keyword_search.return_value = mock_keyword_results

        query_text = "find shared document"
        keywords = ["shared"]
        
        # Semantic scores: (1 - 0.1) = 0.9 for sem_id1; (1 - 0.2) = 0.8 for shared_id2
        # Keyword scores: 1.0 for key_id3; 1.0 for shared_id2
        # Weights: semantic=0.6, keyword=0.4 (default)
        # Combined scores:
        # sem_id1: (0.9 * 0.6) + (0.0 * 0.4) = 0.54
        # shared_id2: (0.8 * 0.6) + (1.0 * 0.4) = 0.48 + 0.4 = 0.88
        # key_id3: (0.0 * 0.6) + (1.0 * 0.4) = 0.4
        # Expected order: shared_id2, sem_id1, key_id3

        results = agent.hybrid_search(query_text=query_text, keywords=keywords, n_results=3)

        mock_semantic_search.assert_called_once_with(query_text, n_results=3) # n_results from hybrid_search
        mock_keyword_search.assert_called_once_with(keywords, n_results=3)

        self.assertIn("ids", results)
        self.assertIn("documents", results)
        self.assertIn("metadatas", results)
        self.assertIn("scores", results) # Hybrid search returns 'scores'
        
        self.assertEqual(len(results["ids"][0]), 3)
        self.assertEqual(results["ids"][0][0], "shared_id2") # Highest score
        self.assertEqual(results["ids"][0][1], "sem_id1")
        self.assertEqual(results["ids"][0][2], "key_id3")

        self.assertAlmostEqual(results["scores"][0][0], 0.88)
        self.assertAlmostEqual(results["scores"][0][1], 0.54)
        self.assertAlmostEqual(results["scores"][0][2], 0.40)


if __name__ == '__main__':
    unittest.main()
