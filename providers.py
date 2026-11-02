from dotenv import load_dotenv
import os
from openai import (OpenAI,OpenAIError,APIConnectionError,APITimeoutError,RateLimitError,AuthenticationError,APIStatusError,)
import ast
load_dotenv()

try:
    cloudflare_account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID")
except:
    cloudflare_account_id = None


providers = {
    "1": {
        "api": os.getenv("GROQ_API_KEY"),
        "url": "https://api.groq.com/openai/v1",
        "model": "openai/gpt-oss-120b",
    },
    "2": {
        "api": os.getenv("GROQ_API_KEY2"),
        "url": "https://api.groq.com/openai/v1",
        "model": "openai/gpt-oss-120b",
    },
    "3": {
        "api": os.getenv("OPENROUTER_API_KEY"),
        "url": "https://openrouter.ai/api/v1",
        "model": "openrouter/free",
    },
    "4": {
        "api": os.getenv("MISTRAL_API_KEY"),
        "url": "https://api.mistral.ai/v1",
        "model": "mistral-small",
    },
    "6": {
        "api": os.getenv("GEMINI_API_KEY"),
        "url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "model": "gemini-3.8-flash",
    },
    # "5": {
        # "api": os.getenv("CLOUDFLARE_API_KEY"),
        # "url": f"https://api.cloudflare.com/client/v4/accounts/{cloudflare_account_id}/ai/v1",
        # "model": "@cf/meta/llama-3.2-1b-instruct",
    # },  
}
