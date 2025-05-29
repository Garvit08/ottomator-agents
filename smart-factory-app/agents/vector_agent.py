import os
import sys
from typing import Optional
import chromadb
from sentence_transformers import SentenceTransformer
import numpy as np
import uuid # For generating unique IDs

# Path adjustments for config import
current_dir_vector_agent = os.path.dirname(os.path.abspath(__file__))
project_root_vector_agent = os.path.abspath(os.path.join(current_dir_vector_agent, '..', '..'))
if project_root_vector_agent not in sys.path:
    sys.path.insert(0, os.path.dirname(project_root_vector_agent))

try:
    from config.config import (
        SENTENCE_TRANSFORMER_MODEL, 
        CHROMA_PERSIST_PATH, 
        VECTOR_COLLECTION_NAME
    )
except ImportError:
    print("Error importing config for VectorAgent. Using fallback environment variables/defaults.")
    SENTENCE_TRANSFORMER_MODEL = os.getenv("SENTENCE_TRANSFORMER_MODEL", 'all-MiniLM-L6-v2')
    CHROMA_PERSIST_PATH = os.getenv("CHROMA_PERSIST_PATH", None)
    VECTOR_COLLECTION_NAME = os.getenv("VECTOR_COLLECTION_NAME", "smart_factory_vectors")


class VectorAgent:
    def __init__(self, model_name: str = SENTENCE_TRANSFORMER_MODEL, 
                 chroma_path: Optional[str] = CHROMA_PERSIST_PATH, # Optional type hint
                 collection_name: str = VECTOR_COLLECTION_NAME):
        """
        Initializes the Vector Agent.
        - Loads the sentence transformer model from config.
        - Initializes the ChromaDB client and collection from config.
        """
        self.model_name = model_name
        self.chroma_path = chroma_path
        self.collection_name = collection_name

        print(f"Initializing VectorAgent with model: {self.model_name}, collection: {self.collection_name}")
        try:
            self.model = SentenceTransformer(self.model_name)
            print(f"SentenceTransformer model '{self.model_name}' loaded successfully.")
        except Exception as e:
            print(f"Error loading SentenceTransformer model '{self.model_name}': {e}")
            raise

        try:
            if self.chroma_path:
                print(f"Using persistent ChromaDB storage at: {self.chroma_path}")
                self.client = chromadb.PersistentClient(path=self.chroma_path)
            else:
                print("Using in-memory ChromaDB client.")
                self.client = chromadb.Client() # Default in-memory client
            
            self.collection = self.client.get_or_create_collection(
                name=self.collection_name,
                # metadata={"hnsw:space": "cosine"} # Example: set distance function if needed
            )
            print(f"ChromaDB collection '{self.collection_name}' accessed/created successfully.")
        except Exception as e:
            print(f"Error initializing ChromaDB with path '{self.chroma_path}' and collection '{self.collection_name}': {e}")
            raise

    def add_texts(self, texts: list[str], metadatas: list[dict] = None, ids: list[str] = None):
        """
        Adds texts to the ChromaDB collection.
        - Generates embeddings for the texts.
        - Assigns unique IDs if not provided.
        - Stores texts, embeddings, and metadatas.
        """
        if not texts:
            print("No texts provided to add.")
            return

        print(f"Adding {len(texts)} texts to collection '{self.collection.name}'...")
        try:
            embeddings = self.model.encode(texts).tolist()
        except Exception as e:
            print(f"Error generating embeddings: {e}")
            return

        if ids is None:
            ids = [str(uuid.uuid4()) for _ in texts]
        
        if metadatas is None:
            metadatas = [{} for _ in texts]
        
        if not (len(texts) == len(embeddings) == len(metadatas) == len(ids)):
            print("Error: Texts, embeddings, metadatas, and IDs lists must have the same length.")
            return

        try:
            # ChromaDB expects 'documents' for the text content itself.
            self.collection.add(
                embeddings=embeddings,
                documents=texts, # Store the original texts
                metadatas=metadatas, # type: ignore
                ids=ids
            )
            print(f"Successfully added {len(texts)} items to the collection.")
        except Exception as e:
            print(f"Error adding texts to ChromaDB: {e}")

    def semantic_search(self, query_text: str, n_results: int = 5, where_filter: dict = None): # type: ignore
        """
        Performs semantic search in ChromaDB.
        - Generates embedding for the query text.
        - Queries the collection for similar documents.
        """
        if not query_text:
            print("No query text provided for semantic search.")
            return None
        
        print(f"Performing semantic search for: '{query_text}'")
        try:
            query_embedding = self.model.encode(query_text).tolist()
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results,
                include=['metadatas', 'documents', 'distances'], # Ensure documents are included
                where=where_filter
            )
            return results
        except Exception as e:
            print(f"Error during semantic search: {e}")
            return None

    def keyword_search(self, keywords: list[str], n_results: int = 5, where_filter: dict = None): # type: ignore
        """
        Performs a basic keyword search.
        This is a placeholder and can be improved with more sophisticated methods.
        Currently, it uses ChromaDB's metadata filtering (`where_filter`) or
        a simple text match in retrieved documents if `where_filter` is not specific enough.

        A more robust keyword search would involve creating a `where_document` filter
        if searching the content of the documents.
        """
        if not keywords:
            print("No keywords provided for search.")
            return None

        print(f"Performing keyword search for: {keywords}")
        
        # Construct a document filter for keywords using $contains or $or for multiple keywords
        # Example: {"$or": [{"text_field": {"$contains": "keyword1"}}, {"text_field": {"$contains": "keyword2"}}]}
        # This assumes you have a metadata field 'text_field' or you are using $contains on 'documents'
        # ChromaDB's `where_document` is the more direct way for document content.
        document_conditions = []
        for keyword in keywords:
            document_conditions.append({"$contains": keyword})
        
        if not document_conditions:
             return {"ids": [], "documents": [], "metadatas": [], "distances": []}

        # If there's only one keyword, no need for $or
        final_document_filter = {"$or": document_conditions} if len(document_conditions) > 1 else document_conditions[0]

        try:
            # We are not providing query_embeddings, so this is effectively a metadata/document content search.
            # To make this a pure keyword search without semantic meaning, we can omit query_embeddings
            # and rely solely on where/where_document filters.
            # However, collection.get() is better for pure filtering if no vector search aspect is needed.
            results = self.collection.get(
                where_document=final_document_filter,
                # where=where_filter, # If you also want to filter by metadata
                n_results=n_results, # n_results might not be directly applicable in `get` as in `query`
                                     # it will return all matches up to a limit if one is set for `get`
                include=['metadatas', 'documents']
            )
            # The 'get' method returns a different structure than 'query'.
            # We'll reformat it slightly to be consistent for the hybrid search.
            # 'get' doesn't return distances.
            formatted_results = {
                "ids": [results["ids"]], 
                "documents": [results["documents"]],
                "metadatas": [results["metadatas"]],
                "distances": [[0.0] * len(results["ids"][0])] # Placeholder for distances
            }
            if not results["ids"]: # ChromaDB returns lists of lists for these items from query
                 formatted_results = {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}


            # If 'get' returns flat lists, ensure they are wrapped in another list like query results
            if results and results["ids"] and not isinstance(results["ids"][0], list):
                 formatted_results = {
                    "ids": [results["ids"]],
                    "documents": [results["documents"]],
                    "metadatas": [results["metadatas"]],
                    "distances": [[0.0] * len(results["ids"])] # Placeholder for distances
                }
            else: # Already in the desired list-of-lists structure or empty
                 formatted_results = {
                    "ids": results["ids"] if results["ids"] else [[]],
                    "documents": results["documents"] if results["documents"] else [[]],
                    "metadatas": results["metadatas"] if results["metadatas"] else [[]],
                    "distances": [[0.0] * len(ids_list) for ids_list in results["ids"]] if results["ids"] else [[]]
                }

            return formatted_results

        except Exception as e:
            print(f"Error during keyword search: {e}")
            # Check if it's due to `where_document` not being supported or some other issue
            if "No $contains operator for TEXT type" in str(e) or "Unsupported where_document" in str(e):
                print("Note: `where_document` with `$contains` might require specific ChromaDB versions or configurations.")
                print("Falling back to a manual keyword search if possible (not implemented in this basic version).")
            return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}


    def hybrid_search(self, query_text: str, keywords: list[str], n_results: int = 5, semantic_weight: float = 0.6, keyword_weight: float = 0.4):
        """
        Performs hybrid search by combining semantic and keyword search results.
        - Fetches results from both search types.
        - Combines and re-ranks them (simple combination for now).
        """
        print(f"Performing hybrid search for query: '{query_text}' and keywords: {keywords}")
        
        semantic_results = self.semantic_search(query_text, n_results=n_results)
        keyword_results = self.keyword_search(keywords, n_results=n_results)

        combined_results = {}
        
        # Helper to process and add results
        def process_results(results_dict, search_type_weight, is_semantic=False):
            if not results_dict or not results_dict.get("ids") or not results_dict["ids"][0]:
                return

            for i, doc_id in enumerate(results_dict["ids"][0]):
                if doc_id not in combined_results:
                    combined_results[doc_id] = {
                        "document": results_dict["documents"][0][i],
                        "metadata": results_dict["metadatas"][0][i],
                        "semantic_score": 0.0,
                        "keyword_score": 0.0,
                        "combined_score": 0.0
                    }
                
                if is_semantic:
                    # Lower distance means higher similarity. Convert to score (0 to 1).
                    # Max distance can be > 1 for some distance metrics (e.g. L2).
                    # Cosine distance is typically 0 to 2. 0 = identical, 1 = orthogonal, 2 = opposite.
                    # Score = 1 - distance (for cosine, if distance is 0-1 range)
                    # Or use a non-linear mapping. For simplicity:
                    distance = results_dict["distances"][0][i]
                    combined_results[doc_id]["semantic_score"] = max(0, 1 - distance) # Assuming cosine distance for this scoring
                else: # Keyword match
                    combined_results[doc_id]["keyword_score"] = 1.0 # Binary: 1 if matched by keyword

        process_results(semantic_results, semantic_weight, is_semantic=True)
        process_results(keyword_results, keyword_weight, is_semantic=False)

        # Calculate combined score
        for doc_id in combined_results:
            s_score = combined_results[doc_id]["semantic_score"]
            k_score = combined_results[doc_id]["keyword_score"]
            combined_results[doc_id]["combined_score"] = (s_score * semantic_weight) + (k_score * keyword_weight)

        # Sort by combined score in descending order
        sorted_items = sorted(combined_results.items(), key=lambda item: item[1]["combined_score"], reverse=True)
        
        # Format to be similar to ChromaDB output
        final_results = {
            "ids": [[item[0] for item in sorted_items[:n_results]]],
            "documents": [[item[1]["document"] for item in sorted_items[:n_results]]],
            "metadatas": [[item[1]["metadata"] for item in sorted_items[:n_results]]],
            "scores": [[item[1]["combined_score"] for item in sorted_items[:n_results]]] # Use 'scores' instead of 'distances'
        }
        return final_results

# Example Usage
if __name__ == "__main__":
    # Config import path adjustments are at the top.
    # VectorAgent now uses defaults from config.
    print("Starting VectorAgent example usage (with config values)...")
    
    # Ensure sentence-transformers model (from config) is downloaded (first run might take time)
    try:
        # Initialize with default config values by not passing arguments
        # For testing, you might want to use a specific test collection name
        # agent = VectorAgent(collection_name="factory_docs_test_collection_config")
        agent = VectorAgent() # Uses SENTENCE_TRANSFORMER_MODEL, CHROMA_PERSIST_PATH, VECTOR_COLLECTION_NAME

        print(f"\n--- VectorAgent Configuration ---")
        print(f"Model: {agent.model_name}")
        print(f"Chroma Path: {agent.chroma_path if agent.chroma_path else 'In-memory'}")
        print(f"Collection Name: {agent.collection_name}")
        print(f"--- End VectorAgent Configuration ---\n")

        # 1. Add sample documents
        sample_texts = [
            "Work instruction for assembling the XG-500 unit.",
            "Maintenance schedule for the CNC machine model T-800.",
            "Safety protocol for handling corrosive materials in Area 5.",
            "Quality control checklist for final product inspection.",
            "Troubleshooting guide for the conveyor belt system.",
            "The T-800 CNC machine requires weekly oiling and filter checks."
        ]
        sample_metadatas = [
            {"doc_type": "work_instruction", "model": "XG-500", "version": "1.2"},
            {"doc_type": "maintenance_schedule", "machine": "CNC T-800", "frequency": "weekly"},
            {"doc_type": "safety_protocol", "area": "Area 5", "hazard_level": "high"},
            {"doc_type": "quality_control", "stage": "final_inspection"},
            {"doc_type": "troubleshooting_guide", "system": "conveyor_belt"},
            {"doc_type": "maintenance_procedure", "machine": "CNC T-800", "task": "oiling"}
        ]
        # Generate unique IDs for the sample texts
        sample_ids = [f"doc{i+1}" for i in range(len(sample_texts))]

        agent.add_texts(texts=sample_texts, metadatas=sample_metadatas, ids=sample_ids)
        
        # Verify number of items in collection
        print(f"Collection count: {agent.collection.count()}")

        # 2. Perform semantic search
        print("\n--- Semantic Search ---")
        semantic_query = "How to maintain the T-800 model?"
        search_results = agent.semantic_search(query_text=semantic_query, n_results=2)
        if search_results and search_results["documents"] and search_results["documents"][0]:
            for i, doc in enumerate(search_results["documents"][0]):
                print(f"  Document: {doc}")
                print(f"  Metadata: {search_results['metadatas'][0][i]}")
                print(f"  Distance: {search_results['distances'][0][i]:.4f}\n")
        else:
            print(f"No results found for semantic query: {semantic_query}")

        # 3. Perform keyword search
        print("\n--- Keyword Search ---")
        # This uses where_document with $contains. Ensure your ChromaDB version supports this.
        keywords_to_search = ["CNC", "T-800"] 
        keyword_search_results = agent.keyword_search(keywords=keywords_to_search, n_results=3)
        if keyword_search_results and keyword_search_results["documents"] and keyword_search_results["documents"][0]:
            for i, doc in enumerate(keyword_search_results["documents"][0]):
                print(f"  Document: {doc}")
                print(f"  Metadata: {keyword_search_results['metadatas'][0][i]}\n")
        else:
            print(f"No results found for keywords: {keywords_to_search}")


        # 4. Perform hybrid search
        print("\n--- Hybrid Search ---")
        hybrid_query = "instructions for T-800 machine"
        hybrid_keywords = ["T-800", "instruction"]
        hybrid_search_results = agent.hybrid_search(query_text=hybrid_query, keywords=hybrid_keywords, n_results=3)
        if hybrid_search_results and hybrid_search_results["documents"] and hybrid_search_results["documents"][0]:
            for i, doc in enumerate(hybrid_search_results["documents"][0]):
                print(f"  Document: {doc}")
                print(f"  Metadata: {hybrid_search_results['metadatas'][0][i]}")
                print(f"  Combined Score: {hybrid_search_results['scores'][0][i]:.4f}\n") # Using 'scores' from hybrid
        else:
            print(f"No results found for hybrid search query: {hybrid_query}, keywords: {hybrid_keywords}")

        # Clean up (optional, especially for in-memory)
        # If you want to delete the collection after testing:
        # agent.client.delete_collection(name=agent.collection.name)
        # print(f"\nCollection '{agent.collection.name}' deleted.")
        
    except Exception as e:
        print(f"An error occurred during VectorAgent example usage: {e}")
        import traceback
        traceback.print_exc()

    print("\nVectorAgent example usage finished.")
