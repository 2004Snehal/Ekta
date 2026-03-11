"""
Hybrid Database Metadata Agent using LangGraph.

This module implements an intelligent routing agent that classifies user queries
into "general" (non-database) or "database" (schema-related) categories.

- General queries are routed directly to a response generator.
- Database queries are routed through a keyword-based schema search node
  before generating context-aware responses.

Architecture:
  StateGraph: AgentState (messages, intent, retrieved_schema)
  Nodes: Router -> [Keyword Search] -> Response Generator
  Edges: Conditional routing based on intent classification.

LLM: Local Ollama instance (configurable via .env)
Schema: Mocked Python dictionary (no Vector DB, no embeddings)
Matching: Keyword-based substring/tokenization search
"""

import os
import json
from typing import Any, TypedDict, Annotated, Sequence
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, AIMessage
from langchain_core.language_models import BaseLanguageModel
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_community.llms import Ollama


# ============================================================================
# 1. CONFIGURATION & SETUP
# ============================================================================

load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gpt-oss:20b")

# Initialize the local LLM
llm: BaseLanguageModel = Ollama(
    base_url=OLLAMA_BASE_URL,
    model=OLLAMA_MODEL,
    temperature=0.7,
)

print(f"[INFO] Using Ollama model: {OLLAMA_MODEL} at {OLLAMA_BASE_URL}")


# ============================================================================
# 1.5 LOAD SCHEMA JSON
# ============================================================================

def load_schema_from_json(filepath: str = "schema.json") -> dict[str, Any]:
    """
    Load database schema from JSON file.
    
    Args:
        filepath: Path to schema.json file (relative or absolute).
    
    Returns:
        Parsed schema dictionary.
    """
    try:
        # Try absolute path first
        if os.path.isabs(filepath):
            with open(filepath, 'r') as f:
                return json.load(f)
        # Try relative to script directory
        script_dir = os.path.dirname(os.path.abspath(__file__))
        schema_path = os.path.join(script_dir, filepath)
        with open(schema_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"[WARNING] Schema file not found at {filepath}. Using mock schema.")
        return {"tables": {}}
    except json.JSONDecodeError as e:
        print(f"[WARNING] Invalid JSON in schema file: {e}. Using mock schema.")
        return {"tables": {}}


# Load the FRAMMER schema
FRAMMER_SCHEMA = load_schema_from_json("schema.json")
print(f"[INFO] Loaded schema with {len(FRAMMER_SCHEMA.get('tables', {}))} tables")


# ============================================================================
# 2. PYDANTIC MODELS FOR STRUCTURED OUTPUT
# ============================================================================

class RouterOutput(BaseModel):
    """Structured output from the Router node for intent classification."""

    intent: str = Field(
        ...,
        description="The classified intent: 'general' (non-database questions) or 'database' (schema/metadata questions)",
        enum=["general", "database"],
    )
    reasoning: str = Field(
        ...,
        description="Brief explanation of why this intent was chosen",
    )
class queryNodeOutput(BaseModel):
    """Structured output from the Keyword Search node."""
    query: str = Field(
        ...,
        description="the sql query to be executed on the database"
    )
class SchemaSearchResult(BaseModel):
    """Result structure from keyword schema search."""

    matched_tables: list[str] = Field(
        default_factory=list, description="List of matched table names"
    )
    matched_columns: list[str] = Field(
        default_factory=list, description="List of matched column descriptions"
    )


class ResponseOutput(BaseModel):
    """Structured output for the response generator node."""

    response: str = Field(
        ...,
        description="The final response to the user's query",
    )
    confidence: float = Field(
        default=0.95,
        description="Confidence level of the response (0.0 to 1.0)",
    )


# ============================================================================
# 3. SCHEMA REFERENCE (loaded from schema.json)
# ============================================================================
# FRAMMER_SCHEMA is loaded above in section 1.5


# ============================================================================
# 4. UTILITY FUNCTIONS
# ============================================================================

def format_schema_context(matched_tables: list[str], matched_columns: list[str]) -> str:
    """
    Format matched schema information into a readable context string.

    Args:
        matched_tables: List of table names.
        matched_columns: List of column descriptions.

    Returns:
        Formatted schema context string for LLM consumption.
    """
    context = ""
    schema_tables = FRAMMER_SCHEMA.get("tables", {})

    if matched_tables:
        context += "Matched Tables:\n"
        for table in matched_tables:
            if table not in schema_tables:
                continue
            table_info = schema_tables[table]
            context += f"\n  Table: {table}\n"
            context += f"  Type: {table_info.get('type', 'unknown')}\n"
            context += f"  Description: {table_info.get('description', 'N/A')}\n"
            context += f"  Grain: {table_info.get('grain', 'N/A')}\n"
            context += f"  Columns:\n"
            for col_name, col_info in table_info.get("columns", {}).items():
                col_type = col_info.get('type', 'unknown')
                col_desc = col_info.get('description', '')
                context += f"    - {col_name} ({col_type}): {col_desc}\n"

    if matched_columns:
        context += "\n\nAdditional Matched Columns:\n"
        for col_desc in matched_columns:
            context += f"  - {col_desc}\n"

    return context if context else "No relevant schema found for your query."


# ============================================================================
# 5. STATE DEFINITION
# ============================================================================


class AgentState(TypedDict):
    """
    State representation for the LangGraph agent.

    Attributes:
        messages: Conversation history (uses add_messages reducer for proper sequencing).
        intent: Routing decision ('general' or 'database').
        retrieved_schema: List of matched schema context strings.
    """
    user_query: str
    messages: Annotated[Sequence[BaseMessage], add_messages]
    intent: str
    output_str: str
    query_str: str
    png_path: str

# ============================================================================
# 6. NODE IMPLEMENTATIONS
# ============================================================================


def router_node(state: AgentState) -> dict[str, Any]:
    """
    Router node: Classifies user intent using an LLM with structured output.

    Uses PydanticOutputParser to extract intent from RouterOutput model.
    Classifies queries into 'general' (non-database) or 'database' (schema/metadata) categories.

    Args:
        state: Current agent state.

    Returns:
        Updated state dict with 'intent' set based on LLM classification.
    """
    # Create output parser for RouterOutput model
    parser = PydanticOutputParser(pydantic_object=RouterOutput)
    
    # Get format instructions from parser
    format_instructions = parser.get_format_instructions()
    
    # Create prompt template with format instructions
    prompt_template_str = """You are an intelligent query router for a database assistant.

Your task is to classify user queries into ONE of these categories:

1. "general": General-purpose questions that don't require database schema knowledge.
   Examples: "Hello", "What is a primary key?", "How do databases work?", "Tell me a joke"

2. "database": Specific database schema or structural questions requiring knowledge of table/column structure.
   Examples: "Which columns relate to user revenue?", "How is the orders table linked to customers?", "Show me the users table schema"

Analyze the LATEST user message and classify it.

{format_instructions}

Query: {query}"""

    # Get the latest user query
    latest_message = state["messages"][-1]
    user_query = (
        latest_message.content
        if isinstance(latest_message, HumanMessage)
        else str(latest_message)
    )

    try:
        # Create the prompt with format instructions
        prompt = PromptTemplate(
            template=prompt_template_str,
            input_variables=["query"],
            partial_variables={"format_instructions": format_instructions},
        )

        # Chain: prompt -> LLM -> parser
        chain = prompt | llm | parser

        # Invoke the chain to get structured output
        parsed_output: RouterOutput = chain.invoke({"query": user_query})
        intent = parsed_output.intent.lower()

        print(f"[ROUTER] Reasoning: {parsed_output.reasoning}")
        print(f"[ROUTER] Classified intent: {intent}")
        return {
            "intent": intent,
            "messages": state["messages"],
            "retrieved_schema": state.get("retrieved_schema", []),
        }

    except Exception as e:
        print(f"[ERROR] Router node failed: {e}")
        # Fallback to general intent on error
        return {
            "intent": "general",
            "messages": state["messages"],
            "retrieved_schema": state.get("retrieved_schema", []),
        }


def query_node(state: AgentState) -> dict[str, Any]:
   
    # Get the latest user message
    latest_message = state["messages"][-1]
    user_query = (
        latest_message.content
        if isinstance(latest_message, HumanMessage)
        else str(latest_message)
    )
    parser=PydanticOutputParser(pydantic_object=queryNodeOutput)
    format_instructions=parser.get_format_instructions()
    
    prompt_template_str="""You are a helpful assistant that generates SQL queries based on user questions about a database schema.
Use the following format instructions to generate a SQL query that retrieves relevant data from the database based on the user's question.

Schema:
{schema}

Format Instructions:
{format_instructions}

User Question: {question}"""
    
    prompt=PromptTemplate(
        template=prompt_template_str,
        input_variables=["question"],
        partial_variables={
            "schema": json.dumps(FRAMMER_SCHEMA, indent=2),
            "format_instructions": format_instructions
        },
    )
    try:
        # Chain: prompt -> LLM -> parser
        chain = prompt | llm | parser

        # Invoke the chain to get structured output
        parsed_output: queryNodeOutput = chain.invoke({"question": user_query})
        query_str = parsed_output.query
        print(f"[QUERY NODE] Generated SQL Query: {query_str}")
        return {
            "user_query": state.get("user_query", ""),
            "messages": state["messages"],
            "intent": state.get("intent", "general"),
            "output_str": "",
            "query_str": query_str,
            "png_path": "",
        }
    except Exception as e:
        print(f"[ERROR] Query node failed: {e}")
    
    return {
        "user_query": state.get("user_query", ""),
        "messages": state["messages"],
        "intent": state.get("intent", "general"),
        "output_str": "",
        "query_str": "",
        "png_path": "",
    }


def response_generator_node(state: AgentState) -> dict[str, Any]:
    """
    Response Generator node: Generates the final LLM response with structured output.

    Uses PydanticOutputParser to extract response from ResponseOutput model.
    Constructs a context-aware prompt based on the intent and retrieved schema.

    Args:
        state: Current agent state.

    Returns:
        Updated state dict with the generated response added to messages.
    """
    intent = state.get("intent", "general")
    retrieved_schema = state.get("retrieved_schema", [])
    
    # Create output parser for ResponseOutput model
    parser = PydanticOutputParser(pydantic_object=ResponseOutput)
    format_instructions = parser.get_format_instructions()

    # Build base prompt based on intent
    if intent == "database":
        base_prompt = """You are a helpful database assistant for the FRAMMER AI Analytics Platform.

A user is asking about database schema, table structure, or relationships.

Use the provided schema context to answer their question accurately.
If the schema doesn't contain relevant information, acknowledge the limitation
and suggest what information might be needed.

Be concise and technical."""

        # Append schema context if available
        if retrieved_schema and retrieved_schema[0]:
            base_prompt += f"\n\n=== SCHEMA CONTEXT ===\n{retrieved_schema[0]}\n=== END SCHEMA ==="
    else:
        base_prompt = """You are a helpful, friendly general-purpose assistant.

Answer the user's question clearly and concisely.
If they ask about database-specific topics, provide general explanations."""

    # Create prompt template with format instructions
    prompt_template_str = f"""{base_prompt}

{{format_instructions}}

User Question: {{question}}"""

    try:
        # Get the latest user query
        latest_message = state["messages"][-1]
        user_query = (
            latest_message.content
            if isinstance(latest_message, HumanMessage)
            else str(latest_message)
        )

        # Create the prompt
        prompt = PromptTemplate(
            template=prompt_template_str,
            input_variables=["question"],
            partial_variables={"format_instructions": format_instructions},
        )

        # Chain: prompt -> LLM -> parser
        chain = prompt | llm | parser

        # Invoke the chain to get structured output
        parsed_output: ResponseOutput = chain.invoke({"question": user_query})
        response_text = parsed_output.response
        confidence = parsed_output.confidence

        # Add response to conversation history
        ai_response = AIMessage(
            content=response_text,
            metadata={"confidence": confidence, "intent": intent}
        )
        updated_messages = list(state["messages"]) + [ai_response]

        return {
            "intent": intent,
            "messages": updated_messages,
            "retrieved_schema": retrieved_schema,
        }

    except Exception as e:
        print(f"[ERROR] Response generator node failed: {e}")
        fallback_response = AIMessage(
            content=f"I encountered an error processing your request: {str(e)}"
        )
        updated_messages = list(state["messages"]) + [fallback_response]
        return {
            "intent": intent,
            "messages": updated_messages,
            "retrieved_schema": retrieved_schema,
        }


# ============================================================================
# 7. GRAPH CONSTRUCTION
# ============================================================================


def build_agent_graph() -> Any:
    """
    Constructs and compiles the LangGraph state graph.

    Flow:
      START -> Router Node
      Router Node -> (conditional)
        - If intent == 'database': -> Keyword Search Node -> Response Generator -> END
        - If intent == 'general': -> Response Generator -> END

    Returns:
        The compiled graph ready for invocation.
    """
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("router", router_node)
    workflow.add_node("keyword_schema_search", query_node)
    workflow.add_node("response_generator", response_generator_node)

    # Entry point
    workflow.add_edge(START, "router")

    # Conditional edge from router
    def route_based_intent(state: AgentState) -> str:
        """Determine next node based on intent."""
        intent = state.get("intent", "general")
        return "keyword_schema_search" if intent == "database" else "response_generator"

    workflow.add_conditional_edges("router", route_based_intent)

    # Edges from schema search
    workflow.add_edge("keyword_schema_search", "response_generator")

    # Exit point
    workflow.add_edge("response_generator", END)

    # Compile the graph
    graph = workflow.compile()
    return graph


# ============================================================================
# 8. TEST & EXECUTION
# ============================================================================


def run_agent(graph: Any, user_query: str) -> None:
    """
    Executes the agent graph with a user query and prints the results.

    Args:
        graph: The compiled LangGraph graph.
        user_query: The user's input query string.
    """
    print("\n" + "=" * 80)
    print(f"USER QUERY: {user_query}")
    print("=" * 80)

    # Initialize state
    initial_state = {
        "user_query": user_query,
        "messages": [HumanMessage(content=user_query)],
        "intent": "",
        "output_str": "",
        "query_str": "",
        "png_path": "",
    }

    try:
        # Invoke the graph
        result = graph.invoke(initial_state)

        # Extract and display results
        intent = result.get("intent", "unknown")
        retrieved_schema = result.get("retrieved_schema", [])
        messages = result.get("messages", [])

        print(f"\n[ROUTING DECISION] Intent: {intent}")

        if retrieved_schema and intent == "database":
            print(f"\n[SCHEMA RETRIEVAL] Matched schema:\n{retrieved_schema[0]}")

        # Get the last message (the response)
        if messages:
            last_message = messages[-1]
            if isinstance(last_message, AIMessage):
                print(f"\n[RESPONSE]:\n{last_message.content}")
            else:
                print(f"\n[RESPONSE]:\n{str(last_message)}")

    except Exception as e:
        print(f"\n[ERROR] Graph execution failed: {e}")


def main() -> None:
    """
    Main entry point: Build the graph and run test queries demonstrating
    both 'general' and 'database' routing paths.
    """
    print("\n[STARTING] Hybrid Database Metadata Agent")
    print(f"[CONFIG] LLM Model: {OLLAMA_MODEL}")
    print(f"[CONFIG] Ollama Base URL: {OLLAMA_BASE_URL}")
    print(f"[CONFIG] Schema Database: {FRAMMER_SCHEMA.get('database', 'unknown')}")

    # Build the graph
    graph = build_agent_graph()
    print("\n[GRAPH] Compiled successfully\n")

    # Test queries for FRAMMER Analytics Platform
    test_queries = [
        # General queries (should route to 'general')
        # "Hello! How are you today?",
        # "What is a data warehouse?",
        # # Database queries (should route to 'database')
        # "Which tables store video information?",
        # "How are videos linked to outputs?",
        "What columns track publishing metrics?",
        # "Tell me about user channels and teams",
        # "Show me the client dimension structure",
    ]

    print("\n" + "#" * 80)
    print("# RUNNING TEST QUERIES ON FRAMMER ANALYTICS SCHEMA")
    print("#" * 80)

    for query in test_queries:
        run_agent(graph, query)

    print("\n" + "#" * 80)
    print("# TEST EXECUTION COMPLETED")
    print("#" * 80 + "\n")


if __name__ == "__main__":
    main()
