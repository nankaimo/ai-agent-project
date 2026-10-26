import json
import os
import requests
from dotenv import load_dotenv

# 1. .env 파일의 환경변수 로드
load_dotenv()


# 2. 카카오 토큰 자동 갱신 함수
def get_valid_kakao_token(token_file="kakao_code.json"):
    if not os.path.exists(token_file):
        print(
            f"❌ {token_file} 파일이 없습니다. main_ollama.py와 같은 폴더에 있는지 확인해 주세요."
        )
        return None

    try:
        with open(token_file, "r", encoding="utf-8") as fp:
            tokens = json.load(fp)
    except Exception as e:
        print(f"❌ {token_file} 읽기 실패:", e)
        return None

    refresh_token = tokens.get("refresh_token")
    if refresh_token:
        url = "https://kauth.kakao.com/oauth/token"
        client_id = os.getenv("KAKAO_REST_API_KEY") or tokens.get("client_id")

        if not client_id:
            print(
                "⚠️ client_id(REST API 키)가 없습니다. 기존 access_token으로 시도합니다."
            )
            return tokens.get("access_token")

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

            with open(token_file, "w", encoding="utf-8") as fp:
                json.dump(tokens, fp, indent=4, ensure_ascii=False)
            print("🔄 카카오 Access Token 자동 갱신 완료!")

    return tokens.get("access_token")


# 3. 로컬 Ollama API 호출 함수
def generate_with_ollama(prompt, model_name="llama3.2"):
    """로컬 Ollama API(http://localhost:11434)를 통해 요약문을 생성합니다."""
    url = "http://localhost:11434/api/generate"
    payload = {"model": model_name, "prompt": prompt, "stream": False}

    try:
        response = requests.post(url, json=payload, timeout=90)
        if response.status_code == 200:
            return response.json().get("response")
        else:
            print(
                f"❌ Ollama 호출 실패 (상태 코드 {response.status_code}):",
                response.text,
            )
            return None
    except requests.exceptions.ConnectionError:
        print(
            "❌ Ollama 서비스에 연결할 수 없습니다. Ollama 앱이 실행 중인지 확인하세요."
        )
        return None
    except Exception as e:
        print("❌ Ollama 요청 중 오류 발생:", e)
        return None


# --- 실행부 ---

sample_article = """
[AI 트렌드 리포트]
최근 생성형 AI 분야에서는 단순한 대화형 모델을 넘어, 스스로 판단하고 도구를 사용하는 'AI 에이전트(Agent)' 시스템이 빠르게 확산되고 있다.
기존 LLM은 환각 현상이나 수학적/논리적 연산의 한계가 있었으나, 파이썬 로컬 스크립트가 데이터 수집 및 연산을 담당하고 LLM이 결과를 추론 및 요약하는 'Agentic Workflow' 조합을 통해 효율성을 극대화하고 있다.
이러한 구조는 연산 비용을 수십 배 이상 아낄 수 있으며, 개인 맞춤형 데이터 브리핑, 자동화 리포트 생성 등 다양한 분야에서 실용성을 인정받고 있다.
"""

print("🦙 로컬 Ollama AI가 원문을 분석하여 요약 중입니다...")

prompt = f"""
다음은 매거진 아티클 본문입니다. 
카카오톡으로 보기 좋게 이모지를 활용하여 [3줄 요약]과 [주요 키워드 2개]를 한국어로 작성해 주세요.

[본문]
{sample_article}
"""

# ⚠️ 맥북에 현재 설치된 Ollama 모델 이름으로 변경해 주세요. (예: llama3.2, qwen2.5, gemma2 등)
OLLAMA_MODEL = "llama3.2"

summary_text = generate_with_ollama(prompt, model_name=OLLAMA_MODEL)

if summary_text:
    print("\n--- [Ollama 요약 결과] ---")
    print(summary_text)
    print("---------------------------\n")

    print("📱 카카오톡 메시지 전송 시도 중...")
    access_token = get_valid_kakao_token()

    if access_token:
        send_url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
        headers = {"Authorization": f"Bearer {access_token}"}

        payload = {
            "template_object": json.dumps(
                {
                    "object_type": "text",
                    "text": f"📰 [오늘의 AI 매거진 요약 (Ollama)]\n\n{summary_text}",
                    "link": {
                        "web_url": "https://news.google.com",
                        "mobile_web_url": "https://news.google.com",
                    },
                    "button_title": "원문 보기",
                },
                ensure_ascii=False,
            )
        }

        res = requests.post(send_url, headers=headers, data=payload)
        res_json = res.json()

        if res.status_code == 200 and res_json.get("result_code") == 0:
            print("🎉 카카오톡 메시지가 성공적으로 전송되었습니다!")
        else:
            print("❌ 카카오톡 전송 실패 응답:", res_json)
    else:
        print("❌ 유효한 카카오 Access Token을 가져오지 못했습니다.")
else:
    print("❌ Ollama 요약 생성 실패로 카카오톡 전송을 중단합니다.")
