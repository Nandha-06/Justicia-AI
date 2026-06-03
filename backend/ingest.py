import json
import os
import sys
from dotenv import load_dotenv
load_dotenv()

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings

try:
    from turbovec.langchain import TurboQuantVectorStore as TurboVecStore
except ImportError:
    from turbovec.langchain import TurboVecVectorStore as TurboVecStore

SECTIONS_FILE = "data/bns_sections.json"
DB_DIR = "db"

def ingest_data():
    # 1. Verify files exist
    if not os.path.exists(SECTIONS_FILE):
        print(f"Error: Scraped data file {SECTIONS_FILE} not found. Run scraper.py first.")
        sys.exit(1)
        
    print(f"Loading scraped BNS sections from {SECTIONS_FILE}...")
    with open(SECTIONS_FILE, "r", encoding="utf-8") as f:
        sections = json.load(f)
        
    print(f"Loaded {len(sections)} sections.")
    
    # 2. Create context-rich document chunks
    print("Chunking sections...")
    splitter = RecursiveCharacterTextSplitter(chunk_size=1500, chunk_overlap=150)
    documents = []
    
    for item in sections:
        text = item["content_text"]
        if not text:
            text = "No description available for this section."
            
        metadata = {
            "section_id": item["section_id"],
            "section_number": item["section_number"],
            "section_title": item["section_title"],
            "chapter": item["chapter"],
            "source_url": item["source_url"]
        }
        
        # Split section content
        chunks = splitter.split_text(text)
        for i, chunk in enumerate(chunks):
            # Prepend context to chunk content for better LLM retrieval performance
            context_prefix = f"Chapter: {metadata['chapter']}\nSection {metadata['section_number']}: {metadata['section_title']}\n\n"
            page_content = context_prefix + chunk
            
            chunk_metadata = metadata.copy()
            chunk_metadata["chunk_index"] = i
            
            doc = Document(
                page_content=page_content,
                metadata=chunk_metadata
            )
            documents.append(doc)
            
    print(f"Created {len(documents)} document chunks from {len(sections)} sections.")
    
    # 3. Generate embeddings locally
    print("Initializing local HuggingFace embeddings (all-MiniLM-L6-v2)...")
    embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
    
    print("Building TurboVec Vector Store (bit_width=4)...")
    
    # Ingest all documents at once since there are no API rate limits for local model
    texts = [doc.page_content for doc in documents]
    metadatas = [doc.metadata for doc in documents]
    ids = [f"sec-{doc.metadata['section_id']}-chunk-{doc.metadata['chunk_index']}" for doc in documents]
    
    store = TurboVecStore.from_texts(
        texts=texts,
        embedding=embeddings,
        metadatas=metadatas,
        ids=ids,
        bit_width=4
    )
            
    # 4. Persist index to disk
    print(f"Saving vector database to directory: '{DB_DIR}'...")
    os.makedirs(DB_DIR, exist_ok=True)
    store.dump(DB_DIR)
    
    print("Ingestion completed successfully!")

if __name__ == "__main__":
    ingest_data()
