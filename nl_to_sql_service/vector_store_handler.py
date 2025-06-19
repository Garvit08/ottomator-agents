# nl_to_sql_service/vector_store_handler.py
"""Handles interactions with a vector store, specifically ChromaDB.

This module provides the VectorStoreHandler class, which is responsible for:
1. Initializing a connection to a persistent ChromaDB instance.
2. Loading and using a SentenceTransformer model for generating embeddings.
3. Populating the vector store with schema chunks (text content and metadata).
4. Retrieving relevant schema chunks from the vector store based on a query embedding.
"""

import os
import logging
from typing import List, Dict, Any, Optional

# Attempt to import ChromaDB and SentenceTransformer
try:
    import chromadb
    CHROMA_AVAILABLE = True
except ImportError:
    chromadb = None # type: ignore
    CHROMA_AVAILABLE = False

try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SentenceTransformer = None # type: ignore
    SENTENCE_TRANSFORMERS_AVAILABLE = False

class VectorStoreHandler:
    """Handles interactions with a vector store (e.g., ChromaDB) for schema RAG.

    Manages the connection to ChromaDB, embedding generation using SentenceTransformers,
    and provides methods to populate and query the vector store with schema chunks.

    Attributes:
        config (Any): Configuration object expected to have attributes like
                      `chroma_persist_path`, `collection_name`, `embedding_model_name`.
                      (Should be a Pydantic model in a full setup, e.g., VectorStoreConfig).
        logger (logging.Logger): Logger for messages.
        embedding_model (Optional[SentenceTransformer]): Loaded sentence transformer model.
        chroma_client (Optional[chromadb.PersistentClient]): ChromaDB persistent client.
        collection (Optional[chromadb.api.models.Collection.Collection]): ChromaDB collection.
    """

    def __init__(self, config: Any, logger: Optional[logging.Logger] = None):
        """
        Initializes the VectorStoreHandler.

        Args:
            config (Any): A configuration object or dictionary containing:
                - `chroma_persist_path` (str): Filesystem path for ChromaDB persistence.
                - `collection_name` (str): Name of the ChromaDB collection to use.
                - `embedding_model_name` (str): Name of the SentenceTransformer model.
            logger (Optional[logging.Logger]): An optional, pre-configured logger instance.
        """
        self.config = config
        self.logger = logger if logger else self._get_default_logger()
        self.embedding_model: Optional[SentenceTransformer] = None
        self.chroma_client: Optional[chromadb.PersistentClient] = None
        self.collection: Optional[chromadb.api.models.Collection.Collection] = None # type: ignore

        self._log("Initializing VectorStoreHandler...", "info")

        if not CHROMA_AVAILABLE:
            self._log("ChromaDB library not found. VectorStoreHandler cannot function.", "error")
            return # Early exit if critical dependency is missing
        if not SENTENCE_TRANSFORMERS_AVAILABLE or SentenceTransformer is None:
            self._log("SentenceTransformers library not found. VectorStoreHandler cannot function effectively.", "error")
            return # Early exit

        # Initialize Embedding Model
        try:
            model_name = getattr(self.config, 'embedding_model_name', 'all-MiniLM-L6-v2')
            self.embedding_model = SentenceTransformer(model_name)
            self._log(f"SentenceTransformer model '{model_name}' loaded successfully.", "info")
        except Exception as e:
            self._log(f"Error loading SentenceTransformer model '{getattr(self.config, 'embedding_model_name', 'N/A')}': {e}",
                      "error", exc_info=True)
            self.embedding_model = None # Ensure it's None if loading fails

        # Initialize ChromaDB Client and Collection
        if chromadb: # Check if chromadb was imported successfully
            try:
                persist_path = getattr(self.config, 'chroma_persist_path', './chroma_db_store')
                collection_name_val = getattr(self.config, 'collection_name', 'nl_sql_schema_store')

                if not os.path.exists(persist_path):
                    os.makedirs(persist_path, exist_ok=True)
                    self._log(f"Created ChromaDB persistence directory: {persist_path}", "info")

                self.chroma_client = chromadb.PersistentClient(path=persist_path)

                # Note: ChromaDB's get_or_create_collection can take an embedding_function.
                # If using a SentenceTransformerEmbeddingFunction from chromadb.utils.embedding_functions,
                # it can be passed here. However, manually embedding before adding gives more control
                # and ensures our specific loaded model is used.
                self.collection = self.chroma_client.get_or_create_collection(
                    name=collection_name_val
                    # metadata={"hnsw:space": "cosine"} # Optional: specify distance metric
                )
                self._log(f"ChromaDB client initialized. Path: '{persist_path}'. Collection '{collection_name_val}' loaded/created.", "info")
            except Exception as e:
                self._log(f"Error initializing ChromaDB client/collection: {e}", "error", exc_info=True)
                self.chroma_client = None
                self.collection = None
        else:
            self._log("ChromaDB client could not be initialized as library is unavailable.", "error")


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

    def _log(self, message: str, level: str = "info", exc_info:bool = False):
        """Helper method for logging messages."""
        if level.lower() == "debug": self.logger.debug(message)
        elif level.lower() == "info": self.logger.info(message)
        elif level.lower() == "warning": self.logger.warning(message)
        elif level.lower() == "error": self.logger.error(message, exc_info=exc_info)
        elif level.lower() == "critical": self.logger.critical(message, exc_info=exc_info)
        else: self.logger.info(message)


    def populate_vector_store(self, schema_chunks: List[Dict[str, Any]], batch_size: int = 100):
        """Populates the vector store with schema chunks.

        Args:
            schema_chunks (List[Dict[str, Any]]): A list of dictionaries, where each
                dictionary represents a schema chunk. Expected keys:
                - "text_content" (str): The textual representation of the schema chunk.
                - "metadata" (Dict[str, Any]): Metadata associated with the chunk,
                  which must include at least "table_name".
            batch_size (int): Number of chunks to process and add in a single batch.
        """
        if not self.embedding_model:
            self._log("Embedding model not available. Cannot populate vector store.", "error")
            return
        if not self.collection:
            self._log("ChromaDB collection not available. Cannot populate vector store.", "error")
            return
        if not schema_chunks:
            self._log("No schema chunks provided to populate.", "info")
            return

        self._log(f"Starting population of vector store with {len(schema_chunks)} chunks in batches of {batch_size}.", "info")

        num_chunks = len(schema_chunks)
        for i in range(0, num_chunks, batch_size):
            batch = schema_chunks[i:i + batch_size]
            batch_texts = [chunk["text_content"] for chunk in batch]
            batch_metadatas = [chunk["metadata"] for chunk in batch]

            # Generate unique IDs for each chunk to enable potential updates/deletes
            # Using table_name and an index within the batch for simplicity.
            # A hash of text_content could also be used for content-addressable IDs.
            batch_ids = [f"chunk_{chunk['metadata'].get('table_name', 'unknown_table')}_{j+i}" for j, chunk in enumerate(batch)]

            try:
                self._log(f"Processing batch {i//batch_size + 1}/{(num_chunks + batch_size - 1)//batch_size} ({len(batch)} chunks)...", "debug")
                batch_embeddings = self.embedding_model.encode(batch_texts).tolist()

                self.collection.add(
                    ids=batch_ids,
                    embeddings=batch_embeddings,
                    documents=batch_texts,
                    metadatas=batch_metadatas
                )
                self._log(f"Successfully added batch of {len(batch)} chunks to collection '{self.collection.name}'.", "info")
            except Exception as e:
                self._log(f"Error adding batch to ChromaDB: {e}", "error", exc_info=True)

        self._log(f"Vector store population completed. Total chunks processed: {num_chunks}.", "info")


    def retrieve_relevant_schema_chunks(self, query_text: str, n_results: int = 3) -> List[Dict[str, Any]]:
        """Retrieves relevant schema chunks (text and metadata) from the vector store.

        Args:
            query_text (str): The NL query or text to find relevant schema chunks for.
            n_results (int): The maximum number of relevant chunks to retrieve.

        Returns:
            List[Dict[str, Any]]: A list of dictionaries, where each dictionary
            contains 'text_content' and 'metadata' for a retrieved chunk.
            Returns an empty list on failure or if no relevant chunks are found.
        """
        if not self.embedding_model:
            self._log("Embedding model not available. Cannot retrieve schema chunks.", "error")
            return []
        if not self.collection:
            self._log("ChromaDB collection not available. Cannot retrieve schema chunks.", "error")
            return []

        self._log(f"Retrieving {n_results} relevant schema chunks for query: '{query_text[:100]}...'", "info")
        retrieved_items: List[Dict[str, Any]] = []
        try:
            query_embedding = self.embedding_model.encode(query_text).tolist()

            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results,
                include=['documents', 'metadatas'] # Request documents and their metadata
            )

            # Process results if available
            # results['documents'] is List[List[str]]
            # results['metadatas'] is List[List[Dict[str, Any]]]
            if results and results.get('documents') and results.get('metadatas'):
                docs_batch = results['documents'][0] # First (and only) query result
                metadatas_batch = results['metadatas'][0]

                if len(docs_batch) == len(metadatas_batch):
                    for i in range(len(docs_batch)):
                        retrieved_items.append({
                            "text_content": docs_batch[i],
                            "metadata": metadatas_batch[i] if metadatas_batch[i] else {}
                        })
                    self._log(f"Retrieved {len(retrieved_items)} schema chunks with metadata from vector store.", "info")
                else:
                    self._log("Mismatch between number of documents and metadatas returned by ChromaDB query.", "warning")
                    # Fallback: just return documents if metadata is mismatched
                    # for doc_text in docs_batch:
                    #     retrieved_items.append({"text_content": doc_text, "metadata": {}})

            if not retrieved_items:
                 self._log(f"No relevant schema chunks found for the query.", "info")

            return retrieved_items
        except Exception as e:
            self._log(f"Error retrieving schema chunks from ChromaDB: {e}", "error", exc_info=True)
            return []

if __name__ == '__main__':
    # This example requires ChromaDB and SentenceTransformers to be installed.
    # It also assumes a local ChromaDB persistence path.

    # Setup basic logging for the example
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger = logging.getLogger("VectorStoreHandlerExample")

    # Dummy Config for testing
    class DummyVecStoreConfig:
        chroma_persist_path = "./temp_chroma_store_for_example"
        collection_name = "test_schema_collection"
        embedding_model_name = "all-MiniLM-L6-v2" # A common, small model

    config = DummyVecStoreConfig()

    # Clean up previous test run if any
    if os.path.exists(config.chroma_persist_path):
        import shutil
        shutil.rmtree(config.chroma_persist_path)
        logger.info(f"Cleaned up old test ChromaDB store: {config.chroma_persist_path}")

    if not CHROMA_AVAILABLE or not SENTENCE_TRANSFORMERS_AVAILABLE:
        logger.error("ChromaDB or SentenceTransformers library not installed. Skipping VectorStoreHandler example.")
    else:
        logger.info("--- Running VectorStoreHandler Example ---")
        handler = VectorStoreHandler(config=config, logger=logger)

        if handler.collection and handler.embedding_model:
            # Example schema chunks
            sample_schema_chunks = [
                {"text_content": "Table: users | Columns: id (INT, PK), name (TEXT), email (TEXT) | Description: Stores user information.",
                 "metadata": {"table_name": "users", "source": "ddl_parser"}},
                {"text_content": "Table: orders | Columns: order_id (INT, PK), user_id (INT, FK to users.id), order_date (DATE), amount (DECIMAL) | Description: Stores customer orders.",
                 "metadata": {"table_name": "orders", "source": "ddl_parser"}},
                {"text_content": "Table: products | Columns: product_id (INT, PK), name (TEXT), category (TEXT), price (DECIMAL) | Description: Stores product details.",
                 "metadata": {"table_name": "products", "source": "ddl_parser"}},
                {"text_content": "Hypertable: sensor_data | Columns: time (TIMESTAMPTZ, PK), device_id (TEXT, PK), temperature (FLOAT), humidity (FLOAT) | Description: Stores time-series sensor readings. Partitioned by time.",
                 "metadata": {"table_name": "sensor_data", "object_type": "HYPERTABLE"}}
            ]

            # Populate vector store
            handler.populate_vector_store(sample_schema_chunks)

            # Retrieve relevant chunks
            query = "details about user orders and their products"
            logger.info(f"\nQuerying for: '{query}'")
            retrieved_chunks = handler.retrieve_relevant_schema_chunks(query_text=query, n_results=2)

            logger.info("\nRetrieved Chunks:")
            for i, chunk_text in enumerate(retrieved_chunks):
                logger.info(f"  Chunk {i+1}: {chunk_text}")

            # Verify count in collection (optional)
            if handler.collection:
                logger.info(f"Total items in collection '{handler.collection.name}': {handler.collection.count()}")

        else:
            logger.error("VectorStoreHandler or its components failed to initialize. Example cannot run fully.")

        # Clean up test ChromaDB store
        if os.path.exists(config.chroma_persist_path):
            import shutil
            shutil.rmtree(config.chroma_persist_path)
            logger.info(f"Cleaned up test ChromaDB store: {config.chroma_persist_path}")
```
