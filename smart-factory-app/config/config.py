import os

# --- PostgreSQL Configuration ---
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "password")
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_NAME = os.environ.get("DB_NAME", "smart_factory_db")
DATABASE_URI = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# --- Neo4j Configuration ---
NEO4J_URI = os.environ.get("NEO4J_URI", "neo4j://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "password")

# --- Vector DB (Chroma) Configuration ---
CHROMA_PERSIST_PATH = os.environ.get("CHROMA_PERSIST_PATH", None) # None means in-memory
VECTOR_COLLECTION_NAME = os.environ.get("VECTOR_COLLECTION_NAME", "smart_factory_vectors")

# --- Sentence Transformer Model Configuration ---
SENTENCE_TRANSFORMER_MODEL = os.environ.get("SENTENCE_TRANSFORMER_MODEL", "all-MiniLM-L6-v2")

# --- Ollama Configuration ---
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "mistral")

# --- ETL Configuration ---
# Convert string "true" or "false" to boolean
ETL_USE_MOCK_DB_STR = os.environ.get("ETL_USE_MOCK_DB", "true")
ETL_USE_MOCK_DB = ETL_USE_MOCK_DB_STR.lower() == "true"

# --- API Configuration ---
API_USE_MOCK_AGENTS_STR = os.environ.get("API_USE_MOCK_AGENTS", "true") # If agents can't be imported, API will use mocks
API_USE_MOCK_AGENTS = API_USE_MOCK_AGENTS_STR.lower() == "true"

# --- Prompts Configuration ---
# Assuming prompts are in smart-factory-app/prompts/
PROMPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'prompts')
PARSE_QUERY_PROMPT_FILE = os.path.join(PROMPTS_DIR, 'parse_query_prompt.txt')
GENERATE_RESPONSE_PROMPT_FILE = os.path.join(PROMPTS_DIR, 'generate_response_prompt.txt')

if __name__ == "__main__":
    # Print out all config variables to verify
    print(f"DB_USER: {DB_USER}")
    print(f"DB_PASSWORD: {'*' * len(DB_PASSWORD) if DB_PASSWORD else 'None'}")
    print(f"DB_HOST: {DB_HOST}")
    print(f"DB_PORT: {DB_PORT}")
    print(f"DB_NAME: {DB_NAME}")
    print(f"DATABASE_URI: {DATABASE_URI.replace(DB_PASSWORD, '********') if DB_PASSWORD else DATABASE_URI}")
    print(f"NEO4J_URI: {NEO4J_URI}")
    print(f"NEO4J_USER: {NEO4J_USER}")
    print(f"NEO4J_PASSWORD: {'*' * len(NEO4J_PASSWORD) if NEO4J_PASSWORD else 'None'}")
    print(f"CHROMA_PERSIST_PATH: {CHROMA_PERSIST_PATH}")
    print(f"VECTOR_COLLECTION_NAME: {VECTOR_COLLECTION_NAME}")
    print(f"SENTENCE_TRANSFORMER_MODEL: {SENTENCE_TRANSFORMER_MODEL}")
    print(f"OLLAMA_BASE_URL: {OLLAMA_BASE_URL}")
    print(f"OLLAMA_MODEL: {OLLAMA_MODEL}")
    print(f"ETL_USE_MOCK_DB: {ETL_USE_MOCK_DB}")
    print(f"API_USE_MOCK_AGENTS: {API_USE_MOCK_AGENTS}")
    print(f"PROMPTS_DIR: {PROMPTS_DIR}")
    print(f"PARSE_QUERY_PROMPT_FILE: {PARSE_QUERY_PROMPT_FILE}")
    print(f"GENERATE_RESPONSE_PROMPT_FILE: {GENERATE_RESPONSE_PROMPT_FILE}")
