# nl_to_sql_service/schema_processor.py
"""Processes detailed database schema information into formatted text chunks.

This module defines the SchemaProcessor class, which takes structured schema
details (typically from DBSchemaHandler) and transforms each table's information
into a comprehensive, human-readable text string suitable for embedding and
use in RAG (Retrieval Augmented Generation) systems for NL-to-SQL tasks.
"""
from typing import List, Dict, Any, Optional
import logging

class SchemaProcessor:
    """Processes detailed database schema information into formatted text chunks.

    The primary method, `create_schema_chunks`, converts a structured representation
    of the database schema (including table types, column details, descriptions,
    primary/foreign keys, and TimescaleDB specifics) into a list of dictionaries,
    where each dictionary contains a formatted text chunk (`text_content`) for a
    single table and associated metadata.
    """
    def __init__(self, logger: Optional[logging.Logger] = None):
        """Initializes the SchemaProcessor.

        Args:
            logger (Optional[logging.Logger]): An optional, pre-configured logger instance.
                                               If None, a default logger is created.
        """
        self.logger = logger if logger else self._get_default_logger()
        self._log("SchemaProcessor initialized.", "info")

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

    def _log(self, message: str, level: str = "info", exc_info: bool = False):
        """Helper method for logging messages."""
        if level.lower() == "debug": self.logger.debug(message)
        elif level.lower() == "info": self.logger.info(message)
        elif level.lower() == "warning": self.logger.warning(message)
        elif level.lower() == "error": self.logger.error(message, exc_info=exc_info)
        elif level.lower() == "critical": self.logger.critical(message, exc_info=exc_info)
        else: self.logger.info(message)


    def create_schema_chunks(self, detailed_schema_info: Dict[str, Dict[str, Any]],
                             include_sample_values: bool = False) -> List[Dict[str, Any]]:
        """
        Transforms detailed structured schema information into formatted text chunks.

        Each chunk corresponds to a single table or view and contains its properties,
        column details, and relationships in a human-readable format.

        Args:
            detailed_schema_info: A dictionary where keys are table/view names,
                and values are dictionaries containing detailed information for that
                object (e.g., from `DBSchemaHandler._fetch_schema_data`).
                Expected structure per table:
                {
                    "table_type": str, (e.g., "TABLE", "VIEW", "HYPERTABLE")
                    "description": Optional[str],
                    "columns": List[Dict[str, Any]], (name, type, is_nullable, description, is_pk)
                    "primary_keys": List[str],
                    "foreign_keys": List[Dict[str, str]], (column, references_table, references_column)
                    "timescale_dimensions": Optional[List[Dict[str, Any]]], (for hypertables)
                    "continuous_aggregate_definition": Optional[str] (for CAGGs)
                }
            include_sample_values (bool): If True, attempts to include sample values
                for columns in the text chunk (assuming sample values are provided
                within the column details in `detailed_schema_info`). Defaults to False.

        Returns:
            List[Dict[str, Any]]: A list of chunk dictionaries. Each dictionary has:
                - "text_content": A formatted string with all details for one table/view.
                - "metadata": A dictionary with at least {"table_name": str, "object_type": str}.
        """
        self._log(f"Creating schema chunks for {len(detailed_schema_info)} tables/views. "
                  f"Include sample values: {include_sample_values}", "info")

        all_chunks: List[Dict[str, Any]] = []

        for table_name, table_details in detailed_schema_info.items():
            chunk_parts: List[str] = []

            table_type = table_details.get("table_type", "TABLE") # Default to TABLE if not specified
            chunk_parts.append(f"Table: {table_name}")
            chunk_parts.append(f"Type: {table_type}")

            if table_details.get("description"):
                chunk_parts.append(f"Description: {table_details['description']}")

            # TimescaleDB specific information
            if table_type == "HYPERTABLE" and table_details.get("timescale_dimensions"):
                dims_str_parts = []
                for dim in table_details["timescale_dimensions"]:
                    dims_str_parts.append(f"{dim.get('column_name', 'N/A')} (type: {dim.get('dimension_type', 'N/A')}, partitions: {dim.get('num_partitions', 'N/A')})")
                if dims_str_parts:
                    chunk_parts.append(f"Time/Space Partitioning Key(s): {'; '.join(dims_str_parts)}")

            if table_type == "CONTINUOUS AGGREGATE" and table_details.get("continuous_aggregate_definition"):
                # Add a snippet of the CA definition for brevity, or the full one if it's not too long
                ca_def = table_details['continuous_aggregate_definition']
                ca_def_snippet = (ca_def[:200] + '...') if len(ca_def) > 200 else ca_def
                chunk_parts.append(f"Aggregate Definition (Snippet): {ca_def_snippet}")

            # Column details
            columns = table_details.get("columns", [])
            if columns:
                chunk_parts.append("Columns:")
                for col in columns:
                    col_name = col.get("name", "N/A")
                    col_type = col.get("type", "N/A")
                    col_is_pk = "Yes" if col.get("is_pk") else "No"
                    col_is_nullable = "Yes" if col.get("is_nullable") else "No" # Assuming is_nullable is boolean
                    col_desc = col.get("description", "N/A") or "N/A" # Ensure not None

                    # Foreign key information for this column
                    fk_info_str = "No"
                    # Check against the table-level foreign_keys list
                    for fk in table_details.get("foreign_keys", []):
                        if fk.get("column") == col_name:
                            ref_table = fk.get("references_table", "N/A")
                            ref_col = fk.get("references_column", "N/A")
                            fk_info_str = f"Yes (references {ref_table}({ref_col}))"
                            break

                    col_str = (f"- {col_name} (Type: {col_type}, PK: {col_is_pk}, Nullable: {col_is_nullable}, "
                               f"FK: {fk_info_str}, Description: {col_desc})")

                    if include_sample_values and col.get("sample_values"):
                        # Assuming sample_values is a list of strings or numbers
                        sample_vals_str = ", ".join(map(str, col["sample_values"][:3])) # Show up to 3 samples
                        col_str += f" Sample Values: [{sample_vals_str}]"
                    chunk_parts.append(col_str)
            else:
                chunk_parts.append("Columns: (No column information available)")

            # Primary Keys (if not already clear from PK in column list)
            # primary_keys = table_details.get("primary_keys", [])
            # if primary_keys:
            #     chunk_parts.append(f"Primary Key(s): {', '.join(primary_keys)}")

            text_content = "\n".join(chunk_parts)
            metadata = {
                "table_name": table_name,
                "object_type": table_type
                # Add other relevant metadata, e.g., schema_name if it varies
            }
            all_chunks.append({"text_content": text_content, "metadata": metadata})
            self._log(f"Created chunk for table: {table_name}", "debug")

        self._log(f"Successfully created {len(all_chunks)} schema chunks.", "info")
        return all_chunks


if __name__ == '__main__':
    # Example Usage
    logging.basicConfig(level=logging.DEBUG)
    logger = logging.getLogger(__name__)
    processor = SchemaProcessor(logger=logger)

    # Example detailed_schema_info (mocked output from DBSchemaHandler)
    mock_schema_data = {
        "equipment_status": {
            "table_type": "HYPERTABLE",
            "description": "Stores historical status changes for all equipment, partitioned by time.",
            "columns": [
                {"name": "id", "type": "BIGSERIAL", "is_nullable": False, "description": "Unique identifier for the status entry", "is_pk": True, "sample_values": [101, 102, 103]},
                {"name": "equipment_id", "type": "TEXT", "is_nullable": False, "description": "Identifier for the equipment (FK to equipment table)", "is_pk": False},
                {"name": "timestamp", "type": "TIMESTAMPTZ", "is_nullable": False, "description": "Timestamp of the status event", "is_pk": False},
                {"name": "status", "type": "TEXT", "is_nullable": True, "description": "Actual status text, e.g., 'Running', 'Stopped'.", "is_pk": False, "sample_values": ['RUNNING', 'IDLE', 'FAULT']},
                {"name": "code", "type": "TEXT", "is_nullable": True, "description": "Status code associated with the status text", "is_pk": False}
            ],
            "primary_keys": ["id"],
            "foreign_keys": [
                {"column": "equipment_id", "references_table": "public.equipment", "references_column": "machine_id"}
            ],
            "timescale_dimensions": [
                {"column_name": "timestamp", "dimension_type": "time", "num_partitions": 12}
            ]
        },
        "daily_oee_summary": {
            "table_type": "CONTINUOUS AGGREGATE",
            "description": "Daily summarized OEE per equipment.",
            "columns": [
                {"name": "day", "type": "DATE", "is_nullable": False, "description": "Reporting day", "is_pk": True},
                {"name": "equipment_id", "type": "TEXT", "is_nullable": False, "description": "Equipment identifier", "is_pk": True},
                {"name": "avg_oee_percent", "type": "DOUBLE PRECISION", "is_nullable": True, "description": "Average OEE for the day", "is_pk": False}
            ],
            "primary_keys": ["day", "equipment_id"],
            "foreign_keys": [],
            "continuous_aggregate_definition": "SELECT time_bucket('1 day', timestamp) AS day, equipment_id, AVG(oee) as avg_oee_percent FROM oee_metrics GROUP BY 1, 2;"
        },
        "simple_table": {
            "table_type": "BASE TABLE",
            "description": None, # No description
            "columns": [
                 {"name": "col_a", "type": "INTEGER", "is_nullable": True, "description": None, "is_pk": False},
            ],
            "primary_keys": [],
            "foreign_keys": []
        }
    }

    chunks_with_samples = processor.create_schema_chunks(mock_schema_data, include_sample_values=True)
    print("\n--- Schema Chunks (with samples) ---")
    for i, chunk in enumerate(chunks_with_samples):
        print(f"\n--- Chunk {i+1} ---")
        print(f"Metadata: {chunk['metadata']}")
        print("Text Content:")
        print(chunk['text_content'])

    chunks_without_samples = processor.create_schema_chunks(mock_schema_data, include_sample_values=False)
    print("\n--- Schema Chunks (without samples) ---")
    for i, chunk in enumerate(chunks_without_samples):
        print(f"\n--- Chunk {i+1} ---")
        print(f"Metadata: {chunk['metadata']}")
        print("Text Content:")
        print(chunk['text_content'])

```
