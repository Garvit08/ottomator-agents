# nl_to_sql_service/few_shot_manager.py
"""Manages few-shot examples for NL-to-SQL conversion.

This module provides the FewShotManager class, responsible for loading,
selecting (using various strategies like random, keyword, semantic, hybrid),
and formatting few-shot examples to be included in prompts for the LLM.
It can leverage sentence transformer models for semantic selection if available.
"""
import json
import random
from typing import Dict, List, Optional, Any, Set
import os
import logging
import re

# Attempt to import SentenceTransformer and its utilities
try:
    from sentence_transformers import SentenceTransformer
    from sentence_transformers.util import cos_sim
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SentenceTransformer = None
    cos_sim = None
    SENTENCE_TRANSFORMERS_AVAILABLE = False

# Basic list of common English stop words for keyword extraction
DEFAULT_STOP_WORDS: Set[str] = set([
    "i", "me", "my", "myself", "we", "our", "ours", "ourselves", "you", "your", "yours",
    "yourself", "yourselves", "he", "him", "his", "himself", "she", "her", "hers",
    "herself", "it", "its", "itself", "they", "them", "their", "theirs", "themselves",
    "what", "which", "who", "whom", "this", "that", "these", "those", "am", "is", "are",
    "was", "were", "be", "been", "being", "have", "has", "had", "having", "do", "does",
    "did", "doing", "a", "an", "the", "and", "but", "if", "or", "because", "as", "until",
    "while", "of", "at", "by", "for", "with", "about", "against", "between", "into",
    "through", "during", "before", "after", "above", "below", "to", "from", "up", "down",
    "in", "out", "on", "off", "over", "under", "again", "further", "then", "once", "here",
    "there", "when", "where", "why", "how", "all", "any", "both", "each", "few", "more",
    "most", "other", "some", "such", "no", "nor", "not", "only", "own", "same", "so",
    "than", "too", "very", "s", "t", "can", "will", "just", "don", "should", "now",
    "show", "me", "list", "get", "find", "tell", "give", "provide", "calculate", "what's",
    "select", "from", "where", "group", "order", "by", "limit", "count", "average", "sum",
    "min", "max", "table", "column", "database", "query", "sql"
])


class FewShotManager:
    """Handles loading, selection, and formatting of few-shot examples.

    This class is responsible for managing a collection of few-shot examples
    used to guide an LLM in translating natural language to SQL. It supports
    loading examples from a JSON file and can select relevant examples using
    various strategies, including random, keyword-based, semantic similarity,
    and a hybrid approach. Semantic capabilities depend on the availability of
    the `sentence-transformers` library and a suitable embedding model.

    Attributes:
        examples_filepath (str): Path to the JSON file containing examples.
        embedding_model_name (Optional[str]): Name of the sentence transformer model.
        logger (logging.Logger): Logger instance for messages.
        embedding_model (Optional[SentenceTransformer]): Loaded sentence transformer model instance.
        examples (List[Dict[str, Any]]): List of loaded few-shot examples.
    """
    def __init__(self, examples_filepath: str,
                 embedding_model_name: Optional[str] = "all-MiniLM-L6-v2",
                 logger: Optional[logging.Logger] = None):
        """Initializes the FewShotManager.

        Args:
            examples_filepath (str): Path to the JSON file containing few-shot examples.
                                     Each example is expected to be a dictionary.
            embedding_model_name (Optional[str]): Name of the sentence transformer model
                                                 to use for semantic similarity. If None,
                                                 semantic/hybrid strategies will be limited.
                                                 Defaults to "all-MiniLM-L6-v2".
            logger (Optional[logging.Logger]): An optional, pre-configured logger instance.
                                               If None, a default logger is created.
        """
        self.examples_filepath = examples_filepath
        self.embedding_model_name = embedding_model_name
        self.logger = logger if logger else self._get_default_logger()
        self.embedding_model: Optional[SentenceTransformer] = None

        if SENTENCE_TRANSFORMERS_AVAILABLE and self.embedding_model_name and SentenceTransformer:
            try:
                self.embedding_model = SentenceTransformer(self.embedding_model_name)
                self._log(f"SentenceTransformer model '{self.embedding_model_name}' loaded successfully.", "info")
            except Exception as e:
                self._log(f"Failed to load SentenceTransformer model '{self.embedding_model_name}': {e}. "
                          "Semantic and hybrid strategies will be affected.", "error", exc_info=True)
                self.embedding_model = None
        else:
            self._log("SentenceTransformers library not available or no embedding model name provided. "
                      "Semantic and hybrid strategies will not be fully functional.", "warning")

        self.examples: List[Dict[str, Any]] = self._load_examples()
        if self.embedding_model:
            self._preprocess_examples_for_embeddings()

    def _get_default_logger(self) -> logging.Logger:
        """Creates and configures a default logger if one is not provided.

        Returns:
            logging.Logger: The configured logger instance.
        """
        logger = logging.getLogger(__name__)
        if not logger.handlers: # Avoid adding multiple handlers if logger is already configured
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO) # Default level for the manager's logger
        return logger

    def _log(self, message: str, level: str = "info", exc_info: bool = False):
        """Helper method for logging messages through the instance's logger.

        Args:
            message (str): The message to log.
            level (str): The logging level (e.g., "info", "warning", "error", "debug").
            exc_info (bool): If True, exception information is added to the log message.
        """
        if level.lower() == "debug": self.logger.debug(message)
        elif level.lower() == "info": self.logger.info(message)
        elif level.lower() == "warning": self.logger.warning(message)
        elif level.lower() == "error": self.logger.error(message, exc_info=exc_info)
        elif level.lower() == "critical": self.logger.critical(message, exc_info=exc_info)
        else: self.logger.info(message) # Default to info for unrecognized levels

    def _load_examples(self) -> List[Dict[str, Any]]:
        """Loads few-shot examples from the JSON file specified in `examples_filepath`.

        Returns:
            List[Dict[str, Any]]: A list of example dictionaries. Returns an empty
            list if the file is not found or cannot be parsed.
        """
        if not os.path.exists(self.examples_filepath):
            self._log(f"Few-shot examples file not found: {self.examples_filepath}. "
                      "Ensure the path is correct or check configuration.", "error")
            return []
        try:
            with open(self.examples_filepath, 'r', encoding='utf-8') as f:
                data: List[Dict[str, Any]] = json.load(f)
            self._log(f"Successfully loaded {len(data)} few-shot examples from {self.examples_filepath}.", "info")
            return data
        except json.JSONDecodeError as e:
            self._log(f"JSON decode error loading examples from {self.examples_filepath}: {e}. "
                      "File might be malformed. Returning empty list.", "error", exc_info=True)
            return []
        except Exception as e:
            self._log(f"Unexpected error loading examples from {self.examples_filepath}: {e}",
                      "error", exc_info=True)
            return []

    def _preprocess_examples_for_embeddings(self):
        """Generates and caches embeddings for examples if an embedding model is loaded.

        Iterates through `self.examples`. If an example does not have an 'embedding'
        field or if it's not a list (indicating pre-computed embedding), this method
        generates an embedding for its 'nl_query' (or 'description' as fallback)
        and stores it as a list of floats in the example dictionary.
        """
        if not self.embedding_model:
            self._log("No embedding model loaded, skipping embedding preprocessing.", "debug")
            return

        self._log("Starting preprocessing of examples for embeddings...", "info")
        processed_count = 0
        for i, example in enumerate(self.examples):
            # Check if embedding is missing or not in the expected list format
            if not isinstance(example.get("embedding"), list):
                text_to_embed = example.get('nl_query') or example.get('description', '') # Prioritize nl_query
                if text_to_embed:
                    try:
                        # Generate embedding using the loaded SentenceTransformer model
                        embedding = self.embedding_model.encode(text_to_embed).tolist()
                        example['embedding'] = embedding
                        processed_count +=1
                        self._log(f"Generated embedding for example ID: {example.get('id', f'index_{i}')}", "debug")
                    except Exception as e:
                        self._log(f"Error generating embedding for example ID {example.get('id', f'index_{i}')}: {e}",
                                  "error", exc_info=True)
                else:
                    self._log(f"No text ('nl_query' or 'description') to embed for example ID: {example.get('id', f'index_{i}')}",
                              "warning")
        self._log(f"Finished preprocessing examples. Generated embeddings for {processed_count} examples.", "info")

    def _extract_keywords(self, text: str) -> List[str]:
        """Extracts unique, non-stopword keywords from a given text string.

        The process involves lowercasing, removing basic punctuation, splitting into
        words, and filtering out common stop words and short words.

        Args:
            text (str): The text string to extract keywords from.

        Returns:
            List[str]: A list of unique keywords.
        """
        if not text: return []
        text_lower = text.lower()
        # Remove common punctuation using regex, keeping alphanumeric and spaces
        text_cleaned = re.sub(r'[^\w\s]', '', text_lower)
        words = text_cleaned.split()
        # Filter out stop words and words with length <= 1 (e.g., single characters)
        keywords = [word for word in words if word not in DEFAULT_STOP_WORDS and len(word) > 1]
        return list(set(keywords)) # Return unique keywords

    def get_relevant_examples(self, nl_query: str, n_examples: int = 3,
                              selection_strategy: str = "random") -> List[Dict[str, Any]]:
        """Selects relevant few-shot examples based on the NL query and strategy.

        Args:
            nl_query (str): The natural language query from the user.
            n_examples (int): The desired number of few-shot examples.
            selection_strategy (str): The strategy for selection. Supported:
                "random": Selects examples randomly.
                "keyword": Scores examples based on keyword overlap with the query.
                "semantic": Scores examples based on semantic similarity to the query
                            using embeddings. Falls back to "keyword" if model unavailable.
                "hybrid": Combines keyword and semantic results. Falls back if model unavailable.
                Any other string defaults to "first_n" (slicing first N examples).

        Returns:
            List[Dict[str, Any]]: A list of selected example dictionaries.
        """
        if not self.examples:
            self._log("No few-shot examples loaded to select from.", "warning")
            return []
        if n_examples <= 0:
            self._log("Number of examples to select (n_examples) must be positive.", "warning")
            return []

        self._log(f"Selecting {n_examples} examples for query '{nl_query[:50]}...' using strategy '{selection_strategy}'.", "info")

        # Ensure we don't try to sample more examples than available
        num_to_sample = min(n_examples, len(self.examples))
        if num_to_sample == 0 and len(self.examples) > 0 : # if n_examples was 0 but we have examples
            num_to_sample = len(self.examples) if n_examples > len(self.examples) else n_examples # re-evaluate if n_examples > 0
            if n_examples <= 0 : return []


        if selection_strategy == "random":
            return random.sample(self.examples, num_to_sample)

        elif selection_strategy == "keyword":
            query_keywords = self._extract_keywords(nl_query)
            if not query_keywords:
                self._log("No keywords extracted from query for 'keyword' strategy. Falling back to random selection.", "warning")
                return random.sample(self.examples, num_to_sample)

            scored_examples: List[Tuple[Dict[str, Any], int]] = []
            for example in self.examples:
                score = 0
                # Fields to check for keywords in the example
                example_nl = example.get('nl_query', '').lower()
                example_desc = example.get('description', '').lower()
                example_intent = example.get('intent', '').lower()
                example_own_keywords = [k.lower() for k in example.get('keywords', []) if isinstance(k, str)]

                for kw in query_keywords:
                    if kw in example_nl: score += 2 # Higher weight for NL query match
                    if kw in example_desc: score += 1
                    if kw in example_intent: score += 1
                    if kw in example_own_keywords: score += 3 # Highest weight for pre-defined keyword match

                if score > 0:
                    scored_examples.append((example, score))

            # Sort by score in descending order
            scored_examples.sort(key=lambda x: x[1], reverse=True)
            self._log(f"Keyword strategy found {len(scored_examples)} matches. Top scores: {[s for _,s in scored_examples[:5]]}", "debug")
            return [ex for ex, score in scored_examples[:num_to_sample]]

        elif selection_strategy == "semantic":
            if not self.embedding_model or not SENTENCE_TRANSFORMERS_AVAILABLE or not cos_sim:
                self._log("Semantic strategy unavailable (embedding model or library missing). Falling back to 'keyword' strategy.", "warning")
                return self.get_relevant_examples(nl_query, n_examples, "keyword")

            try:
                query_embedding = self.embedding_model.encode(nl_query)
            except Exception as e:
                self._log(f"Error encoding query for semantic search: {e}. Falling back to 'keyword'.", "error", exc_info=True)
                return self.get_relevant_examples(nl_query, n_examples, "keyword")

            example_similarities: List[Tuple[Dict[str, Any], float]] = []
            for example in self.examples:
                example_embedding = example.get('embedding')
                if isinstance(example_embedding, list) and len(example_embedding) > 0: # Check if embedding is valid list
                    try:
                        # Calculate cosine similarity
                        similarity_tensor = cos_sim(query_embedding, [example_embedding]) # Pass example_embedding as list of one
                        similarity = similarity_tensor[0][0].item()
                        example_similarities.append((example, similarity))
                    except Exception as e:
                        self._log(f"Error calculating similarity for example ID {example.get('id', 'N/A')}: {e}", "error", exc_info=True)
                        example_similarities.append((example, -1.0)) # Assign very low score on error
                else:
                    example_similarities.append((example, -1.0)) # Example has no valid embedding

            example_similarities.sort(key=lambda x: x[1], reverse=True) # Sort by similarity
            self._log(f"Semantic strategy top similarity scores: {[s for _,s in example_similarities[:5]]}", "debug")
            return [ex for ex, score in example_similarities[:num_to_sample]]

        elif selection_strategy == "hybrid":
            self._log("Using hybrid selection strategy: combining keyword and semantic ranked lists.", "info")
            # Get more examples from each strategy to have a larger pool for final selection
            pool_size = max(n_examples * 2, 5) # Get more to allow for better combined ranking
            keyword_selected = self.get_relevant_examples(nl_query, pool_size, "keyword")
            semantic_selected = self.get_relevant_examples(nl_query, pool_size, "semantic")

            # Combine and de-duplicate, prioritizing items that appear in both or have higher ranks
            # For simplicity, create a dictionary to hold unique examples by ID,
            # then convert back to list. This basic approach doesn't re-score based on combined rank.
            combined_results: Dict[str, Dict[str, Any]] = {}
            for ex in keyword_selected: # Add keyword results first
                if ex.get("id"): combined_results[ex["id"]] = ex
            for ex in semantic_selected: # Add semantic results; if ID exists, it might update (or use first seen)
                if ex.get("id") and ex["id"] not in combined_results: # Add if not already from keyword (keyword preferred if collision)
                    combined_results[ex["id"]] = ex
                elif not ex.get("id"): # Handle examples without ID (less ideal)
                    # This could lead to duplicates if content is same but objects are different.
                    # A more robust de-duplication for non-ID items would be needed.
                    # For now, we add it if it's not an identical object already in values.
                    is_present = False
                    for present_ex in combined_results.values():
                        if present_ex == ex: # Simplistic object comparison
                            is_present = True
                            break
                    if not is_present:
                         # Create a temporary ID for dict key if example has no ID
                         combined_results[f"temp_id_{random.randint(1000,9999)}"] = ex


            final_selection = list(combined_results.values())
            # If still more than n_examples, a simple truncation is applied.
            # More advanced hybrid strategies might re-rank based on combined scores or use reciprocal rank fusion.
            return final_selection[:num_to_sample]

        else: # Default to "first_n" (basic slicing) for any other strategy string
            self._log(f"Unknown or default selection strategy '{selection_strategy}'. Using basic slicing (first N).", "warning")
            return self.examples[:num_to_sample]


    def format_examples_for_prompt(self, examples: List[Dict[str, Any]]) -> str:
        """Formats selected few-shot examples into a string for LLM prompts.

        Each example is formatted to show the user question, the corresponding SQL query,
        and an optional description.

        Args:
            examples (List[Dict[str, Any]]): A list of few-shot example dictionaries.
                Expected keys: 'nl_query', 'sql_query'. Optional: 'description'.

        Returns:
            str: A string containing the formatted examples, separated by newlines.
                 Returns an empty string if no examples are provided or if examples
                 are malformed (missing 'nl_query' or 'sql_query').
        """
        if not examples:
            return ""

        formatted_parts = []
        for i, ex in enumerate(examples):
            nl = ex.get('nl_query')
            sql = ex.get('sql_query')

            # Ensure both nl_query and sql_query are present to form a valid example
            if not nl or not sql:
                self._log(f"Skipping example {ex.get('id', f'index_{i+1}')} due to missing 'nl_query' or 'sql_query'.", "warning")
                continue

            desc = ex.get('description')

            # Construct the example string
            example_str = f"Example {i+1}:\nUser Question: {nl}\nSQL Query: {sql}"
            if desc:
                example_str += f"\nDescription: {desc}"
            example_str += "\n---" # Separator for readability
            formatted_parts.append(example_str)

        # Join all formatted example strings with double newlines
        return "\n\n".join(formatted_parts)

if __name__ == '__main__':
    # Setup a temporary directory for test files
    test_dir = "temp_test_few_shot_files"
    os.makedirs(test_dir, exist_ok=True)
    dummy_examples_path = os.path.join(test_dir, "dummy_nl_to_sql_examples_advanced.json")

    dummy_data = [
        {"id": "ex1", "nl_query": "What is the total sales for product X?", "sql_query": "SELECT SUM(sales) FROM orders WHERE product_name = 'X';", "description": "Total sales for product X", "keywords": ["sales", "product X"], "intent": "get_sales"},
        {"id": "ex2", "nl_query": "Show me active users in engineering department", "sql_query": "SELECT name FROM users WHERE status = 'active' AND department = 'engineering';", "description": "Active users in engineering", "keywords": ["users", "active", "engineering"], "intent": "get_users"},
        {"id": "ex3", "nl_query": "How many issues were created yesterday for project Alpha?", "sql_query": "SELECT COUNT(*) FROM issues WHERE project = 'Alpha' AND creation_date = CURRENT_DATE - 1;", "description": "Issues created yesterday for Alpha", "keywords": ["issues", "yesterday", "project Alpha"], "intent": "count_issues"},
        {"id": "ex4", "nl_query": "List all tasks due this week.", "sql_query": "SELECT task_name FROM tasks WHERE due_date >= date_trunc('week', CURRENT_DATE) AND due_date < date_trunc('week', CURRENT_DATE + interval '1 week');", "description": "Tasks due this week", "keywords": ["tasks", "due", "week"], "intent": "get_tasks"}
    ]
    with open(dummy_examples_path, 'w', encoding='utf-8') as f:
        json.dump(dummy_data, f, indent=4)

    print("--- Testing FewShotManager Advanced Strategies ---")
    manager = FewShotManager(examples_filepath=dummy_examples_path, embedding_model_name="all-MiniLM-L6-v2")

    if not SENTENCE_TRANSFORMERS_AVAILABLE or not manager.embedding_model:
        print("\nWARNING: SentenceTransformers library or model not available. Semantic/Hybrid tests will fallback or be limited.")

    print(f"\nLoaded {len(manager.examples)} examples.")
    if manager.examples and manager.examples[0].get('embedding'):
        print(f"First example embedding length: {len(manager.examples[0]['embedding'])}")


    test_nl_query = "Show active users in sales department"
    print(f"\nTest NL Query: \"{test_nl_query}\"")
    print(f"Extracted keywords from query: {manager._extract_keywords(test_nl_query)}")

    n_select = 2
    print(f"\n--- Keyword Strategy (n={n_select}) ---")
    keyword_examples = manager.get_relevant_examples(test_nl_query, n_examples=n_select, selection_strategy="keyword")
    for ex in keyword_examples: print(f"  ID: {ex.get('id')}, NL: {ex.get('nl_query')}")

    print(f"\n--- Semantic Strategy (n={n_select}) ---")
    semantic_examples = manager.get_relevant_examples(test_nl_query, n_examples=n_select, selection_strategy="semantic")
    for ex in semantic_examples: print(f"  ID: {ex.get('id')}, NL: {ex.get('nl_query')}, Embedding sample: {str(ex.get('embedding', [])[:3])}...")


    print(f"\n--- Hybrid Strategy (n={n_select}) ---")
    hybrid_examples = manager.get_relevant_examples(test_nl_query, n_examples=n_select, selection_strategy="hybrid")
    for ex in hybrid_examples: print(f"  ID: {ex.get('id')}, NL: {ex.get('nl_query')}")

    print(f"\n--- Random Strategy (n={n_select}) ---")
    random_examples = manager.get_relevant_examples(test_nl_query, n_examples=n_select, selection_strategy="random")
    for ex in random_examples: print(f"  ID: {ex.get('id')}, NL: {ex.get('nl_query')}")

    # Clean up
    os.remove(dummy_examples_path)
    os.rmdir(test_dir)
    print(f"\nCleaned up dummy files and directory: {test_dir}")
