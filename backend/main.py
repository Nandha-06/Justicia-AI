import os
import sys
import json
import asyncio
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional, Dict, Any

# Ensure parent directory is in path to import backend modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.scraper import scrape_bns
from backend.ingest import ingest_data
from backend.rag_agent import query_bns_agent

app = FastAPI(title="Justicia AI API")

# Enable CORS for local testing
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global status tracker
pipeline_status = {
    "is_scraping": False,
    "is_ingesting": False,
}

class QueryRequest(BaseModel):
    query: str
    chat_history: Optional[List[Dict[str, str]]] = []

async def run_scraper_task():
    global pipeline_status
    pipeline_status["is_scraping"] = True
    try:
        print("Starting background scraping task...")
        # Start scraping all 358 sections
        await scrape_bns(1, 358, use_crawl4ai=True)
    except Exception as e:
        print(f"Error in background scraper task: {e}")
    finally:
        pipeline_status["is_scraping"] = False

async def run_ingestion_task():
    global pipeline_status
    pipeline_status["is_ingesting"] = True
    try:
        print("Starting background ingestion task...")
        # Since ingest_data is synchronous, we run it in an executor to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, ingest_data)
    except Exception as e:
        print(f"Error in background ingestion task: {e}")
    finally:
        pipeline_status["is_ingesting"] = False

@app.get("/api/status")
def get_status():
    """
    Returns the real-time status of the pipeline (scraping count, ingestion status).
    """
    scraped_count = 0
    if os.path.exists("data/bns_sections.json"):
        try:
            with open("data/bns_sections.json", "r", encoding="utf-8") as f:
                sections = json.load(f)
                scraped_count = len(sections)
        except Exception:
            pass
            
    db_loaded = os.path.exists("db/index.tvim") and os.path.exists("db/docstore.json")
    
    return {
        "is_scraping": pipeline_status["is_scraping"],
        "scraped_count": scraped_count,
        "scraped_total": 358,
        "is_ingesting": pipeline_status["is_ingesting"],
        "db_loaded": db_loaded,
        "api_key_configured": "GEMINI_API_KEY" in os.environ
    }

@app.post("/api/query")
def execute_query(request: QueryRequest):
    """
    Executes a legal query against the gemma agent.
    """
    if "GEMINI_API_KEY" not in os.environ:
        raise HTTPException(
            status_code=400,
            detail="GEMINI_API_KEY is not set on the server. Please set it before running queries."
        )
        
    db_loaded = os.path.exists("db/index.tvim") and os.path.exists("db/docstore.json")
    if not db_loaded:
        raise HTTPException(
            status_code=400,
            detail="The vector database is not loaded. Please ingest the scraped data first."
        )
        
    print(f"Received query: '{request.query}'")
    
    # Structure chat history for LangChain (List of dicts or messages)
    chat_history_messages = []
    if request.chat_history:
        for msg in request.chat_history:
            role = msg.get("role", "human")
            content = msg.get("content", "")
            if role == "user":
                chat_history_messages.append(("human", content))
            elif role == "assistant":
                chat_history_messages.append(("ai", content))
                
    result = query_bns_agent(request.query, chat_history=chat_history_messages)
    
    if not result.get("success", False):
        raise HTTPException(status_code=500, detail=result.get("error", "Internal agent error"))
        
    return {
        "answer": result.get("answer"),
        "steps": result.get("steps", [])
    }

@app.post("/api/query-stream")
def execute_query_stream(request: QueryRequest):
    """
    Executes a legal query and streams the gemma agent responses/steps in real-time.
    """
    if "GEMINI_API_KEY" not in os.environ:
        raise HTTPException(
            status_code=400,
            detail="GEMINI_API_KEY is not set on the server. Please set it before running queries."
        )
        
    db_loaded = os.path.exists("db/index.tvim") and os.path.exists("db/docstore.json")
    if not db_loaded:
        raise HTTPException(
            status_code=400,
            detail="The vector database is not loaded. Please ingest the scraped data first."
        )
        
    chat_history_messages = []
    if request.chat_history:
        for msg in request.chat_history:
            role = msg.get("role", "human")
            content = msg.get("content", "")
            if role == "user":
                chat_history_messages.append(("human", content))
            elif role == "assistant":
                chat_history_messages.append(("ai", content))

    async def event_generator():
        from backend.rag_agent import create_bns_agent
        try:
            agent_executor = create_bns_agent()
            
            async for event in agent_executor.astream_events(
                {"input": request.query, "chat_history": chat_history_messages},
                version="v1"
            ):
                event_type = event["event"]
                name = event["name"]
                
                if event_type == "on_tool_start":
                    yield f"data: {json.dumps({'type': 'tool_start', 'tool': name, 'tool_input': event['data'].get('input', {})})}\n\n"
                elif event_type == "on_tool_end":
                    obs = event["data"].get("output", "")
                    yield f"data: {json.dumps({'type': 'tool_end', 'tool': name, 'observation_length': len(str(obs))})}\n\n"
                elif event_type == "on_chat_model_stream":
                    chunk = event["data"].get("chunk")
                    if chunk:
                        content = chunk.content
                        if isinstance(content, str) and content:
                            yield f"data: {json.dumps({'type': 'token', 'content': content})}\n\n"
                        elif isinstance(content, list):
                            text = ""
                            for part in content:
                                if isinstance(part, str):
                                    text += part
                                elif isinstance(part, dict) and part.get("type") == "text":
                                    text += part.get("text", "")
                            if text:
                                yield f"data: {json.dumps({'type': 'token', 'content': text})}\n\n"
            
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.post("/api/trigger-scrape")
def trigger_scrape(background_tasks: BackgroundTasks):
    """
    Triggers the BNS law scraper in the background.
    """
    if pipeline_status["is_scraping"]:
        return {"message": "Scraper is already running."}
        
    background_tasks.add_task(run_scraper_task)
    return {"message": "Scraper triggered successfully in the background."}

@app.post("/api/trigger-ingest")
def trigger_ingest(background_tasks: BackgroundTasks):
    """
    Triggers vector database ingestion in the background.
    """
    if pipeline_status["is_ingesting"]:
        return {"message": "Ingestion is already running."}
        
    db_loaded = os.path.exists("data/bns_sections.json")
    if not db_loaded:
        raise HTTPException(
            status_code=400, 
            detail="Scraped data is missing. Please run scraping before ingestion."
        )
        
    background_tasks.add_task(run_ingestion_task)
    return {"message": "Ingestion triggered successfully in the background."}

# Mount static frontend directory (created in next steps)
# This will serve index.html at "/"
frontend_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")
if os.path.exists(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")
else:
    print(f"Warning: Frontend path {frontend_path} does not exist yet. Static mounting skipped.")
