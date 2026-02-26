import os
from dotenv import load_dotenv

load_dotenv()

# Gauss / Internal API Config (Legacy)
OPENAPI_TOKEN = os.getenv("OPENAPI_TOKEN", "token")
GEN_AI_CLIENT = os.getenv("GEN_AI_CLIENT", "clien")
USER_MAIL = os.getenv("USER_MAIL", "user@test.com")

MODEL_ID_GAUSS_2 = os.getenv("MODEL_ID_GAUSS_2", "gauss2")
MODEL_ID_GAUSS_O = os.getenv("MODEL_ID_GAUSS_O", "gausso")
GEN_AI_HOST = os.getenv("GEN_AI_HOST", "https://my.host.net:8088/call_messages")

# OpenAI Config (New)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_API_BASE = os.getenv("OPENAI_API_BASE")  # For proxy or alternate endpoints
OPENAI_MODEL_NAME = os.getenv("OPENAI_MODEL_NAME", "gpt-4o")
