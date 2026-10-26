import json
import os
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import trafilatura
from crewai import Agent, Task, Crew, Process, LLM
from crewai.tools import tool
import litellm

# 1. 환경변수 로드
load_dotenv()
groq_api_key = os.getenv("GROQ_API_KEY")

if not groq_api_key:
    print("❌ .env 파일에서 GROQ_API_KEY를 찾을 수 없습니다.")
    exit(1)

os.environ["GROQ_API_KEY"] = groq_api_key
litellm.drop_params = True

# 2. 모델 설정 (토큰 제한 방어를 위해 max_tokens 조절)
RESEARCHER_LLM = LLM(
    model="openai/qwen/qwen3.8-27b",
    api_base="https://api.groq.com/openai/v1",
    api_key=groq_api_key,
    max_tokens=800
)

EDITOR_LLM = LLM(
    model="openai/qwen/qwen3.8-27b",
    api_base="https://api.groq.com/openai/v1",
    api_key=groq_api_key,
    max_tokens=800
)

# 3. 에이전트가 사용할 도구(Tool) 정의
@tool
def get_google_trending_topics_tool() -> str:
    """구글 뉴스 RSS를 기반으로 한국의 실시간 주요 거시/사회 이슈 Top 3를 수집합니다."""
    url = "https://news.google.com/rss?hl=ko&gl=KR&ceid=KR:ko"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(res.text, "xml")
        items = soup.find_all("item")[:3]
        return "\n".join([f"- {item.title.text.strip()}" for item in items if item.title])
    except Exception as e:
        return f"구글 이슈 수집 실패: {e}"

@tool
def get_naver_section_news_tool() -> str:
    """네이버 뉴스의 정치, 경제, 사회, IT/과학 분야별 주요 뉴스를 수집합니다."""
    sections = {"정치": "100", "경제": "101", "사회": "102", "IT/과학": "105"}
    headers = {"User-Agent": "Mozilla/5.0"}
    result_text = ""
    
    for sec_name, sec_id in sections.items():
        url = f"https://news.naver.com/section/{sec_id}"
        try:
            res = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(res.text, "html.parser")
            links = soup.select("a.sa_text_title, a._headline_link, .sa_text_title")[:2]
            
            result_text += f"\n[{sec_name}]\n"
            for a in links:
                title = a.text.strip()
                href = a.get("href", "")
                if href and not href.startswith("http"):
                    href = "https://news.naver.com" + href
                
                try:
                    res_article = requests.get(href, headers=headers, timeout=5)
                    content = trafilatura.extract(res_article.text)
                    summary_ref = content[:100] if content else "본문 없음"
                except Exception:
                    summary_ref = "추출 실패"
                    
                result_text += f"- 제목: {title}\n  요약: {summary_ref}\n"
        except Exception as e:
            continue
    return result_text

# 4. 에이전트 정의
researcher = Agent(
    role='수석 뉴스 리서처',
    goal='구글 트렌드와 네이버 섹션별 뉴스를 핵심만 간결하게 수집하여 전달한다.',
    backstory='당신은 방대한 정보 중 핵심만 골라내는 베테랑 정보 수집가입니다.',
    verbose=True,
    allow_delegation=False,
    tools=[get_google_trending_topics_tool, get_naver_section_news_tool],
    llm=RESEARCHER_LLM
)

editor = Agent(
    role='에그제큐티브 에디터',
    goal='수집된 정보를 바탕으로 카카오톡 전송용 종합 보고서를 750자 이내로 요약한다.',
    backstory='당신은 복잡한 이슈를 한눈에 파악할 수 있게 압축 정리하는 최고의 편집장입니다.',
    verbose=True,
    allow_delegation=False,
    llm=EDITOR_LLM
)

# 5. 태스크 정의
task1_collect = Task(
    description='구글과 네이버 뉴스 수집 도구를 사용해서 오늘의 주요 뉴스를 요약 형태로 수집하세요.',
    expected_output='주요 뉴스 제목과 핵심 요약이 포함된 텍스트 데이터',
    agent=researcher
)

task2_edit = Task(
    description='''
    수집된 데이터를 바탕으로 아래 지침에 따라 카카오톡 브리핑을 작성하세요.
    1. [1부: 오늘 세간의 거시적 흐름]: 거시 이슈 통합 총평 (2줄)
    2. [2부: 카테고리별 핵심 요약]: 정치, 경제, 사회, IT 핵심을 이모지와 함께 1줄씩 요약
    3. 전체 분량은 공백 포함 750자 이내로 엄격히 제한.
    반드시 한국어로 작성하세요.
    ''',
    expected_output='카카오톡 전송 규격에 맞는 최종 뉴스 브리핑 텍스트',
    agent=editor
)

# 6. Crew 구성
crew = Crew(
    agents=[researcher, editor],
    tasks=[task1_collect, task2_edit],
    process=Process.sequential
)

# 7. 카카오톡 전송 함수 정의
def send_kakao_memo(text: str):
    """kakao_code.json에 저장된 액세스 토큰을 이용해 나에게 카카오톡 메시지를 전송합니다."""
    json_path = "kakao_code.json"
    if not os.path.exists(json_path):
        print("❌ kakao_code.json 파일을 찾을 수 없어 카카오톡 전송을 건너뜁니다.")
        return

    with open(json_path, "r") as f:
        tokens = json.load(f)
    
    access_token = tokens.get("access_token")
    if not access_token:
        print("❌ kakao_code.json에 access_token이 없습니다.")
        return

    header = {"Authorization": f"Bearer {access_token}"}
    url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
    
    # 텍스트 형태의 나에게 보내기 페이로드
    payload = {
        "object_type": "text",
        "text": text,
        "link": {
            "web_url": "https://developers.kakao.com",
            "mobile_web_url": "https://developers.kakao.com"
        }
    }
    
    response = requests.post(url, headers=header, data={"template_object": json.dumps(payload)})
    
    if response.status_code == 200:
        print("✅ 카카오톡 나에게 전송 성공!")
    else:
        print(f"❌ 카카오톡 전송 실패: {response.status_code}, {response.text}")

if __name__ == "__main__":
    print("🚀 AI 에이전트 팀 뉴스 수집 및 편집 시작...")
    final_briefing = crew.kickoff()
    
    print("\n========================================")
    print("✅ 최종 브리핑 결과물 생성 완료. 카카오톡 전송 중...")
    
    # 카카오톡으로 전송 실행
    send_kakao_memo(str(final_briefing))
