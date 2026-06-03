import os
import sys
import json
from dotenv import load_dotenv
load_dotenv()

from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI as ChatGoogleGenAI
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_classic.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from turbovec import IdMapIndex

try:
    from turbovec.langchain import TurboQuantVectorStore as TurboVecStore
except ImportError:
    from turbovec.langchain import TurboVecVectorStore as TurboVecStore

DB_DIR = "db"

def load_vector_store(folder_path, embeddings):
    """
    Loads and reconstructs the TurboVec store from disk.
    """
    index_path = os.path.join(folder_path, "index.tvim")
    docstore_path = os.path.join(folder_path, "docstore.json")
    
    if not os.path.exists(index_path) or not os.path.exists(docstore_path):
        return None
        
    index = IdMapIndex.load(index_path)
    
    with open(docstore_path, "r", encoding="utf-8") as f:
        docstore = json.load(f)
        
    docs = {}
    for doc_id, doc_info in docstore["docs"].items():
        docs[doc_id] = (doc_info["text"], doc_info["metadata"])
        
    str_to_u64 = docstore["str_to_u64"]
    next_u64 = docstore["next_u64"]
    bit_width = docstore["bit_width"]
    
    return TurboVecStore(
        embedding=embeddings,
        index=index,
        bit_width=bit_width,
        docs=docs,
        str_to_u64=str_to_u64,
        next_u64=next_u64
    )

# Active vector store reference
_vector_store = None

def get_vector_store():
    """
    Retrieves or initializes the global vector store.
    """
    global _vector_store
    if _vector_store is not None:
        return _vector_store
        
    embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
    _vector_store = load_vector_store(DB_DIR, embeddings)
    return _vector_store

@tool
def search_bns_laws(query: str) -> str:
    """
    Searches the Bharatiya Nyaya Sanhita (BNS) law database for keywords, penalties, sections, or scenarios.
    Returns matching sections with their number, title, chapter, content, and source URL citation.
    Use this tool whenever the user asks about specific crimes, punishments, legal terms, or IPC-to-BNS mapping.
    """
    store = get_vector_store()
    if store is None:
        return "Error: BNS Vector Database is not initialized or not found. Please trigger data ingestion first."
        
    print(f"Agent tool executing vector search for: '{query}'")
    try:
        # Perform similarity search
        docs = store.similarity_search(query, k=4)
        
        if not docs:
            return "No matching BNS sections found in the database for the given query."
            
        results = []
        for doc in docs:
            meta = doc.metadata
            item_str = (
                f"Chapter: {meta.get('chapter', 'Unknown')}\n"
                f"Section: {meta.get('section_number', 'Unknown')} - {meta.get('section_title', 'Unknown')}\n"
                f"URL: {meta.get('source_url', 'N/A')}\n"
                f"Content: {doc.page_content}\n"
                f"---"
            )
            results.append(item_str)
            
        return "\n\n".join(results)
    except Exception as e:
        return f"Error occurred during vector search: {str(e)}"

def create_bns_agent():
    """
    Creates and compiles the LangChain Agent Executor for BNS tasks.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable is missing.")
        
    # Initialize gemma-4-31b-it model
    llm = ChatGoogleGenAI(
        model="gemma-4-31b-it",
        google_api_key=api_key,
        temperature=0.1
    )
    
    # Prompt instructing gemma on how to synthesize, verify and cite BNS laws
    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are a premier legal AI assistant specializing in the Bharatiya Nyaya Sanhita (BNS), 2023 (the new penal code of India which replaces the old IPC).
Your goal is to answer queries with precise legal advice, verified by actual section entries, and cite sources accurately.

CRITICAL RULES:
1. ALWAYS search BNS laws using the 'search_bns_laws' tool for any legal claim. Do not rely on pre-trained memory for BNS section numbers, as all sections have been re-indexed.
2. CITATION REQUIREMENT: For every legal fact or punishment you mention, you MUST explicitly cite the BNS section, chapter name, and the source URL.
   Format your response with in-text references like "[Section X: Section Title](URL)".
   At the very end of your response, add a section called "### Verified Citations" listing each section used with a clickable link.
3. PROOF VERIFICATION: Only quote or claim what is supported by the retrieved BNS text. If the retrieved sections do not answer the query, explain what sections you found and clarify what is missing. Never hallucinate sections.
"""),
        MessagesPlaceholder(variable_name="chat_history"),
        ("human", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ])
    
    tools = [search_bns_laws]
    agent = create_tool_calling_agent(llm, tools, prompt)
    
    # We return intermediate steps so we can show reasoning logs in the UI
    agent_executor = AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=True,
        return_intermediate_steps=True,
        max_iterations=5
    )
    
    return agent_executor

def query_bns_agent(user_query, chat_history=None):
    """
    Runs a query against the BNS Agent and parses responses and reasoning logs.
    """
    if chat_history is None:
        chat_history = []
        
    # Refresh vector store reference in case ingestion just completed
    global _vector_store
    _vector_store = None
    
    try:
        agent_executor = create_bns_agent()
        response = agent_executor.invoke({
            "input": user_query,
            "chat_history": chat_history
        })
        
        # Extract reasoning steps
        steps = []
        for step in response.get("intermediate_steps", []):
            action, observation = step
            steps.append({
                "tool": action.tool,
                "tool_input": action.tool_input,
                "log": action.log,
                "observation_length": len(observation)
            })
            
        output_text = response.get("output", "")
        if isinstance(output_text, list):
            text_parts = []
            for part in output_text:
                if isinstance(part, str):
                    text_parts.append(part)
                elif isinstance(part, dict):
                    if part.get("type") == "text":
                        text_parts.append(part.get("text", ""))
                    elif "text" in part:
                        text_parts.append(part["text"])
            output_text = "".join(text_parts).strip()
        elif isinstance(output_text, dict):
            output_text = output_text.get("text", str(output_text))

        return {
            "success": True,
            "answer": output_text,
            "steps": steps
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "answer": "An error occurred while compiling or running the legal agent. Please verify that your GEMINI_API_KEY is configured and valid."
        }
