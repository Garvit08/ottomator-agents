# nl_to_sql_service/few_shot_manager.py
import json
import random # For initial basic selection strategy
from typing import Dict, List, Optional, Any
import os # For checking file path
import logging # Using standard logging

class FewShotManager:
    """
    Handles loading, selection, and formatting of few-shot examples
    for the NL-to-SQL conversion process.
    """
    def __init__(self, examples_filepath: str,
                 embedding_model_name: Optional[str] = None,
                 logger: Optional[logging.Logger] = None):
        """
        Initializes the FewShotManager.

        Args:
            examples_filepath (str): Path to the JSON file containing few-shot examples.
            embedding_model_name (Optional[str]): Name of the sentence transformer model
                                                 for semantic similarity (if strategy requires it).
                                                 Currently a placeholder for future implementation.
            logger (Optional[logging.Logger]): An optional logger instance.
        """
        self.examples_filepath = examples_filepath
        self.embedding_model_name = embedding_model_name # Placeholder for future use
        self.embedding_model = None # Placeholder for future use
        self.logger = logger if logger else self._get_default_logger()

        self.examples = self._load_examples()

        # Placeholder for future embedding model loading and example preprocessing
        # if self.embedding_model_name:
        #     self._log(f"Embedding model '{self.embedding_model_name}' would be loaded here.", "info")
        #     # self._preprocess_examples_for_embeddings()

    def _get_default_logger(self) -> logging.Logger:
        logger = logging.getLogger(__name__)
        if not logger.handlers: # Add handler only if no handlers are configured
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO) # Default level
        return logger

    def _log(self, message: str, level: str = "info"):
        if level.lower() == "info":
            self.logger.info(message)
        elif level.lower() == "warning":
            self.logger.warning(message)
        elif level.lower() == "error":
            self.logger.error(message)
        elif level.lower() == "debug":
            self.logger.debug(message)
        else:
            self.logger.info(message) # Default to info

    def _load_examples(self) -> List[Dict[str, Any]]:
        """Loads examples from the specified JSON file."""
        # Path resolution considerations:
        # If examples_filepath is relative, its base path needs to be well-defined.
        # For instance, if it's relative to the project root or a specific 'data' directory.
        # The config_manager currently makes base_prompt_template_path relative to its own dir.
        # For few_shot_examples_path, it's a direct path from env/default.
        # If it's a relative path like "nl_to_sql_examples.json", we might assume it's
        # relative to where the application is run from, or a pre-defined data directory.

        # For robustness, paths provided from config should ideally be absolute
        # or resolved relative to a clear base path (e.g., project root).
        # Here, we'll just check existence and log.
        if not os.path.exists(self.examples_filepath):
            self._log(f"Few-shot examples file not found: {self.examples_filepath}. "
                      "Please ensure the file exists or check 'few_shot_examples_path' in config.", "error")
            return []

        try:
            with open(self.examples_filepath, 'r', encoding='utf-8') as f:
                data: List[Dict[str, Any]] = json.load(f)
            self._log(f"Successfully loaded {len(data)} few-shot examples from {self.examples_filepath}.", "info")
            return data
        except json.JSONDecodeError as e:
            self._log(f"Error: Could not decode JSON from {self.examples_filepath}. Error: {e}. Returning empty list.", "error")
            return []
        except Exception as e:
            self._log(f"An unexpected error occurred loading examples from {self.examples_filepath}: {e}", "error")
            return []

    def get_relevant_examples(self, nl_query: str, n_examples: int = 3,
                              selection_strategy: str = "random") -> List[Dict[str, Any]]:
        """
        Selects relevant few-shot examples based on the natural language query.

        Args:
            nl_query (str): The natural language query from the user.
            n_examples (int): The desired number of few-shot examples.
            selection_strategy (str): The strategy to use for selection.
                                      Supported: "random", "first_n" (default for others).
                                      Future: "keyword", "semantic", "hybrid".

        Returns:
            List[Dict[str, Any]]: A list of selected example dictionaries.
        """
        if not self.examples:
            self._log("No few-shot examples loaded to select from.", "warning")
            return []

        self._log(f"Selecting {n_examples} examples for query '{nl_query[:50]}...' using strategy '{selection_strategy}'.", "debug")

        if n_examples <= 0:
            return []

        if selection_strategy == "random":
            if not self.examples: return [] # Should be caught by above, but defensive
            # Ensure n_examples does not exceed the number of available examples
            num_to_sample = min(n_examples, len(self.examples))
            return random.sample(self.examples, num_to_sample)

        elif selection_strategy in ["keyword", "semantic", "hybrid"]:
            # Placeholder for more advanced strategies
            # These would require further implementation (e.g., keyword matching, embedding comparisons)
            self._log(f"Strategy '{selection_strategy}' is planned but not fully implemented. "
                      "Using basic slicing (first N examples) as a fallback.", "warning")
            return self.examples[:min(n_examples, len(self.examples))] # Return a copy of the slice

        else: # Default to "first_n" or basic slicing if strategy is unknown or "first_n"
            self._log(f"Unknown or default selection strategy '{selection_strategy}'. Using basic slicing (first N).", "debug")
            return self.examples[:min(n_examples, len(self.examples))] # Return a copy

    def format_examples_for_prompt(self, examples: List[Dict[str, Any]]) -> str:
        """
        Formats a list of selected example dictionaries into a string
        suitable for inclusion in an LLM prompt.

        Args:
            examples (List[Dict[str, Any]]): A list of few-shot example dictionaries.
                                         Each dictionary is expected to have at least
                                         'nl_query' and 'sql_query' keys.
                                         'description' is optional.
        Returns:
            str: A string containing the formatted examples, or an empty string
                 if no examples are provided or if examples are malformed.
        """
        if not examples:
            return ""

        formatted_parts = []
        for i, ex in enumerate(examples):
            nl = ex.get('nl_query')
            sql = ex.get('sql_query')

            if not nl or not sql:
                self._log(f"Skipping example {ex.get('id', i+1)} due to missing 'nl_query' or 'sql_query'.", "warning")
                continue

            desc = ex.get('description')

            example_str = f"Example {i+1}:\nUser Question: {nl}\nSQL Query: {sql}"
            if desc:
                example_str += f"\nDescription: {desc}"
            # Using a clear separator for each example block
            example_str += "\n---"
            formatted_parts.append(example_str)

        # Join example blocks with double newlines for readability in the prompt
        return "\n\n".join(formatted_parts)

# Example Usage (for testing or direct script run):
if __name__ == '__main__':
    # Create a dummy examples file for testing
    dummy_examples_path = "dummy_nl_to_sql_examples.json"
    dummy_data = [
        {
            "id": "ex1", "nl_query": "What is X?", "sql_query": "SELECT X FROM T1;",
            "description": "Desc for X", "keywords": ["X"], "intent": "get_x"
        },
        {
            "id": "ex2", "nl_query": "Count Y where Z > 10", "sql_query": "SELECT COUNT(Y) FROM T2 WHERE Z > 10;",
            "description": "Desc for Y", "keywords": ["Y", "Z"], "intent": "count_y"
        },
        {
            "id": "ex3", "nl_query": "Show all A for B", "sql_query": "SELECT A FROM T3 WHERE B_COL = 'B';",
            "description": "Desc for A B", "keywords": ["A", "B"], "intent": "get_a_for_b"
        },
         {
            "id": "ex4", "nl_query": "Find C in D", "sql_query": "SELECT C FROM T4 WHERE D_COL = 'D';",
            "description": "Desc for C D", "keywords": ["C", "D"], "intent": "find_c"
        }
    ]
    with open(dummy_examples_path, 'w', encoding='utf-8') as f:
        json.dump(dummy_data, f, indent=4)

    # Test with default logger
    print("--- Testing with default logger ---")
    manager = FewShotManager(examples_filepath=dummy_examples_path)
    print(f"Loaded {len(manager.examples)} examples.")

    selected_random = manager.get_relevant_examples("some query", n_examples=2, selection_strategy="random")
    print(f"\nSelected Random Examples (n=2): {len(selected_random)}")
    for ex in selected_random: print(ex.get("id"))

    selected_first_n = manager.get_relevant_examples("some query", n_examples=2, selection_strategy="first_n")
    print(f"\nSelected First-N Examples (n=2): {len(selected_first_n)}")
    for ex in selected_first_n: print(ex.get("id"))

    formatted_prompt_str = manager.format_examples_for_prompt(selected_first_n)
    print(f"\nFormatted Prompt String for First-N:\n{formatted_prompt_str}")

    # Test with non-existent file
    print("\n--- Testing with non-existent file ---")
    non_existent_manager = FewShotManager(examples_filepath="non_existent_examples.json")
    print(f"Loaded {len(non_existent_manager.examples)} examples (should be 0).")

    # Test with malformed JSON
    malformed_examples_path = "malformed_nl_to_sql_examples.json"
    with open(malformed_examples_path, 'w', encoding='utf-8') as f:
        f.write("[{'id': 'bad', 'nl_query': 'test' ") # Incomplete JSON

    print("\n--- Testing with malformed JSON file ---")
    malformed_manager = FewShotManager(examples_filepath=malformed_examples_path)
    print(f"Loaded {len(malformed_manager.examples)} examples (should be 0).")

    # Clean up dummy files
    os.remove(dummy_examples_path)
    os.remove(malformed_examples_path)

    # Test formatting with missing keys
    print("\n--- Testing formatting with missing keys ---")
    missing_key_examples = [{"id":"mk1", "nl_query":"NLQ1"}, {"id":"mk2", "sql_query":"SQL2"}]
    formatted_missing = manager.format_examples_for_prompt(missing_key_examples)
    print(f"Formatted missing key examples:\n'{formatted_missing}' (should be empty or skip problematic ones)")

    empty_examples = []
    formatted_empty = manager.format_examples_for_prompt(empty_examples)
    print(f"Formatted empty examples:\n'{formatted_empty}' (should be empty)")
