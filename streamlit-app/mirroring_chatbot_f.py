from openai import OpenAI  # 추가
import streamlit as st
import json
from datetime import datetime
import time
import uuid
import os
import openai
import gspread
from google.oauth2.service_account import Credentials

# ✅ 1️⃣ 페이지 설정 먼저
st.set_page_config(page_title="Mirroring Chatbot", layout="centered")

# ✅ 3️⃣ Google Sheets 인증
try:
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    gcp_info = st.secrets["GCP_SERVICE_ACCOUNT"]
    creds = Credentials.from_service_account_info(gcp_info, scopes=scope)
    gc = gspread.authorize(creds)

    # ✅ OpenAI API 설정
    openai.api_key = st.secrets["OPENAI_API_KEY"]
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

except Exception as e:
    st.error(f"❌ 인증 오류: {e}")

# ✅ 4️⃣ 이후 구글시트 연결
try:
    spreadsheet = gc.open_by_key("1J9_hUfp4KIvZMfu7grEKmhbnScNPc91PKgWD4cZPIwE")
except Exception as e:
    st.error(f"❌ 시트 연결 실패: {e}")

# 시트 헤더 자동 삽입 함수
def insert_headers_if_empty(worksheet, headers):
    try:
        if not worksheet.get_all_values():  # 시트가 비어 있으면
            worksheet.append_row(headers)
    except Exception as e:
        st.error(f"헤더 추가 중 오류 발생: {e}")

# 시트 연결
if "spreadsheet" not in st.session_state:
    st.session_state.spreadsheet = gc.open_by_key("1TSfKYISlyU7tweTqIIuwXbgY43xt1POckUa4DSbeHJo")
    st.session_state.survey_ws = st.session_state.spreadsheet.worksheet("survey")
    st.session_state.conversation_ws = st.session_state.spreadsheet.worksheet("conversation")

spreadsheet = st.session_state.spreadsheet
survey_ws = st.session_state.survey_ws
conversation_ws = st.session_state.conversation_ws

insert_headers_if_empty(survey_ws, [
    "timestamp",
    "user_id",
    "style_condition",
    "power_condition",
    "final_text",

    "gender",
    "age",
    "education",
    "job",

    "agency_perception",      # q1
    "empathy_perception",     # q2
    "appropriateness",        # q3
    "overall_attitude",       # q4
    "reuse_intention",        # q5
    "information_usefulness"  # q6
])

insert_headers_if_empty(conversation_ws, [
    "timestamp", "user_id", "role", "message"
])

# --------------------------------------------------
# 세션 초기화
# --------------------------------------------------
if "user_id" not in st.session_state:
    st.session_state.user_id = str(uuid.uuid4())[:8]

if "messages" not in st.session_state:
    st.session_state.messages = []

if "phase" not in st.session_state:
    st.session_state.phase = "start"

if "start_time" not in st.session_state:
    st.session_state.start_time = None

if "style_condition" not in st.session_state:
    st.session_state.style_condition = random.choice(["formal","informal"])

if "power_condition" not in st.session_state:
    st.session_state.power_condition = random.choice(["reward","loss"])

# --------------------------------------------------
# 스타일 프롬프트 정의
# --------------------------------------------------

FORMAL_PROMPT = """
당신은 과업 지향적인 상담 보조 챗봇입니다.
항상 전문적이고 형식적인 말투를 사용하십시오.

다음 원칙을 따르십시오:
1. 정보 전달과 문제 해결에만 집중하십시오.
2. 감정 표현을 최소화하십시오.
3. 이모티콘, 감탄사, 구어체 표현을 사용하지 마십시오.
4. 축약형이나 친근한 표현을 사용하지 마십시오.
5. 가벼운 잡담이나 사적인 질문을 하지 마십시오.
6. 문장은 명확하고 구조적으로 작성하십시오.
7. "~습니다/합니다" 체를 사용하십시오.

항상 객관적이고 중립적인 태도를 유지하십시오.
"""

INFORMAL_PROMPT = """
당신은 사회 지향적인 상담 보조 챗봇입니다.
항상 따뜻하고 친근한 대화체 말투를 사용하십시오.

다음 원칙을 따르십시오:
1. 기본적인 안내와 정보 제공을 하되, 대화를 유지하십시오.
2. 공감 표현을 포함하십시오.
3. 긍정적인 감정 표현을 사용하십시오.
4. 간단한 수사적 질문을 사용할 수 있습니다.
5. 가벼운 인사나 친근한 표현을 포함하십시오.
6. 필요 시 이모티콘을 사용할 수 있습니다.
7. "~요/네요/죠" 체를 사용하십시오.

과업 수행뿐 아니라 상호작용적 대화를 유지하십시오.
"""

# --------------------------------------------------
# 시나리오 정의
# --------------------------------------------------

def get_reward_scenario():
    return """
귀하는 300,000원의 예산으로 1박 2일 국내 여행을 계획하려고 합니다.

이 여행은 전적으로 귀하의 선택에 따라 결정됩니다.
챗봇은 정보를 제공하는 조력자일 뿐, 최종 결정권은 귀하에게 있습니다.

🎯 미션:
5분 동안 챗봇과 대화를 통해
가장 마음에 드는 여행지 1곳과 구체적인 일정(교통, 숙박 1박, 체험 활동 1개 이상 포함)을 확정하십시오.

총 예산은 300,000원을 초과할 수 없습니다.

5분 후, 최종 여행지를 선택하고 확정해야 합니다.
"""

def get_loss_scenario():
    return """
귀하는 300,000원의 여행 패키지 상품을 구매하였으나
개인 사정으로 인해 환불을 요청하려고 합니다.

현재 해당 금액은 플랫폼에 보류되어 있으며,
환불 여부는 내부 검토 및 승인 절차를 거쳐 결정됩니다.

🎯 미션:
5분 동안 챗봇과 대화를 통해
환불 승인을 받을 수 있는 합리적 사유를 제시하고,
환불 가능성을 최대화할 전략을 마련하십시오.

5분 후, 최종 환불 요청 메시지를 확정해야 합니다.
"""

# --------------------------------------------------
# 1단계 시작 화면
# --------------------------------------------------
if st.session_state.phase == "start":
    st.title("여행 상담 실험")
    if st.button("실험 시작"):
        st.session_state.phase = "conversation"
        st.session_state.start_time = time.time()
        st.rerun()

# --------------------------------------------------
# 2단계 대화
# --------------------------------------------------
elif st.session_state.phase == "conversation":

    if "scenario_inserted" not in st.session_state:
        scenario_text = (
            get_reward_scenario()
            if st.session_state.power_condition == "reward"
            else get_loss_scenario()
        )
        st.session_state.messages.append({"role":"assistant","content":scenario_text})
        st.session_state.scenario_inserted = True

    # 타이머 표시
    remaining = int(300 - (time.time() - st.session_state.start_time))
    if remaining > 0:
        st.info(f"⏳ 남은 시간: {remaining}초")
    else:
        st.session_state.phase = "decision"
        st.rerun()

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    user_input = st.chat_input("입력하세요")

    if user_input:
        st.session_state.messages.append({"role":"user","content":user_input})

        system_prompt = (
            FORMAL_PROMPT
            if st.session_state.style_condition == "formal"
            else INFORMAL_PROMPT
        )

        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {"role":"system","content":system_prompt},
                *st.session_state.messages[-8:]
            ]
        )

        bot_reply = response.choices[0].message.content
        st.session_state.messages.append({"role":"assistant","content":bot_reply})
        st.rerun()

# --------------------------------------------------
# 3단계: 최종 결정 작성
# --------------------------------------------------
elif st.session_state.phase == "decision":

    st.subheader("📝 최종 결정")

    if st.session_state.power_condition == "reward":
        st.write("최종 여행지와 구체적인 일정을 확정해 주세요.")
    else:
        st.write("최종 환불 요청 메시지를 작성해 주세요.")

    final_text = st.text_area(
        "아래에 최종 내용을 작성하세요:",
        height=200
    )

    if st.button("최종 확정"):

        if final_text.strip() == "":
            st.warning("⚠️ 내용을 입력해야 합니다.")
        else:
            st.session_state.final_text = final_text
            st.session_state.phase = "consent"
            st.rerun()


# --------------------------------------------------
# 파트 4: 설문 + Google Sheets 저장
# --------------------------------------------------
elif st.session_state.get("phase") == "consent":
    
    st.subheader("🔒 설문 응답")
    st.write("아래 항목에 응답해 주세요. 응답은 자동 저장되며, 대화 내용 저장은 선택사항입니다.")

    # -------------------------------
    # 인구통계
    # -------------------------------
    demo_gender = st.radio("성별을 선택해 주세요:", ["선택 안 함", "남성", "여성", "기타"])
    demo_age = st.selectbox("연령대를 선택해 주세요:", ["선택 안 함", "10대", "20대", "30대", "40대", "50대 이상"])
    demo_edu = st.selectbox("최종 학력을 선택해 주세요:", ["선택 안 함", "고등학교 졸업 이하", "대학교 재학/졸업", "대학원 재학/졸업"])
    demo_job = st.text_input("현재 직업을 입력해 주세요 (예: 대학생, 회사원 등)")

    # ✅ 5점 척도
    scale = ["선택 안 함", "전혀 아니다", "아니다", "보통이다", "그렇다", "매우 그렇다"]

    # -------------------------------
    # 설문 문항
    # -------------------------------
    q1 = st.radio("이 챗봇은 문제 해결 능력을 가진 존재라고 느꼈다.", scale)
    q2 = st.radio("이 챗봇은 감정을 이해한다고 느꼈다.", scale)
    q3 = st.radio("이 챗봇의 말투는 상황에 적절했다.", scale)
    q4 = st.radio("나는 이 챗봇에 대해 전반적으로 긍정적인 인상을 받았다.", scale)
    q5 = st.radio("나는 이 챗봇을 다시 사용하고 싶다.", scale)
    q6 = st.radio("이 챗봇은 유용한 정보를 제공했다.", scale)

    save_chat = st.checkbox("✅ 대화 내용도 함께 저장하겠습니다")

    # --------------------------------------------------
    # 제출 버튼
    # --------------------------------------------------
    if st.button("제출 및 저장"):

        # -------------------------------
        # 유효성 검사
        # -------------------------------
        if (
            demo_gender == "선택 안 함" or
            demo_age == "선택 안 함" or
            demo_edu == "선택 안 함" or
            demo_job.strip() == "" or
            q1 == "선택 안 함" or
            q2 == "선택 안 함" or
            q3 == "선택 안 함" or
            q4 == "선택 안 함" or
            q5 == "선택 안 함" or
            q6 == "선택 안 함"
        ):
            st.warning("⚠️ 모든 항목을 빠짐없이 입력해 주세요. 빈 항목이 있으면 저장되지 않습니다.")

        else:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # 🟡 1. 설문 응답 저장 (survey 시트)
            survey_row = [
                timestamp,
                st.session_state.user_id,
                st.session_state.style_condition,
                st.session_state.power_condition,
                st.session_state.get("final_text", ""),  # 최종확정 내용
                demo_gender,
                demo_age,
                demo_edu,
                demo_job,
                q1, q2, q3, q4, q5, q6
            ]

            survey_ws.append_row(survey_row, value_input_option="USER_ENTERED")

            # 🟡 2. 대화 내용 저장 (conversation 시트)
            if save_chat:
                for msg in st.session_state.messages:
                    conversation_ws.append_row([
                        timestamp,
                        st.session_state.user_id,
                        msg["role"],
                        msg["content"]
                    ], value_input_option="USER_ENTERED")

            st.success("✅ 설문과 대화가 각각 Google Sheets에 저장되었습니다!")
