# smart-factory-app/agents/sql_agent_utils.py
import os
import sys
import json
from typing import List, Dict, Set, Any

# Ensure sql_query_examples can be imported.
# If this script is run directly, this path adjustment might be needed.
# When imported by another module (e.g., sql_agent.py), Python's import system should handle it.
current_dir = os.path.dirname(os.path.abspath(__file__))
# If sql_agent_utils.py is in smart-factory-app/agents/
# and sql_query_examples.py is also in smart-factory-app/agents/
# then direct relative import `from .sql_query_examples import SQL_QUERY_EXAMPLES` should work.
# If running this script directly, sys.path might need parent of smart-factory-app.
project_root = os.path.abspath(os.path.join(current_dir, '..', '..')) # Parent of smart-factory-app
if project_root not in sys.path:
    sys.path.insert(0, project_root) # Allows `from smart_factory_app.agents...`

try:
    from smart_factory_app.agents.sql_query_examples import SQL_QUERY_EXAMPLES
except ImportError:
    # Fallback for direct execution if the above path adjustment isn't enough
    # or if the package structure isn't perfectly recognized.
    if os.path.basename(os.getcwd()) == 'agents': # If CWD is agents directory
         from sql_query_examples import SQL_QUERY_EXAMPLES
    else: # Try one level up if CWD is smart-factory-app
         from agents.sql_query_examples import SQL_QUERY_EXAMPLES


def _extract_keywords_from_parsed_query(parsed_query: Dict[str, Any]) -> Set[str]:
    """
    Extracts keywords from the parsed query dictionary.
    Keywords are taken from intent (split by '_') and string values in parameters.
    All keywords are lowercased.
    """
    keywords: Set[str] = set()

    intent = parsed_query.get("intent")
    if intent and isinstance(intent, str):
        keywords.update(intent.lower().split('_'))

    parameters = parsed_query.get("parameters")
    if isinstance(parameters, dict):
        for value in parameters.values():
            if isinstance(value, str):
                # Split string parameter values into words if they seem like phrases,
                # or add them as is if they are specific codes/IDs.
                # For simplicity, let's add the value directly and also split it if it contains spaces.
                keywords.add(value.lower())
                keywords.update(value.lower().split()) 
            elif isinstance(value, list): # If a parameter value is a list of strings
                for item in value:
                    if isinstance(item, str):
                        keywords.add(item.lower())
                        keywords.update(item.lower().split())


    # Add machine_id if present
    machine_id = parsed_query.get("machine_id")
    if isinstance(machine_id, str):
        keywords.add(machine_id.lower())
    elif isinstance(machine_id, list): # If machine_id can be a list
        for mid in machine_id:
            if isinstance(mid, str):
                keywords.add(mid.lower())
                
    # Remove generic words or very short words if necessary (optional refinement)
    # keywords = {kw for kw in keywords if len(kw) > 2} 
    
    return keywords


def get_relevant_sql_examples(parsed_query: Dict[str, Any], max_examples: int = 2) -> List[Dict[str, Any]]:
    """
    Selects relevant SQL query examples based on the parsed user query.

    Args:
        parsed_query: The dictionary output from llm_interface.parse_query.
        max_examples: The maximum number of relevant examples to return.

    Returns:
        A list of dictionaries, where each dictionary is a relevant example
        from SQL_QUERY_EXAMPLES.
    """
    if not SQL_QUERY_EXAMPLES:
        return []

    scored_examples = []
    query_keywords = _extract_keywords_from_parsed_query(parsed_query)
    parsed_intent_lower = parsed_query.get("intent", "").lower()

    for example in SQL_QUERY_EXAMPLES:
        score = 0
        example_keywords_lower = {kw.lower() for kw in example.get("keywords", [])}
        example_desc_lower = example.get("description", "").lower()
        example_params_lower = {p.lower() for p in example.get("parameters", [])}

        # 1. Intent Match
        if parsed_intent_lower and example.get("expected_intent", "").lower() == parsed_intent_lower:
            score += 3

        # 2. Keyword Match
        for kw in query_keywords:
            if kw in example_keywords_lower:
                score += 1
            # Check if keyword is a substring in description for broader matching
            if kw in example_desc_lower: # kw is already lowercased
                score += 1
        
        # Bonus for direct keyword overlap if intent is less specific
        if parsed_intent_lower == "general_query" or not parsed_intent_lower:
            common_kws = len(query_keywords.intersection(example_keywords_lower))
            score += common_kws * 0.5


        # 3. Parameter Overlap
        # Consider parameters from top-level of parsed_query and within its 'parameters' dict
        available_query_params = set()
        if parsed_query.get("machine_id"): available_query_params.add("machine_id")
        if parsed_query.get("timestamp") or parsed_query.get("timestamp_range"):
            available_query_params.add("start_date") # Approximate match
            available_query_params.add("end_date")   # Approximate match
            available_query_params.add("current_date_time") # Approximate
            available_query_params.add("zoned_current_time") # Approximate
            # If timestamp is specific like 'yesterday', it implies date params
        
        if isinstance(parsed_query.get("parameters"), dict):
            for p_key in parsed_query["parameters"].keys():
                available_query_params.add(p_key.lower())
        
        # Specific check for dynamic table/time column names often passed in parameters
        # These are important for selecting the right template variants.
        dynamic_template_params = {"table_name", "aggregated_table_name", "time_column"}
        
        for example_param_key_lower in example_params_lower:
            if example_param_key_lower in available_query_params:
                score += 0.5
                if example_param_key_lower in dynamic_template_params: # Boost if dynamic param matches
                    score += 0.5 # Extra boost for matching dynamic placeholders

        if score > 0:
            scored_examples.append({"example": example, "score": score})

    # Sort examples by score in descending order
    scored_examples.sort(key=lambda x: x["score"], reverse=True)

    # Return the example dictionaries themselves, not the scores
    relevant_examples_dicts = [item["example"] for item in scored_examples[:max_examples]]
    
    # Extract unique table names from the selected examples
    suggested_tables: Set[str] = set()
    for item in relevant_examples_dicts:
        tables = item.get("tables_involved", [])
        if isinstance(tables, list):
            suggested_tables.update(tables)
            
    return relevant_examples_dicts, suggested_tables


if __name__ == "__main__":
    print(f"Total SQL examples available: {len(SQL_QUERY_EXAMPLES)}")

    parsed_query_1 = {
        "intent": "get_daily_summary", 
        "machine_id": "CNC-001", 
        "timestamp": "yesterday", 
        "parameters": {"shift_id": "SHIFT_A", "report_type": "daily", "equipment_id": "CNC-001", "start_date": "2023-01-10", "end_date": "2023-01-10"}
    }
    parsed_query_2 = {
        "intent": "get_machine_speed", 
        "machine_id": "PRESS-002", 
        "timestamp": "now", # Implies current_date_time or zoned_current_time
        "parameters": {"equipment_id": "PRESS-002", "start_date": "2023-01-11", "zoned_current_time": "2023-01-11T10:00:00Z"}
    }
    parsed_query_3 = {
        "intent": "calculate_oee", # slightly different from example's "calculate_oee_components"
        "machine_id": "WELDER-001", 
        "timestamp_range": {"start": "2024-07-01", "end": "2024-07-01"}, 
        "parameters": {
            "AGGREGATED_TABLE_NAME": "equipment_data_daily", 
            "time_column": "date",
            "target_kpi": "OEE",
            "equipment_id": "WELDER-001",
            "start_date": "2024-07-01", 
            "end_date": "2024-07-01",
            "shift_id": "ANY"
        }
    }
    parsed_query_4 = { # More generic, testing keyword matches
        "intent": "general_query",
        "machine_id": "CNC-001",
        "timestamp": "last 24 hours",
        "parameters": {"status": "running", "part_count_threshold": 100}
    }


    print("\n--- Testing with parsed_query_1 (Daily Summary) ---")
    relevant_1_examples, tables_1 = get_relevant_sql_examples(parsed_query_1, max_examples=2)
    print(f"  Suggested Tables: {tables_1}")
    for ex in relevant_1_examples:
        print(f"    Selected Example ID: {ex['id']} (Name: {ex['name']})")

    print("\n--- Testing with parsed_query_2 (Machine Speed) ---")
    relevant_2_examples, tables_2 = get_relevant_sql_examples(parsed_query_2, max_examples=2)
    print(f"  Suggested Tables: {tables_2}")
    for ex in relevant_2_examples:
        print(f"    Selected Example ID: {ex['id']} (Name: {ex['name']})")

    print("\n--- Testing with parsed_query_3 (OEE Calculation) ---")
    relevant_3_examples, tables_3 = get_relevant_sql_examples(parsed_query_3, max_examples=2)
    print(f"  Suggested Tables: {tables_3}")
    for ex in relevant_3_examples:
        print(f"    Selected Example ID: {ex['id']} (Name: {ex['name']})")
        
    print("\n--- Testing with parsed_query_4 (General Query, keywords: status, part_count) ---")
    relevant_4_examples, tables_4 = get_relevant_sql_examples(parsed_query_4, max_examples=3)
    print(f"  Suggested Tables: {tables_4}")
    for ex in relevant_4_examples:
        print(f"    Selected Example ID: {ex['id']} (Name: {ex['name']})")

    # Test _extract_keywords_from_parsed_query
    print("\n--- Testing _extract_keywords_from_parsed_query ---")
    extracted_kws_1 = _extract_keywords_from_parsed_query(parsed_query_1)
    print(f"Keywords from parsed_query_1: {extracted_kws_1}")
    # Expected: {'get', 'daily', 'summary', 'cnc-001', 'shift_a', 'daily', ...}
    
    extracted_kws_3 = _extract_keywords_from_parsed_query(parsed_query_3)
    print(f"Keywords from parsed_query_3: {extracted_kws_3}")
    # Expected: {'calculate', 'oee', 'welder-001', 'equipment_data_daily', 'date', 'target_kpi', ...}

    extracted_kws_4 = _extract_keywords_from_parsed_query(parsed_query_4)
    print(f"Keywords from parsed_query_4: {extracted_kws_4}")
    # Expected: {'general', 'query', 'cnc-001', 'running', '100', 'part_count_threshold', 'status'}

    # Test case where parameters might have a list
    parsed_query_5_list_params = {
        "intent": "compare_oee",
        "machine_id": None,
        "parameters": {"comparison_items": ["CNC-001", "CNC-002"], "kpi_name": "OEE"}
    }
    extracted_kws_5 = _extract_keywords_from_parsed_query(parsed_query_5_list_params)
    print(f"Keywords from parsed_query_5_list_params: {extracted_kws_5}")
    # Expected: {'compare', 'oee', 'cnc-001', 'cnc-002', 'oee', 'kpi_name', 'comparison_items'}
    # Note: "oee" might appear twice before set conversion. "comparison_items" is not a string value, so not extracted by current logic.
    # Let's refine _extract_keywords_from_parsed_query to handle list of strings in parameters.
    # (The code was already updated during implementation to handle list of strings)
    # So, 'cnc-001', 'cnc-002' should be there. 'comparison_items' (the key) won't be extracted.

    # Example from prompt:
    # User Query: "Compare the daily OEE for 'CNC-001' and 'CNC-002' last week."
    # JSON Output:
    # {{
    #     "intent": "compare_daily_oee",
    #     "machine_id": null, 
    #     "timestamp_range": {{
    #         "start": "start of last week",
    #         "end": "end of last week"
    #     }},
    #     "parameters": {{
    #         "comparison_items": ["CNC-001", "CNC-002"],
    #         "kpi_name": "OEE"
    #     }}
    # }}
    # Keywords should include: 'compare', 'daily', 'oee', 'cnc-001', 'cnc-002', 'oee', 'kpi_name' (from param value)
    # The key 'comparison_items' is not extracted, only its string values. 'kpi_name' is a value here.
    # The intent 'compare_daily_oee' gets split.
    # `machine_id` is null, so not added.
    
    # Test with an example that should match "machine_goal_capacity"
    parsed_query_goal = {
        "intent": "get_machine_goal",
        "machine_id": "EQP-005",
        "timestamp_range": {"start": "2024-01-01", "end": "2024-01-01"},
        "parameters": {
            "equipment_id": "EQP-005",
            "product_id": "PROD_X",
            "facility_id": "FAC_1",
            "shift_id": "S1",
            "start_date": "2024-01-01", "end_date": "2024-01-01",
            "table_name": "equipment_data_daily" # This is crucial for matching
        }
    }
    print("\n--- Testing with parsed_query_goal (Machine Goal) ---")
    relevant_goal_examples, tables_goal = get_relevant_sql_examples(parsed_query_goal, max_examples=2)
    print(f"  Suggested Tables: {tables_goal}")
    for ex in relevant_goal_examples:
        print(f"    Selected Example ID: {ex['id']} (Name: {ex['name']})")
        # self.assertTrue(any(p_name == "table_name" for p_name in ex['parameters']), # Requires unittest context
        #                 f"Example {ex['id']} should have 'table_name' if it's dynamic.")
        if ex['id'] == 'machine_goal_capacity':
            print(f"      Correctly matched 'machine_goal_capacity' for parsed_query_goal")
            
    # Test with a query that might match 'machine_last_running_status'
    parsed_query_status = {
        "intent": "get_last_running_status",
        "machine_id": "EQP-007",
        "timestamp": "now", # implies current_date_time
        "parameters": {"equipment_id": "EQP-007", "current_date_time": "2024-01-11T12:00:00Z"}
    }
    print("\n--- Testing with parsed_query_status (Machine Status) ---")
    relevant_status_examples, tables_status = get_relevant_sql_examples(parsed_query_status, max_examples=2)
    print(f"  Suggested Tables: {tables_status}")
    for ex in relevant_status_examples:
        print(f"    Selected Example ID: {ex['id']} (Name: {ex['name']})")
        if ex['id'] == 'machine_last_running_status':
             print(f"      Correctly matched 'machine_last_running_status' for parsed_query_status")
             
    # A query that might not have a strong intent match but keyword matches
    parsed_query_keywords_only = {
        "intent": "general_factory_overview", # No direct intent match in examples
        "machine_id": "EQP-001",
        "parameters": {"shift_id": "S1", "focus": "downtime report"} # 'downtime' and 'report' are keywords
    }
    print("\n--- Testing with parsed_query_keywords_only (General, focus on downtime report) ---")
    relevant_keywords_only_examples, tables_keywords_only = get_relevant_sql_examples(parsed_query_keywords_only, max_examples=2)
    print(f"  Suggested Tables: {tables_keywords_only}")
    for ex in relevant_keywords_only_examples:
        print(f"    Selected Example ID: {ex['id']} (Name: {ex['name']})")
        # Expecting 'daily_summary_report' due to "downtime" and "report" keywords.
