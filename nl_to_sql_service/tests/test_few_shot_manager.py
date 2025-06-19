# nl_to_sql_service/tests/test_few_shot_manager.py
import unittest
import json
import os
import shutil # For cleaning up directories
import logging
from typing import Dict, List, Any
from unittest.mock import patch, MagicMock

# Adjust path to import from the nl_to_sql_service package
# This assumes tests are run from the project root (e.g. parent of nl_to_sql_service)
# or that nl_to_sql_service is in PYTHONPATH.
# For direct script run:
import sys
PACKAGE_PARENT = os.path.join(os.path.dirname(__file__), '..', '..') # Gets to the parent of nl_to_sql_service dir
sys.path.insert(0, os.path.normpath(PACKAGE_PARENT))

from nl_to_sql_service.few_shot_manager import FewShotManager

# Mock SentenceTransformer and cos_sim before FewShotManager is imported by the test runner
# This is a common way to ensure mocks are in place early.
# However, if FewShotManager itself does a try-except for these, we might need to patch
# where it's used or ensure the module-level SENTENCE_TRANSFORMERS_AVAILABLE is False.

# For testing, we can explicitly set SENTENCE_TRANSFORMERS_AVAILABLE to True
# and then mock the SentenceTransformer class and cos_sim function.
MOCK_SENTENCE_TRANSFORMERS_AVAILABLE = True

mock_sentence_transformer_module = MagicMock()
mock_sentence_transformer_instance = MagicMock()

def mock_st_encode(text_or_texts: Any) -> Any:
    # Simple mock: return a fixed-size list of numbers based on input length or a hash
    # This needs to return a numpy-like array or something that .tolist() can be called on.
    if isinstance(text_or_texts, str):
        return MagicMock(tolist=lambda: [float(len(text_or_texts) % 10) / 10.0] * 3) # Dummy 3-dim embedding
    # Handle list of texts if your _preprocess_examples_for_embeddings uses batching
    return [MagicMock(tolist=lambda: [float(len(text) % 10) / 10.0] * 3) for text in text_or_texts]


mock_sentence_transformer_instance.encode = mock_st_encode
mock_sentence_transformer_module.SentenceTransformer.return_value = mock_sentence_transformer_instance

def mock_cos_sim(arr1: Any, arr2: Any) -> Any:
    # Mock cosine similarity. arr1 is query, arr2 is list of example embeddings.
    # Return a tensor-like object that can be indexed [0][0] and has .item()
    # For simplicity, if embeddings are identical, return 1.0, else 0.5 or some other value.
    # This mock needs to be robust based on how it's called.
    # cos_sim in sentence_transformers.util.cos_sim(a, b) returns a tensor of shape (len(a), len(b))

    # Assuming arr1 is single query embedding (e.g. list of floats)
    # Assuming arr2 is a list of example embeddings (e.g. list of list of floats)
    results = []
    for ex_emb in arr2:
        if list(arr1) == list(ex_emb): # Simple equality check for mock
            results.append(1.0)
        elif sum(arr1) > sum(ex_emb): # Arbitrary logic for different similarities
             results.append(0.7)
        else:
            results.append(0.3)

    # The real cos_sim returns a tensor, e.g., tensor([[0.7000, 1.0000]])
    # We need to mock this structure.
    mock_tensor = MagicMock()
    mock_tensor.__getitem__.return_value = MagicMock(__getitem__=MagicMock(side_effect=lambda i: MagicMock(item=lambda: results[i])))
    return mock_tensor


class TestFewShotManager(unittest.TestCase):
    """
    Unit tests for the FewShotManager class.
    """
    test_dir = "temp_test_examples_dir"
    valid_examples_file = os.path.join(test_dir, "valid_examples.json")
    malformed_examples_file = os.path.join(test_dir, "malformed_examples.json")
    empty_examples_file = os.path.join(test_dir, "empty_examples.json")

    sample_examples_data = [
        {"id": "ex1", "nl_query": "What is total sales for product X?", "sql_query": "SELECT SUM(sales) FROM orders WHERE product_name = 'X';", "description": "Total sales for X", "keywords": ["sales", "product X"], "intent": "get_sales"},
        {"id": "ex2", "nl_query": "Show active users in engineering department", "sql_query": "SELECT name FROM users WHERE status = 'active' AND department = 'engineering';", "description": "Active users in engineering", "keywords": ["users", "active", "engineering", "department"], "intent": "get_users"},
        {"id": "ex3", "nl_query": "How many issues were created yesterday for project Alpha?", "sql_query": "SELECT COUNT(*) FROM issues WHERE project = 'Alpha' AND creation_date = CURRENT_DATE - 1;", "description": "Issues yesterday for Alpha", "keywords": ["issues", "yesterday", "project Alpha"], "intent": "count_issues"},
        {"id": "ex4", "nl_query": "List all tasks due this week for sales team.", "sql_query": "SELECT task_name FROM tasks WHERE due_date >= date_trunc('week', CURRENT_DATE) AND due_date < date_trunc('week', CURRENT_DATE + interval '1 week') AND team = 'sales';", "description": "Tasks due this week for sales", "keywords": ["tasks", "due", "week", "sales"], "intent": "get_tasks"}
    ]

    @classmethod
    def setUpClass(cls):
        os.makedirs(cls.test_dir, exist_ok=True)
        with open(cls.valid_examples_file, 'w') as f:
            json.dump(cls.sample_examples_data, f)
        with open(cls.malformed_examples_file, 'w') as f:
            f.write("[{'id': 'bad',") # Invalid JSON
        with open(cls.empty_examples_file, 'w') as f:
            json.dump([], f) # Valid JSON, but empty list

        # Configure logger for tests to see output
        logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.test_dir):
            shutil.rmtree(cls.test_dir)

    def setUp(self):
        self.logger = logging.getLogger(__name__)
        # This basic manager is used for tests not involving semantic features directly,
        # or when semantic features are mocked at a higher level.
        self.manager_no_embed = FewShotManager(
            examples_filepath=self.valid_examples_file,
            embedding_model_name=None, # No embedding model
            logger=self.logger
        )
        # Manager for semantic tests (will be patched)
        # Patching at module level for sentence_transformers
        self.patcher_st_available = patch('nl_to_sql_service.few_shot_manager.SENTENCE_TRANSFORMERS_AVAILABLE', MOCK_SENTENCE_TRANSFORMERS_AVAILABLE)
        self.patcher_st_class = patch('nl_to_sql_service.few_shot_manager.SentenceTransformer', mock_sentence_transformer_module.SentenceTransformer)
        self.patcher_cos_sim = patch('nl_to_sql_service.few_shot_manager.cos_sim', mock_cos_sim)

        self.MockSTAvailable = self.patcher_st_available.start()
        self.MockSTClass = self.patcher_st_class.start()
        self.MockCosSim = self.patcher_cos_sim.start()


    def tearDown(self):
        self.patcher_st_available.stop()
        self.patcher_st_class.stop()
        self.patcher_cos_sim.stop()


    def test_load_valid_examples(self):
        self.assertEqual(len(self.manager_no_embed.examples), len(self.sample_examples_data))
        self.assertEqual(self.manager_no_embed.examples[0]['id'], 'ex1')

    def test_load_non_existent_file(self):
        manager = FewShotManager("non_existent.json", logger=self.logger)
        self.assertEqual(len(manager.examples), 0)

    def test_load_malformed_json(self):
        manager = FewShotManager(self.malformed_examples_file, logger=self.logger)
        self.assertEqual(len(manager.examples), 0)

    def test_load_empty_json(self):
        manager = FewShotManager(self.empty_examples_file, logger=self.logger)
        self.assertEqual(len(manager.examples), 0)

    def test_extract_keywords(self):
        text = "Show me the total sales and active users for product X in the engineering department."
        expected_keywords = ["total", "sales", "active", "users", "product", "engineering"] # "x" removed as len > 1
        # Order doesn't matter for set comparison
        self.assertCountEqual(self.manager_no_embed._extract_keywords(text), expected_keywords)
        self.assertEqual(self.manager_no_embed._extract_keywords(""), [])

    def test_get_relevant_examples_random(self):
        selected = self.manager_no_embed.get_relevant_examples("any query", n_examples=2, selection_strategy="random")
        self.assertEqual(len(selected), 2)
        for item in selected:
            self.assertIn(item, self.sample_examples_data)

    def test_get_relevant_examples_n_too_large_random(self):
        selected = self.manager_no_embed.get_relevant_examples("any query", n_examples=10, selection_strategy="random")
        self.assertEqual(len(selected), len(self.sample_examples_data))

    def test_get_relevant_examples_n_zero_random(self):
        selected = self.manager_no_embed.get_relevant_examples("any query", n_examples=0, selection_strategy="random")
        self.assertEqual(len(selected), 0)

    def test_get_relevant_examples_keyword(self):
        nl_query = "active engineering users"
        selected = self.manager_no_embed.get_relevant_examples(nl_query, n_examples=1, selection_strategy="keyword")
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]['id'], 'ex2') # 'ex2' has "active", "users", "engineering"

        nl_query_sales = "total sales"
        selected_sales = self.manager_no_embed.get_relevant_examples(nl_query_sales, n_examples=1, selection_strategy="keyword")
        self.assertEqual(len(selected_sales), 1)
        self.assertEqual(selected_sales[0]['id'], 'ex1') # 'ex1' has "sales"

    def test_get_relevant_examples_keyword_no_match(self):
        nl_query = "completely unrelated query"
        selected = self.manager_no_embed.get_relevant_examples(nl_query, n_examples=2, selection_strategy="keyword")
        # Falls back to random if no keywords extracted or no matches
        self.assertEqual(len(selected), 2) # Should fallback to random of num_to_sample

    def test_format_examples_for_prompt(self):
        examples_to_format = [self.sample_examples_data[0], self.sample_examples_data[1]]
        formatted_string = self.manager_no_embed.format_examples_for_prompt(examples_to_format)

        self.assertIn("Example 1:", formatted_string)
        self.assertIn("User Question: What is total sales for product X?", formatted_string)
        self.assertIn("SQL Query: SELECT SUM(sales) FROM orders WHERE product_name = 'X';", formatted_string)
        self.assertIn("Description: Total sales for X", formatted_string)
        self.assertIn("---", formatted_string)
        self.assertIn("Example 2:", formatted_string)
        self.assertIn("User Question: Show me active users in engineering department", formatted_string)
        self.assertIn("\n\n", formatted_string) # Check for double newline separation

    def test_format_empty_examples(self):
        self.assertEqual(self.manager_no_embed.format_examples_for_prompt([]), "")

    def test_format_examples_missing_keys(self):
        # Example missing sql_query
        examples_missing_keys = [{"id": "bad_ex", "nl_query": "A question"}]
        formatted = self.manager_no_embed.format_examples_for_prompt(examples_missing_keys)
        self.assertEqual(formatted, "") # Should skip this example

    def test_semantic_selection_mocked(self):
        # This test uses the globally patched SentenceTransformer and cos_sim

        # Create a manager instance that *thinks* it has an embedding model
        # The class-level patches should ensure that the mock is used.
        manager_semantic = FewShotManager(
            examples_filepath=self.valid_examples_file,
            embedding_model_name="mocked-model", # Name implies it should try to load
            logger=self.logger
        )
        self.assertTrue(manager_semantic.embedding_model is not None) # Check if mock was loaded via patch

        # The mock_st_encode returns embedding based on length of text
        # Example nl_queries:
        # ex1: "What is total sales for product X?" (len 34) -> emb [0.4, 0.4, 0.4]
        # ex2: "Show me active users in engineering department" (len 46) -> emb [0.6, 0.6, 0.6]
        # ex3: "How many issues were created yesterday for project Alpha?" (len 58) -> emb [0.8, 0.8, 0.8]
        # ex4: "List all tasks due this week for sales team." (len 46) -> emb [0.6, 0.6, 0.6] (Same as ex2)

        # Query that should be identical to ex2's nl_query for perfect match
        test_query_semantic = "Show me active users in engineering department" # len 46 -> emb [0.6,0.6,0.6]

        # _preprocess_examples_for_embeddings should have been called in __init__
        # and used the mocked encode
        self.assertIsNotNone(manager_semantic.examples[0].get("embedding"))

        selected_semantic = manager_semantic.get_relevant_examples(
            test_query_semantic, n_examples=2, selection_strategy="semantic"
        )
        self.assertEqual(len(selected_semantic), 2)
        # Based on mock_cos_sim, ex2 and ex4 should be most similar (score 1.0)
        # then ex3 (score 0.7 if sum logic applies as sum([.6,.6,.6]) vs sum([.8,.8,.8]))
        # then ex1 (score 0.3 if sum logic applies as sum([.6,.6,.6]) vs sum([.4,.4,.4]))
        # So, expected order of IDs: ex2, ex4 (or ex4, ex2), then others.
        selected_ids = [ex['id'] for ex in selected_semantic]
        self.assertIn('ex2', selected_ids)
        self.assertIn('ex4', selected_ids)


    def test_hybrid_selection_mocked(self):
        manager_hybrid = FewShotManager(
            examples_filepath=self.valid_examples_file,
            embedding_model_name="mocked-model-hybrid",
            logger=self.logger
        )
        self.assertTrue(manager_hybrid.embedding_model is not None)

        # Query that has good keyword match with ex2/ex4 and semantic match with ex2/ex4
        test_query_hybrid = "Show active users in engineering department and sales tasks"
        # Keywords: "active", "users", "engineering", "department", "sales", "tasks"
        # Semantic embedding (len 61) -> [0.1, 0.1, 0.1]
        # Expected keyword top: ex2, ex4
        # Expected semantic top (based on mock): ex1 (len 34, [0.4,0.4,0.4]) might be closer to [0.1,0.1,0.1] than ex2/4 ([0.6,...])
        # This depends on the mock_cos_sim logic's interpretation.
        # Let's adjust mock_cos_sim to be more predictable for hybrid:
        # If query is "Show active users in engineering department and sales tasks"
        # Mock encode for this query to be identical to ex1's embedding

        # Re-patch encode for this specific test if needed, or design global mock carefully
        original_side_effect = self.MockSTClass.return_value.encode.side_effect

        # Define specific embeddings for this test case
        # query_emb_hybrid = [0.4, 0.4, 0.4] # Matches ex1
        # ex1_emb = [0.4,0.4,0.4]
        # ex2_emb = [0.6,0.6,0.6]
        # ex3_emb = [0.8,0.8,0.8]
        # ex4_emb = [0.6,0.6,0.6]

        # self.MockSTClass.return_value.encode.side_effect = lambda text: {
        #     test_query_hybrid: query_emb_hybrid,
        #     self.sample_examples_data[0]['nl_query']: ex1_emb,
        #     self.sample_examples_data[1]['nl_query']: ex2_emb,
        #     self.sample_examples_data[2]['nl_query']: ex3_emb,
        #     self.sample_examples_data[3]['nl_query']: ex4_emb,
        # }.get(text, [0.0]*3) # Default for other texts

        # The above lambda side_effect for encode is tricky because preprocess_examples runs in init.
        # For simplicity, we'll rely on the global mock and check the combination logic.
        # Keyword will pick ex2, ex4. Semantic (if query is "Show active users...") will pick ex2, ex4.
        # So hybrid should definitely include ex2 and ex4.

        selected_hybrid = manager_hybrid.get_relevant_examples(
            test_query_hybrid, n_examples=2, selection_strategy="hybrid"
        )
        selected_ids = [ex['id'] for ex in selected_hybrid]
        self.assertEqual(len(selected_ids), 2) # Should be 2 unique examples
        self.assertIn('ex2', selected_ids) # Strong keyword and semantic match
        self.assertIn('ex4', selected_ids) # Strong keyword and semantic match

        # Restore original side_effect if changed locally, though class-level patch handles it.
        # self.MockSTClass.return_value.encode.side_effect = original_side_effect


if __name__ == '__main__':
    unittest.main()
