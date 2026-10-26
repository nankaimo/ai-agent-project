import os
from dotenv import load_dotenv
from google import genai

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# 현재 프로젝트에서 사용 가능한 모든 모델 출력
print("📋 사용 가능한 Gemini 모델 목록:")
for model in client.models.list():
    if "gemini" in model.name:
        print("-", model.name)