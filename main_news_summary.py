import json
import os
import requests
import trafilatura
from dotenv import load_dotenv
from groq import Groq

# 1. 환경변수 로드 및 Groq 클라이언트 초기화
load_dotenv()

groq_api_key = os.getenv("GROQ_API_KEY")
if not groq_api_key:
    print("❌ .env 파일에서 GROQ_API_KEY를 찾을 수 없습니다.")
    exit(1)

client = Groq(api_key=groq_api_key)


# 2. 카카오 토큰 자동 갱신 함수
def get_valid_kakao_token(token_file="kakao_code.json"):
    if not os.path.exists(token_file):
        print(f"❌ {token_file} 파일이 없습니다.")
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

        if client_id:
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


# 3. 영문 웹 페이지 본문 크롤링 함수
def extract_article_text(url):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()

        text = trafilatura.extract(response.text)
        if not text:
            print("❌ 본문 텍스트를 추출하지 못했습니다.")
            return None
        return text
    except Exception as e:
        print(f"❌ 웹 페이지 수집 실패: {e}")
        return None


# 4. Groq API 호출 (70B 대형 모델 기반 영-한 번역 및 요약)
def summarize_en_to_ko_with_groq(english_text):
    prompt = f"""
You are a professional tech news editor and translator. 
Read the following English article and summarize/translate it into natural, fluent KOREAN.

[Instructions]
1. Write the summary in clear, natural Korean (한국어).
2. Include appropriate emojis suitable for KakaoTalk messages.
3. Strict Output Structure:
[3줄 요약]
• (Summary line 1)
• (Summary line 2)
• (Summary line 3)

[주요 키워드 2개]
1. (Keyword 1)
2. (Keyword 2)

[English Article]
{english_text[:4000]}
"""

    try:
        completion = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        return completion.choices[0].message.content
    except Exception as e:
        print("❌ Groq API 호출 오류:", e)
        return None


# --- 실행부 ---
if __name__ == "__main__":
    # 테스트용 해외 테크 기사 URL
    TARGET_URL = "https://arstechnica.com/security/2026/10/disgraced-emudhra-drops-out-of-tls-business-following-certificate-debacle/"
    print(f"🌐 [1/3] 영문 기사 본문 수집 중...\nURL: {TARGET_URL}")
    article_text = extract_article_text(TARGET_URL)

    if article_text:
        print(
            f"✅ 수집 완료 ({len(article_text)}자). Groq Llama-3.3-70B 한글 요약 시작...\n"
        )

        summary_text = summarize_en_to_ko_with_groq(article_text)

        if summary_text:
            print("--- [Groq 한글 요약 결과] ---")
            print(summary_text)
            print("------------------------------\n")

            print("📱 [3/3] 카카오톡 나에게 보내기 전송 중...")
            access_token = get_valid_kakao_token()

            if access_token:
                send_url = (
                    "https://kapi.kakao.com/v2/api/talk/memo/default/send"
                )
                headers = {"Authorization": f"Bearer {access_token}"}

                payload = {
                    "template_object": json.dumps(
                        {
                            "object_type": "text",
                            "text": f"📰 [오늘의 해외 테크 브리핑]\n\n{summary_text}",
                            "link": {
                                "web_url": TARGET_URL,
                                "mobile_web_url": TARGET_URL,
                            },
                            "button_title": "원문 기사 보기",
                        },
                        ensure_ascii=False,
                    )
                }

                res = requests.post(send_url, headers=headers, data=payload)
                res_json = res.json()

                if res.status_code == 200 and res_json.get("result_code") == 0:
                    print("🎉 카카오톡 전송 성공!")
                else:
                    print("❌ 카카오톡 전송 실패:", res_json)
            else:
                print("❌ 카카오 Access Token 획득 실패")
        else:
            print("❌ 요약 생성 실패")
    else:
        print("❌ 기사 본문 수집 실패로 작업을 중단합니다.")
