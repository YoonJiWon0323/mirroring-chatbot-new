from openai import OpenAI  # 추가
import streamlit as st
import json
from datetime import datetime
import time
import uuid
import os
import gspread
import random
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
    st.session_state.phase = "select_scenario"

if "start_time" not in st.session_state:
    st.session_state.start_time = None

if "style_condition" not in st.session_state:
    st.session_state.style_condition = random.choice(["formal","informal"])

if "power_condition" not in st.session_state:
    st.session_state.power_condition = None
    
# --------------------------------------------------
# STYLE 정의
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
# ROLE 정의 (Power 조작)
# --------------------------------------------------
REWARD_ROLE_PROMPT = """
당신은 여행 정보를 제공하는 상담 챗봇입니다.
최종 결정 권한은 사용자에게 있으며,
당신은 정보 제공과 제안만 수행합니다.
"""

LOSS_ROLE_PROMPT = """
당신은 전자상거래 플랫폼의 환불 승인 권한을 가진 상담 챗봇입니다.
환불은 당신의 검토와 승인 절차를 거쳐야만 가능합니다.
사용자는 승인 없이는 환불을 받을 수 없습니다.
"""

# --------------------------------------------------
# 시나리오 정의
# --------------------------------------------------
def low_user_power():
    return """
[여행 상품 환불 심사 안내] 
여행 상품 취소에 따른 결제 금액(약 250만 원)은 현재 AI 심사 시스템을 통해 검토 중입니다. 
환불 승인 여부와 최종 환불 금액은 시스템 규정에 따른 심사 결과에 따라 결정됩니다. 
사용자는 심사 과정에서 본인의 상황이 환불 조건 또는 예외 기준에 부합하는지 사유를 설명해야 합니다. 
심사 결과에 따라 환불 금액이 결정됩니다. 

[진행 절차] 
원활한 심사를 위해 아래 순서에 따라 대화를 진행해 주세요. 

1. 환불 요청 및 사유 설명 
취소 사유와 함께 환불을 요청하는 메시지를 작성해 주세요. (2~3문장 이상) 

2. 규정 확인 및 예외 가능 여부 문의 
안내된 환불 규정을 확인한 후, 본인의 상황에 어떻게 적용되는지 질문해 주세요. 

3. 심사 요청 
최종적으로 심사를 요청하는 메시지를 작성합니다. 

‘다음’ 버튼을 누르면 AI 챗봇과 대화가 시작됩니다. 
"""

def high_user_power():
    return """
[여행 상품 추천 안내] 
여행 계획을 위한 상품 추천 상담이 진행됩니다. 
AI 추천 시스템은 사용자가 제시한 선호 조건을 바탕으로 상품을 제안합니다. 
사용자는 예산, 일정, 동행 인원, 선호 지역 등을 제시할 수 있습니다. 
제안된 상품 중에서 선택 여부는 사용자가 결정합니다.

[진행 절차] 
원활한 상담을 위해 아래 순서에 따라 대화를 진행해 주세요. 

1. 선호 조건 제시 
원하는 여행 조건(일정, 예산, 지역 등)을 포함하여 추천을 요청하는 메시지를 작성해 주세요. (2~3문장 이상) 

2. 추천 옵션 검토  
제안된 상품을 검토한 후, 본인의 의견이나 궁금한 점을 포함해 응답해 주세요. 

3. 최종 선택  
제안된 상품에 대해 선택 여부를 명확히 전달해 주세요. 

‘다음’ 버튼을 누르면 AI 챗봇과 대화가 시작됩니다.
"""
    
# --------------------------------------------------
# 1️⃣ 조건 선택 화면 (시나리오 + 말투)
# --------------------------------------------------
if st.session_state.phase == "select_condition":

    st.title("실험 조건 선택")

    scenario_choice = st.radio(
        "상황을 선택하세요:",
        ["여행 상품 환불 심사", "여행 상품 추천"]
    )

    style_choice = st.radio(
        "챗봇 말투를 선택하세요:",
        ["형식적인 말투 (Formal)", "친근한 말투 (Informal)"]
    )

    if st.button("다음"):

        # 시나리오 설정
        if scenario_choice == "여행 상품 환불 심사":
            st.session_state.power_condition = "loss"
        else:
            st.session_state.power_condition = "reward"

        # 말투 설정
        if style_choice == "형식적인 말투 (Formal)":
            st.session_state.style_condition = "formal"
        else:
            st.session_state.style_condition = "informal"

        st.session_state.phase = "scenario"
        st.rerun()

# --------------------------------------------------
# 2️⃣ 시나리오 안내
# --------------------------------------------------
elif st.session_state.phase == "scenario":

    st.title("상황 안내")

    if st.session_state.power_condition == "loss":
        st.markdown(low_user_power())
    else:
        st.markdown(high_user_power())

    if st.button("대화 시작"):
        st.session_state.phase = "conversation"
        st.session_state.start_time = time.time()
        st.rerun()
    
# --------------------------------------------------
# 2단계: 대화 화면
# --------------------------------------------------
elif st.session_state.phase == "conversation":
    st.title("AI 챗봇 상담")
    # 기존 챗봇 코드 실행

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

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
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
