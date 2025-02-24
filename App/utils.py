# utils.py
import os

def get_openai_api_key():
    return os.getenv('OPENAI_API_KEY')
