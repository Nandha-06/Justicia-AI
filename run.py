import os
import sys
import subprocess

def check_and_prompt_api_key():
    # Try loading from .env if present
    if os.path.exists(".env"):
        print("Loading environment from .env file...")
        with open(".env", "r") as f:
            for line in f:
                if "=" in line and not line.strip().startswith("#"):
                    key, val = line.strip().split("=", 1)
                    os.environ[key.strip()] = val.strip()
                    
    # Prompt user if still missing
    if "GEMINI_API_KEY" not in os.environ:
        print("\n" + "="*60)
        print("                  GEMINI_API_KEY MISSING")
        print("="*60)
        print("This application requires a Google Gemini/Gemma API Key.")
        print("Please paste your API key here (it will not be saved permanently):")
        try:
            api_key = input("API Key: ").strip()
            if api_key:
                os.environ["GEMINI_API_KEY"] = api_key
                print("API Key loaded into environment.")
            else:
                print("Warning: No key entered. Agent queries will fail until a key is set.")
        except KeyboardInterrupt:
            print("\nExiting.")
            sys.exit(0)
        print("="*60 + "\n")

def start_server():
    print("Starting NyayaSanhita AI RAG System Server...")
    print("Click here to open the Web App: http://localhost:8000")
    
    # Locate virtual env uvicorn executable
    uvicorn_cmd = ".venv\\Scripts\\uvicorn" if os.name == 'nt' else ".venv/bin/uvicorn"
    if not os.path.exists(uvicorn_cmd + (".exe" if os.name == 'nt' else "")):
        # Fallback to python uvicorn call
        cmd = [sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "8000"]
    else:
        cmd = [uvicorn_cmd, "backend.main:app", "--host", "127.0.0.1", "--port", "8000"]
        
    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        print("\nStopping server.")

if __name__ == "__main__":
    check_and_prompt_api_key()
    start_server()
