import os
import requests
from dotenv import load_dotenv

load_dotenv()
url = "https://openrouter.ai/api/v1/models"
resp = requests.get(url).json()

free_gemini = [m['id'] for m in resp['data'] if 'google' in m['id'].lower() and ':free' in m['id']]
print("Free models:", free_gemini)

# Test the specific one we tried:
test_url = "https://openrouter.ai/api/v1/chat/completions"
headers = {"Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}", "Content-Type": "application/json"}
data = {"model": "google/gemini-2.0-flash-lite-preview-02-05:free", "messages": [{"role": "user", "content": "hi"}]}
err_resp = requests.post(test_url, headers=headers, json=data)
print("Error:", err_resp.text)
