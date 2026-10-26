import json
import os
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from groq import Groq
import trafilatura

# 1. 환경변수 및 Groq 클라이언트 초기화
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


# 3. [거시 이슈] Google News RSS(한국) 기반 주요 관심 이슈 수집
def get_google_trending_topics(top_n=5):
    url = "https://news.google.com/rss?hl=ko&gl=KR&ceid=KR:ko"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    }

    try:
        res = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(res.text, "xml")
        items = soup.find_all("item")[:top_n]

        trends = []
        for item in items:
            if item.title:
                trends.append(item.title.text.strip())
        return trends
    except Exception as e:
        print(f"⚠️ 구글 주요 이슈 수집 실패: {e}")
        return []


# 4. [섹션별 뉴스] 네이버 분야별 주요 뉴스 각 Top 5 수집
def get_naver_section_ranking_news(top_n=5):
    sections = {
        "정치": "100",
        "경제": "101",
        "사회": "102",
        "IT/과학": "105",
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    }

    category_news = {}

    for sec_name, sec_id in sections.items():
        url = f"https://news.naver.com/section/{sec_id}"
        try:
            res = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(res.text, "html.parser")

            links = soup.select(
                "a.sa_text_title, a._headline_link, .sa_text_title"
            )
            news_list = []
            seen_titles = set()

            for a in links:
                title = a.text.strip()
                href = a.get("href", "")
                if title and href and title not in seen_titles and len(title) > 8:
                    seen_titles.add(title)
                    if not href.startswith("http"):
                        href = "https://news.naver.com" + href
                    news_list.append({"title": title, "url": href})
                    if len(news_list) >= top_n:
                        break

            # 보완 로직: 지정 선택자로 안 잡힐 경우 일반 기사 링크 탐색
            if not news_list:
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    title = a.text.strip()
                    if (
                        "/article/" in href
                        and len(title) > 10
                        and title not in seen_titles
                    ):
                        seen_titles.add(title)
                        news_list.append({"title": title, "url": href})
                        if len(news_list) >= top_n:
                            break

            category_news[sec_name] = news_list
        except Exception as e:
            print(f"⚠️ [{sec_name}] 수집 중 에러: {e}")
            category_news[sec_name] = []

    return category_news


# 5. 뉴스 본문 추출 함수
def get_article_content(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    }
    try:
        res = requests.get(url, headers=headers, timeout=10)
        text = trafilatura.extract(res.text)
        return text[:1000] if text else ""
    except Exception:
        return ""


# 6. Groq LLM으로 거시적 흐름 + 분야별 Top 5 종합 브리핑 생성
def generate_macro_executive_briefing(trends, category_news):
    prompt_context = "=== [실시간 주요 거시/사회 이슈] ===\n"
    if trends:
        for idx, t in enumerate(trends, 1):
            prompt_context += f"{idx}. {t}\n"
    else:
        prompt_context += "이슈 정보 없음\n"

    prompt_context += "\n=== [분야별 주요 뉴스 Top 5] ===\n"

    for sec_name, news_items in category_news.items():
        prompt_context += f"\n▶ [{sec_name}]\n"
        for idx, news in enumerate(news_items, 1):
            content = get_article_content(news["url"])
            summary_ref = content[:250] if content else news["title"]
            prompt_context += (
                f"{idx}. {news['title']}\n   - 요약참조: {summary_ref}\n"
            )

    prompt = f"""
너는 수석 경제/사회 분석가이자 에그제큐티브 에디터야. 
전달된 [실시간 주요 거시/사회 이슈]와 [분야별 주요 뉴스 Top 5]를 바탕으로 카카오톡 전송용 종합 보고서를 작성해 줘.

[작성 지침]
1. **[1부: 오늘 세간의 거시적 흐름]**: 거시 이슈와 분야별 주요 뉴스를 통합 분석하여 2~3줄로 총평할 것.
2. **[2부: 카테고리별 핵심 요약]**: 정치, 경제, 사회, IT/과학 각 카테고리별로 상위 기사 핵심을 이모지를 활용해 1~2줄씩 핵심만 요약할 것.
3. **[엄격한 분량 제한]**: 카카오톡 메시지 글자 수 제한이 있으므로 **전체 분량을 공백 포함 750자 이내**로 짧고 간결하게 작성할 것.

[데이터]
{prompt_context}
"""

    try:
        completion = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        return completion.choices[0].message.content
    except Exception as e:
        print("❌ Groq API 호출 중 오류 발생:", e)
        return None


# --- 실행부 ---
if __name__ == "__main__":
    print("🌐 [1/3] 세간의 주요 이슈(Google News RSS) 수집 중...")
    trends = get_google_trending_topics(top_n=5)
    print(f"  └ 수집된 주요 이슈 {len(trends)}개")

    print("\n📰 [2/3] 네이버 분야별 Top 5 뉴스 수집 중...")
    category_news = get_naver_section_ranking_news(top_n=5)

    for sec, items in category_news.items():
        print(f"  └ [{sec}] {len(items)}개 기사 수집됨")

    print("\n🤖 [3/3] Groq 120B 모델 기반 거시 종합 브리핑 생성 중...")
    briefing = generate_macro_executive_briefing(trends, category_news)

    if briefing:
        print("\n--- [생성된 거시 종합 브리핑] ---")
        print(briefing)
        print("---------------------------------\n")

        print("📱 카카오톡 나에게 보내기 전송 중...")
        access_token = get_valid_kakao_token()

        if access_token:
            send_url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
            headers = {"Authorization": f"Bearer {access_token}"}

            payload = {
                "template_object": json.dumps(
                    {
                        "object_type": "text",
                        "text": f"📊 [오늘의 거시 종합 & 분야별 브리핑]\n\n{briefing}",
                        "link": {
                            "web_url": "https://news.naver.com",
                            "mobile_web_url": "https://news.naver.com",
                        },
                        "button_title": "네이버 뉴스 바로가기",
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
            print("❌ 유효한 카카오 Access Token을 가져오지 못했습니다.")
    else:
        print("❌ 브리핑 생성 실패")
