import os
from dotenv import load_dotenv
import requests
load_dotenv()
key = os.environ.get('OPENROUTER_API_KEY')
headers={'Authorization': f'Bearer {key}'}
print(requests.get('https://openrouter.ai/api/v1/auth/key', headers=headers).text)
