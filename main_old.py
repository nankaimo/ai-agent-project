import json
import os
import time
import requests
from dotenv import load_dotenv
from google import genai
from google.genai.errors import ServerError

# 1. .env 파일 환경변수 로드
load_dotenv()

# Gemini 클라이언트 초기화
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


# 2. 카카오 토큰 자동 갱신 함수
def get_valid_kakao_token(token_file="kakao_code.json"):
    if not os.path.exists(token_file):
        print(f"❌ {token_file} 파일이 없습니다. 경로를 확인해 주세요.")
        return None

    with open(token_file, "r") as fp:
        tokens = json.load(fp)

    refresh_token = tokens.get("refresh_token")
    if refresh_token:
        url = "https://kauth.kakao.com/oauth/token"
        client_id = os.getenv("KAKAO_REST_API_KEY") or tokens.get("client_id")

        data = {
            "grant_type": "refresh_token",
            "client_id": client_id,
            "refresh_token": refresh_token,
        }

        res = requests.post(url, data=data)
        result = res.json()

        if "access_token" in result:
            tokens["access_token"] = result["access_token"]
            if "refresh_token" in result:
                tokens["refresh_token"] = result["refresh_token"]

            with open(token_file, "w") as fp:
                json.dump(tokens, fp, indent=4)
            print("🔄 카카오 Access Token 자동 갱신 완료!")

    return tokens.get("access_token")


# --- 실행부 ---

# 샘플 본문
sample_article = """
[AI 트렌드 리포트]
최근 생성형 AI 분야에서는 단순한 대화형 모델을 넘어, 스스로 판단하고 도구를 사용하는 'AI 에이전트(Agent)' 시스템이 빠르게 확산되고 있다.
기존 LLM은 환각 현상이나 수학적/논리적 연산의 한계가 있었으나, 파이썬 로컬 스크립트가 데이터 수집 및 연산을 담당하고 LLM이 결과를 추론 및 요약하는 'Agentic Workflow' 조합을 통해 효율성을 극대화하고 있다.
이러한 구조는 연산 비용을 수십 배 이상 아낄 수 있으며, 개인 맞춤형 데이터 브리핑, 자동화 리포트 생성 등 다양한 분야에서 실용성을 인정받고 있다.
"""

print("🤖 제미나이가 원문을 분석하여 요약 중입니다...")

prompt = f"""
다음은 매거진 아티클 본문입니다. 
카카오톡으로 보기 좋게 이모지를 활용하여 [3줄 요약]과 [주요 키워드 2개]를 작성해 주세요.

[본문]
{sample_article}
"""

# 3. Gemini API 호출 (503 에러 대비 3회 자동 재시도)
max_retries = 3
summary_text = None

for attempt in range(max_retries):
    try:
        response = client.models.generate_content(
            model="gemini-3.7-flash",
            contents=prompt,
        )
        summary_text = response.text
        break
    except ServerError as e:
        if attempt < max_retries - 1:
            print(
                f"⚠️ 구글 서버 응답 지연 (503). 3초 후 재시도합니다... ({attempt + 1}/{max_retries})"
            )
            time.sleep(3)
        else:
            print("❌ 구글 서버 재시도 횟수를 초과했습니다.")
            raise e

# 4. 요약 결과 확인 및 카카오톡 전송
if summary_text:
    print("\n--- [제미나이 요약 결과] ---")
    print(summary_text)
    print("---------------------------\n")

    access_token = get_valid_kakao_token()

    if access_token:
        send_url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
        headers = {"Authorization": f"Bearer {access_token}"}

        payload = {
            "template_object": json.dumps({
                "object_type": "text",
                "text": f"📰 [오늘의 AI 매거진 요약]\n\n{summary_text}",
                "link": {
                    "web_url": "https://news.google.com",
                    "mobile_web_url": "https://news.google.com",
                },
                "button_title": "원문 보기",
            })
        }

        res = requests.post(send_url, headers=headers, data=payload)

        if res.status_code == 200 and res.json().get("result_code") == 0:
            print("📱 카카오톡 메시지가 성공적으로 전송되었습니다!")
        else:
            print("❌ 카카오톡 전송 실패:", res.json())
