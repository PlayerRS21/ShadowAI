from dotenv import load_dotenv
import os
load_dotenv()

try:
    cloudflare_account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID")
except:
    cloudflare_account_id = None


sources = [
    {
        "api": os.getenv("GROQ_API_KEY"),
        "url": "https://api.groq.com/openai/v1",
        "model": "openai/gpt-oss-20b",
    },
    {
        "api": os.getenv("GROQ_API_KEY2"),
        "url": "https://api.groq.com/openai/v1",
        "model": "openai/gpt-oss-20b",
    },
    {
        "api": os.getenv("OPENROUTER_API_KEY"),
        "url": "https://openrouter.ai/api/v1",
        "model": "openrouter/free",
    },
    {
        "api": os.getenv("GEMINI_API_KEY"),
        "url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "model": "gemini-3.8-flash",
    },
    {
        "api": os.getenv("CLOUDFLARE_API_KEY"),
        "url": f"https://api.cloudflare.com/client/v4/accounts/{cloudflare_account_id}/ai/v1",
        "model": "@cf/meta/llama-3.3-70b-instruct-fp8-fast",
    },  
]
