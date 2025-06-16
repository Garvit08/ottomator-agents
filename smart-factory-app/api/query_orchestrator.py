# smart_factory_app/api/query_orchestrator.py

"""Handles the orchestration of agent calls for processing user queries.

This module defines the QueryOrchestrator class, which is responsible for
managing the multi-step process of interpreting a user's query, dispatching
requests to various specialized agents (SQL, Knowledge Graph, Vector Database),
and synthesizing their outputs into a coherent final response.
"""

import json
from typing import Optional, Dict, List, Any, Tuple

# These would be actual imports in a fully typed environment:
# from smart_factory_app.agents.llm_interface import LLMInterface
# from smart_factory_app.agents.kg_agent import KGAgent
# from smart_factory_app.agents.vector_agent import VectorAgent
# from collections.abc import Callable

class QueryOrchestrator:
    """Orchestrates agent calls and data flow for query processing.

    This class takes a parsed user query and manages interactions with
    SQL, Knowledge Graph (KG), and Vector Database agents to gather relevant
    information. It then uses an LLM interface to synthesize this information
    into a final answer for the user. It also collects debug information
    throughout the process.
    """

    def __init__(self, llm_interface: Any, sql_agent_func: Any, kg_agent: Any, vector_agent: Any,
                 api_forced_mock_active: bool = False):
        """Initializes the QueryOrchestrator.

        Args:
            llm_interface: An instance of a class adhering to the LLMInterface
                protocol, used for generating the final response. Requires a
                `generate_response` method.
            sql_agent_func: A callable (function) that executes natural language
                queries against a SQL database and returns results. Expected
                signature: `(natural_language_query: str, parsed_query_dict: Optional[Dict[str, Any]]) -> Tuple[str, List[str]]`.
            kg_agent: An instance of a class adhering to the KGAgent protocol,
                used for querying a Knowledge Graph. Requires a `query` method.
            vector_agent: An instance of a class adhering to the VectorAgent
                protocol, used for semantic/hybrid search. Requires a
                `hybrid_search` method.
            api_forced_mock_active: A boolean flag indicating if the API is
                operating in a forced mock state. If True, this orchestrator
                will also use mocked agent calls.
        """
        self.llm_interface = llm_interface
        self.sql_agent_func = sql_agent_func
        self.kg_agent = kg_agent
        self.vector_agent = vector_agent
        self._api_forced_mock_active = api_forced_mock_active
        self._log_message("QueryOrchestrator initialized.")

    def _log_message(self, message: str):
        """Simple internal logger for orchestrator steps."""
        print(f"[QueryOrchestrator] {message}")

    def _determine_sql_question(self, parsed_query_data: Dict[str, Any], original_query: str) -> str:
        """Determines the natural language question for the SQL agent.

        Based on the parsed intent and entities from the user's query, this
        method formulates a targeted natural language question suitable for
        the SQL agent.

        Args:
            parsed_query_data: A dictionary containing the parsed components of
                the user's query, including 'intent', 'machine_id', 'timestamp',
                'timestamp_range', and 'parameters'.
            original_query: The original raw query string from the user.

        Returns:
            A string representing the natural language question for the SQL agent.
        """
        self._log_message(f"Determining SQL question for intent: {parsed_query_data.get('intent')}")

        intent = parsed_query_data.get("intent", "unknown")
        machine_id_data = parsed_query_data.get("machine_id")
        machine_id_str = None
        if isinstance(machine_id_data, list):
            machine_id_str = ", ".join(machine_id_data) if machine_id_data else None
        elif isinstance(machine_id_data, str): # Handles cases where machine_id might not be a list yet
            machine_id_str = machine_id_data

        timestamp_info = parsed_query_data.get("timestamp") or parsed_query_data.get("timestamp_range")
        parameters = parsed_query_data.get("parameters")
        question_for_sql_agent = "N/A" # Default

        # Logic to formulate SQL questions based on intent and entities
        if intent == "analyze_downtime" and machine_id_str and timestamp_info:
            question_for_sql_agent = f"What were the alarms and operational status for machine {machine_id_str} around {timestamp_info} that might explain a stop or downtime?"
        elif intent == "fetch_oee" and machine_id_str and timestamp_info:
            question_for_sql_agent = f"What was the OEE for machine {machine_id_str} around {timestamp_info}?"
            if parameters and "oee_threshold" in parameters:
                question_for_sql_agent += f" Specifically, was it above {parameters['oee_threshold']}?"
        elif intent == "get_alarms" and machine_id_str and timestamp_info:
            question_for_sql_agent = f"List alarms for machine {machine_id_str} around {timestamp_info}."
            if parameters and "alarm_code" in parameters:
                 question_for_sql_agent += f" Filter by alarm code {parameters['alarm_code']}."
        elif intent == "get_hourly_data" and machine_id_str and timestamp_info:
            kpi = parameters.get('kpi_name', 'all relevant KPIs') if parameters else 'all relevant KPIs'
            question_for_sql_agent = f"Retrieve hourly data for machine {machine_id_str} concerning {kpi} on {timestamp_info}."
        elif intent in ["get_status", "get_equipment_details", "get_production_goals", "get_minute_data", "get_production_count", "summarize_production"]:
            question_for_sql_agent = f"Regarding user query '{original_query}', provide relevant information from SQL tables. Focus on intent '{intent}'"
            if machine_id_str: question_for_sql_agent += f", machine '{machine_id_str}'"
            if timestamp_info: question_for_sql_agent += f", around time '{timestamp_info}'"
            if parameters: question_for_sql_agent += f", with parameters: {json.dumps(parameters)}"
        else:
            # Fallback for general queries or unhandled intents
            question_for_sql_agent = f"Investigate based on user query: {original_query}. Parsed intent: {intent}, machine: {machine_id_str}, time: {timestamp_info}, params: {parameters}."

        return question_for_sql_agent

    def _call_sql_agent(self, sql_question: str, parsed_query_data: Dict[str, Any]) -> Tuple[Optional[str], Dict[str, Any], Optional[List[str]]]:
        """Calls the SQL agent and extracts key information from its response.

        Args:
            sql_question: The natural language question for the SQL agent.
            parsed_query_data: The original parsed query data, used by the
                SQL agent for potential few-shot example selection.

        Returns:
            A tuple containing:
                - Optional[str]: The textual response from the SQL agent.
                - Dict[str, Any]: Intermediate data extracted from the SQL response
                  (e.g., 'fault_code_from_sql').
                - Optional[List[str]]: Information about few-shot examples used by the SQL agent.
        """
        self._log_message(f"Calling SQL agent with question: {sql_question[:100]}...")
        sql_data_str: Optional[str]
        sql_examples_used_info: Optional[List[str]] = []
        intermediate_data: Dict[str, Any] = {}
        parameters = parsed_query_data.get("parameters")

        if self._api_forced_mock_active:
            sql_data_str = "Mock SQL: CNC-001 had alarm with fault_code = 'FC-123' yesterday (API mock)."
            if "FC-123" in sql_data_str : intermediate_data["fault_code_from_sql"] = 'FC-123'
            self._log_message(f"SQL Agent Result (mocked): {sql_data_str[:100]}...")
            return sql_data_str, intermediate_data, ["mock_sql_example_id"]

        if sql_question == "N/A": # Should ideally not be hit if _determine_sql_question has a fallback
             return "No SQL query was formulated for this request.", intermediate_data, sql_examples_used_info

        try:
            sql_data_result, sql_examples_used_info = self.sql_agent_func(
                natural_language_query=sql_question,
                parsed_query_dict=parsed_query_data
            )
            sql_data_str = str(sql_data_result) if sql_data_result else "No specific data found from SQL for this query."
            self._log_message(f"SQL Agent Result: {sql_data_str[:100]}...")
            if sql_examples_used_info:
                self._log_message(f"SQL Agent used few-shot examples: {sql_examples_used_info}")

            # Extract potential fault codes or other relevant data for downstream agents
            if "fault_code = 'FC-123'" in sql_data_str or (parameters and parameters.get("fault_code") == 'FC-123'):
                intermediate_data["fault_code_from_sql"] = 'FC-123'
            elif "alarm_code: ALM001" in sql_data_str:
                intermediate_data["fault_code_from_sql"] = 'ALM001'
        except Exception as e:
            self._log_message(f"Error calling SQL Agent: {e}")
            sql_data_str = "Error retrieving data from SQL database."

        return sql_data_str, intermediate_data, sql_examples_used_info

    def _determine_kg_query(self, parsed_query_data: Dict[str, Any], intermediate_data: Dict[str, Any]) -> Optional[Tuple[str, Dict[str, Any]]]:
        """Determines the Cypher query and parameters for the KG agent.

        This method formulates a KG query if the intent suggests root cause
        analysis or if relevant entities (like a fault code from SQL) are present.

        Args:
            parsed_query_data: The parsed components of the user's query.
            intermediate_data: Data gathered from previous agent calls (e.g., SQL agent).

        Returns:
            Optional[Tuple[str, Dict[str, Any]]]: A tuple containing the
            Cypher query string and a dictionary of parameters, or None if
            no KG query is needed.
        """
        self._log_message("Determining KG query...")
        intent = parsed_query_data.get("intent")
        machine_id_data = parsed_query_data.get("machine_id")
        machine_id = None
        if isinstance(machine_id_data, list) and machine_id_data:
            machine_id = machine_id_data[0]
        elif isinstance(machine_id_data, str):
            machine_id = machine_id_data

        parameters = parsed_query_data.get("parameters", {}) if parsed_query_data.get("parameters") else {}

        extracted_fault_code = intermediate_data.get("fault_code_from_sql")
        code_to_query = extracted_fault_code or parameters.get("fault_code")

        cypher_query_for_kg = "N/A"
        query_params_for_kg = {}

        # Logic for when to query the KG
        if intent == "find_error_cause" or code_to_query:
            if code_to_query:
                cypher_query_for_kg = "MATCH (f:Fault {code: $code})-[:CAUSED_BY|LINKED_TO_RECOMMENDATION*1..2]->(related) RETURN f.code AS fault_code, related.description AS related_info, labels(related) as related_type"
                query_params_for_kg = {'code': code_to_query}
            elif intent == "find_error_cause" and machine_id:
                cypher_query_for_kg = "MATCH (m:Machine {id: $machine_id})-[:HAD_ALARM|EXPERIENCED_STATUS*1..2]->(event)-[:ASSOCIATED_WITH|SUGGESTS_CAUSE*0..1]->(cause) RETURN event.type AS event_type, event.description AS event_desc, cause.description AS possible_cause ORDER BY event.timestamp DESC LIMIT 5"
                query_params_for_kg = {'machine_id': machine_id}

        if cypher_query_for_kg != "N/A":
            return cypher_query_for_kg, query_params_for_kg
        return None

    def _call_kg_agent(self, kg_query_parts: Optional[Tuple[str, Dict[str, Any]]]) -> Optional[str]:
        """Calls the KG agent if a query is determined to be necessary.

        Args:
            kg_query_parts: A tuple containing the Cypher query and parameters,
                            or None if no query is to be run.

        Returns:
            Optional[str]: A string representation of the KG query results
            (e.g., JSON string), or a message indicating no query was run
            or no results were found.
        """
        if not kg_query_parts:
            self._log_message("No KG query to execute.")
            return "No KG query needed or conditions not met."

        query, params = kg_query_parts
        self._log_message(f"Calling KG agent with query: {query[:50]}...")
        kg_context_str: Optional[str]

        if self._api_forced_mock_active:
            if params.get("code") == 'FC-123':
                 kg_context_str = "Mock KG: Fault FC-123 is caused by 'Sensor Malfunction' (API mock)."
            else:
                 kg_context_str = "Mock KG: No specific mock for this KG query."
            self._log_message(f"KG Agent Result (mocked): {kg_context_str[:100]}...")
            return kg_context_str

        try:
            kg_results = self.kg_agent.query(query, params=params)
            if kg_results:
                kg_context_str = f"Knowledge Graph found: {json.dumps(kg_results)}"
            else:
                kg_context_str = "No specific information found in Knowledge Graph for this query."
            self._log_message(f"KG Agent Result: {kg_context_str[:100]}...")
        except Exception as e:
            self._log_message(f"Error calling KG Agent: {e}")
            kg_context_str = "Error retrieving data from Knowledge Graph."
        return kg_context_str

    def _determine_vector_search_inputs(self, original_query: str, parsed_query_data: Dict[str, Any],
                                       intermediate_data: Dict[str, Any], sql_data_str: Optional[str],
                                       kg_context_str: Optional[str]) -> Tuple[str, List[str]]:
        """Determines the search query and keywords for the Vector DB agent.

        The search query can be augmented with context from SQL or KG results.
        Keywords are extracted from the parsed query and intermediate data.

        Args:
            original_query: The raw user query.
            parsed_query_data: Parsed components of the user's query.
            intermediate_data: Data gathered from previous agent calls.
            sql_data_str: Textual data from the SQL agent.
            kg_context_str: Textual data from the KG agent.

        Returns:
            Tuple[str, List[str]]: A tuple containing the refined search query
            string for semantic search and a list of keywords for hybrid search.
        """
        self._log_message("Determining Vector search inputs...")

        intent = parsed_query_data.get("intent", "unknown")
        machine_id_data = parsed_query_data.get("machine_id")
        parameters = parsed_query_data.get("parameters", {}) if parsed_query_data.get("parameters") else {}

        # Refine search query with context from SQL/KG
        refined_search_terms = []
        if sql_data_str and "No specific data" not in sql_data_str and "Error retrieving" not in sql_data_str and "No SQL query was formulated" not in sql_data_str:
            refined_search_terms.append(f"Context from SQL: {sql_data_str[:500]}") # Limit length of context
        if kg_context_str and "No specific information" not in kg_context_str and "Error retrieving" not in kg_context_str and "No KG query needed" not in kg_context_str:
            refined_search_terms.append(f"Context from KG: {kg_context_str[:300]}")

        search_query_for_vector_db = f"{original_query} {' '.join(refined_search_terms)}" if refined_search_terms else original_query

        # Extract keywords
        query_keywords_for_vector_db = [kw for kw in intent.split('_') if kw not in ["get", "fetch", "find"]] # From intent

        # Add machine IDs to keywords
        if isinstance(machine_id_data, list):
            query_keywords_for_vector_db.extend(m_id for m_id in machine_id_data if m_id)
        elif isinstance(machine_id_data, str):
            query_keywords_for_vector_db.append(machine_id_data)

        # Add string parameters and specific important keys to keywords
        if parameters:
            for k,v in parameters.items():
                if isinstance(v, str): query_keywords_for_vector_db.append(v)
                if k in ["fault_code", "alarm_code", "kpi_name", "sensor_id"] and isinstance(v, str):
                    query_keywords_for_vector_db.append(v)

        # Add fault code from SQL if present
        if intermediate_data.get("fault_code_from_sql"):
            query_keywords_for_vector_db.append(intermediate_data["fault_code_from_sql"])

        # Filter and unique keywords
        query_keywords_for_vector_db = list(set(kw for kw in query_keywords_for_vector_db if kw and len(kw)>1))

        return search_query_for_vector_db, query_keywords_for_vector_db

    def _call_vector_agent(self, search_query: str, keywords: List[str]) -> List[str]:
        """Calls the Vector DB agent using hybrid search.

        Args:
            search_query: The (potentially refined) query string for semantic search.
            keywords: A list of keywords for the keyword component of hybrid search.

        Returns:
            List[str]: A list of document strings retrieved from the vector database,
            or messages indicating errors or no results.
        """
        self._log_message(f"Calling Vector agent with query: {search_query[:100]}..., Keywords: {keywords}")
        vector_results_docs: List[str]

        if self._api_forced_mock_active:
            vector_results_docs = ["Mock Vector DB: Found past issue log for FC-123 on CNC-001 (API mock)."]
            self._log_message(f"Vector Agent Result (mocked): Found {len(vector_results_docs)} documents.")
            return vector_results_docs

        try:
            vector_search_results = self.vector_agent.hybrid_search(
                query_text=search_query,
                keywords=keywords,
                n_results=3 # Default number of results
            )
            # Assuming hybrid_search returns a dict like: {"documents": [["doc1_text", "doc2_text"]], ...}
            # And we need the first list of document texts.
            if vector_search_results and vector_search_results.get("documents") and \
               isinstance(vector_search_results["documents"], list) and \
               len(vector_search_results["documents"]) > 0 and \
               isinstance(vector_search_results["documents"][0], list):
                vector_results_docs = vector_search_results["documents"][0]
            elif vector_search_results and vector_search_results.get("documents") and \
                 isinstance(vector_search_results["documents"], list) and \
                 all(isinstance(doc, str) for doc in vector_search_results["documents"]):
                 # Handle if "documents" is already a List[str]
                 vector_results_docs = vector_search_results["documents"]
            else: # Default if structure is unexpected or no documents
                vector_results_docs = []


            if vector_results_docs:
                self._log_message(f"Vector Agent found {len(vector_results_docs)} documents.")
            else:
                vector_results_docs = ["No relevant documents found in vector database for the refined query."]
                self._log_message("No documents found by Vector Agent with refined query.")
        except Exception as e:
            self._log_message(f"Error calling Vector Agent: {e}")
            vector_results_docs = ["Error retrieving documents from vector database."]
        return vector_results_docs

    def process_query_flow(self, parsed_query_data: Dict[str, Any], original_query: str,
                           chat_history: str) -> Tuple[str, Dict[str, Any]]:
        """Orchestrates the multi-agent query processing flow.

        This method sequentially determines questions for, calls, and processes
        results from the SQL, KG, and Vector agents. Finally, it uses the
        LLM interface to synthesize a response from the gathered context.

        Args:
            parsed_query_data: The structured output from the initial
                `llm_interface.parse_query` call.
            original_query: The original raw user query string.
            chat_history: The stringified conversation history.

        Returns:
            A tuple containing:
                - str: The final synthesized answer from the LLM.
                - Dict[str, Any]: A dictionary containing all intermediate data,
                  queries sent to agents, and responses received, for debugging.
        """
        self._log_message(f"Starting query processing flow for: {original_query[:50]}...")

        collected_debug_info: Dict[str, Any] = {
            "original_query": original_query,
            "parsed_intent_data": parsed_query_data, # From llm_interface.parse_query()
            "chat_history_provided_to_llm_parse": chat_history[:1000] + "..." if len(chat_history) > 1000 else chat_history,
            "question_to_sql_agent": "N/A",
            "sql_agent_few_shot_examples_used": [],
            "sql_agent_response_snippet": "N/A",
            "fault_code_from_sql_for_kg": "N/A",
            "cypher_query_to_kg_agent": "N/A",
            "params_for_kg_agent": {},
            "kg_agent_response_snippet": "N/A",
            "refined_query_to_vector_agent": "N/A",
            "keywords_for_vector_agent": [],
            "vector_agent_response_docs": [],
        }

        # Step 1: SQL Agent
        sql_question = self._determine_sql_question(parsed_query_data, original_query)
        collected_debug_info["question_to_sql_agent"] = sql_question

        sql_data_str, intermediate_sql_data, sql_examples_used = self._call_sql_agent(sql_question, parsed_query_data)
        collected_debug_info["sql_agent_response_snippet"] = sql_data_str[:1000] + "..." if sql_data_str and len(sql_data_str) > 1000 else sql_data_str
        if sql_examples_used:
            collected_debug_info["sql_agent_few_shot_examples_used"] = sql_examples_used
        # Ensure fault_code_from_sql is correctly captured for KG agent
        if intermediate_sql_data.get("fault_code_from_sql"):
            collected_debug_info["fault_code_from_sql_for_kg"] = intermediate_sql_data["fault_code_from_sql"]

        # Step 2: KG Agent
        # Pass intermediate_sql_data which might contain 'fault_code_from_sql'
        kg_query_tuple = self._determine_kg_query(parsed_query_data, intermediate_sql_data)
        if kg_query_tuple:
            collected_debug_info["cypher_query_to_kg_agent"] = kg_query_tuple[0]
            collected_debug_info["params_for_kg_agent"] = kg_query_tuple[1]

        kg_context_str = self._call_kg_agent(kg_query_tuple)
        collected_debug_info["kg_agent_response_snippet"] = kg_context_str[:1000] + "..." if kg_context_str and len(kg_context_str) > 1000 else kg_context_str

        # Step 3: Vector Agent
        # Pass intermediate_sql_data for keyword extraction
        vector_query, vector_keywords = self._determine_vector_search_inputs(
            original_query, parsed_query_data, intermediate_sql_data,
            sql_data_str, kg_context_str
        )
        collected_debug_info["refined_query_to_vector_agent"] = vector_query[:500] + "..." if len(vector_query) > 500 else vector_query
        collected_debug_info["keywords_for_vector_agent"] = vector_keywords

        vector_docs = self._call_vector_agent(vector_query, vector_keywords)
        collected_debug_info["vector_agent_response_docs"] = vector_docs

        # Step 4: Generate Final Response using the LLM interface
        self._log_message("Generating final response using provided llm_interface...")
        final_response_text = self.llm_interface.generate_response(
            sql_data=sql_data_str,
            kg_context=kg_context_str,
            vector_context=vector_docs,
            user_query=original_query,
            chat_history=chat_history
        )

        self._log_message("Query processing flow complete.")
        return final_response_text, collected_debug_info
