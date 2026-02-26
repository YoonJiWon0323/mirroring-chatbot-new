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

    # 실험 조건
    "scenario",
    "tone",

    # 인구통계
    "gender",
    "age",
    "education",
    "job",

    # 조작점검
    "power1","power2","power3",
    "tone1","tone2","tone3",

    # 종속
    "sat1","sat2","sat3",

    # 매개
    "app1","app2","app3",

    # 통제
    "rude1","rude2",
    "comp1","comp2","comp3",

    # AI 노출
    "exp1","exp2","exp3","exp4"
])

insert_headers_if_empty(conversation_ws, [
    "timestamp",
    "user_id",
    "role",
    "message"
])

# --------------------------------------------------
# 세션 초기화
# --------------------------------------------------
if "user_id" not in st.session_state:
    st.session_state.user_id = str(uuid.uuid4())[:8]

if "phase" not in st.session_state:
    st.session_state.phase = "select_scenario"

if "scenario" not in st.session_state:
    st.session_state.scenario = None

if "tone" not in st.session_state:
    st.session_state.tone = None

if "step_index" not in st.session_state:
    st.session_state.step_index = 0

if "chat_log" not in st.session_state:
    st.session_state.chat_log = []

if "last_role" not in st.session_state:
    st.session_state.last_role = None
    
# --------------------------------------------------
# 시나리오 안
# --------------------------------------------------
def scenario_text(scenario):
    if scenario == "refund":
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

    else:
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

# ---------------- 단계 스크립트 ----------------
SCRIPT = {
"refund_격식체": [
"① 심사 시스템에 연결되었습니다.",
"② 250만 원 환불 심사를 시작합니다.",
"③ 취소 사유를 상세히 입력하십시오.",
"④ 수수료 75만 원이 발생합니다.",
"⑤ 서류 제출 시 재심사가 가능합니다.",
"⑥ 심사 요청 여부를 확정하십시오.",
"⑦ 심사 승인 대기 처리되었습니다."
],
"refund_해요체": [
"① 심사 시스템 연결됐어요.",
"② 250만 원 환불 심사 시작할게요.",
"③ 취소 이유 자세히 적어줘요.",
"④ 수수료 75만 원 나오네요.",
"⑤ 서류 내면 다시 심사 가능해요.",
"⑥ 심사 요청할지 결정해봐요.",
"⑦ 심사 승인 대기로 처리됐어요."
],
"refund_반말체": [
"① 심사 시스템 연결됐어.",
"② 250만 원 환불 심사 시작할게.",
"③ 취소 이유 자세히 적어.",
"④ 수수료 75만 원 나와.",
"⑤ 서류 내면 다시 심사 가능해.",
"⑥ 심사 요청할지 결정해.",
"⑦ 심사 승인 대기로 처리됐어."
],
"recommend_격식체": [
"① 추천 상담 시스템에 연결되었습니다.",
"② AI 추천 시스템이 사용자의 조건을 기반으로 상품을 제안합니다.",
"③ 여행 일정과 예산, 선호 지역을 구체적으로 제시하시기 바랍니다.",
"④ 제안된 상품의 세부 내용을 확인하시기 바랍니다.",
"⑤ 상품을 비교·검토한 후 선택 여부를 결정하시기 바랍니다.",
"⑥ 선택 결과에 따라 후속 절차가 안내됩니다."
],
"recommend_해요체": [
"① 추천 상담 시스템에 연결됐어요.",
"② AI 추천 시스템이 사용자의 조건을 바탕으로 상품을 추천해 드려요.",
"③ 여행 일정이나 예산, 원하는 지역을 자세히 알려 주세요.",
"④ 제안된 상품 내용 확인해 주세요.",
"⑤ 상품 비교해 본 뒤 선택할지 정해 주세요.",
"⑥ 선택 결과에 따라 다음 절차를 안내해 드릴게요."
],
"recommend_반말체": [
"① 추천 상담 시스템 연결됐어.",
"② AI 추천 시스템이 사용자 조건을 바탕으로 상품 추천할게.",
"③ 여행 일정이랑 예산, 원하는 지역 자세히 알려 줘.",
"④ 제안된 상품 내용 확인해.",
"⑤ 상품 비교해 본 뒤 선택할지 정해.",
"⑥ 선택 결과에 따라 다음 절차 안내할게."
]
}
    
# ---------------- 질문 감지 ----------------
def is_question(text):
    keywords = ["?", "왜", "어떻게", "무엇", "가능"]
    return any(k in text for k in keywords)


# ==================================================
# 1️⃣ 상황 선택 화면
# ==================================================
if st.session_state.phase == "select_scenario":

    st.title("상황 선택")

    scenario = st.radio("상황을 선택하세요:",
                        ["여행 상품 환불 심사", "여행 상품 추천"])

    if st.button("다음"):
        st.session_state.scenario = "refund" if scenario == "여행 상품 환불 심사" else "recommend"
        st.session_state.phase = "select_tone"
        st.rerun()

# --------------------------------------------------
# 2️⃣ 시나리오 안내
# --------------------------------------------------
elif st.session_state.phase == "scenario":

    st.title("상황 안내")

    if st.button("대화 시작"):
        st.session_state.phase = "conversation"
        st.session_state.start_time = time.time()
        st.rerun()

# ==================================================
# 2️⃣ 말투 선택 화면
# ==================================================
elif st.session_state.phase == "select_tone":

    st.title("챗봇 말투 선택")

    tone = st.radio("말투를 선택하세요:",
                    ["격식체", "해요체", "반말체"])

    if st.button("다음"):
        st.session_state.tone = tone
        st.session_state.phase = "scenario"
        st.rerun()

# ==================================================
# 3️⃣ 시나리오 안내 화면
# ==================================================
elif st.session_state.phase == "scenario":

    st.title("상황 안내")
    st.markdown(scenario_text(st.session_state.scenario))

    if st.button("대화 시작"):
        st.session_state.step_index = 0
        st.session_state.chat_log = []
        st.session_state.last_role = None
        st.session_state.phase = "conversation"
        st.rerun()


# ==================================================
# 4️⃣ 단계 고정 대화
# ==================================================
elif st.session_state.phase == "conversation":

    key = f"{st.session_state.scenario}_{st.session_state.tone}"
    script = SCRIPT[key]

    if st.session_state.last_role != "assistant" and st.session_state.step_index < len(script):

        assistant_text = script[st.session_state.step_index]
        st.chat_message("assistant").write(assistant_text)

        st.session_state.chat_log.append(("assistant", assistant_text))
        st.session_state.last_role = "assistant"

    user_input = st.chat_input("입력하세요")

    if user_input:

        st.chat_message("user").write(user_input)
        st.session_state.chat_log.append(("user", user_input))

        if is_question(user_input):

            # 질문이면 GPT 보조응답
            response = client.chat.completions.create(
                model="gpt-4o",
                temperature=0,
                messages=[
                    {"role":"system","content":f"{st.session_state.tone} 말투로만 답하십시오."},
                    {"role":"user","content":user_input}
                ]
            )

            reply = response.choices[0].message.content
            st.chat_message("assistant").write(reply)
            st.session_state.chat_log.append(("assistant", reply))
            st.session_state.last_role = "assistant"

        else:
            st.session_state.step_index += 1
            st.session_state.last_role = "user"

            if st.session_state.step_index >= len(script):
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
    # 1️⃣ 조작점검 – 권력 인지
    # -------------------------------
    power1 = st.radio("나는 이 대화에서 최종 결정을 내릴 수 있는 입장이었다.", scale, index=None)
    power2 = st.radio("이 상황에서 결정권은 나에게 있었다.", scale, index=None)
    power3 = st.radio("AI가 아니라 내가 결과를 통제한다고 느꼈다.", scale, index=None)

    # -------------------------------
    # 2️⃣ 조작점검 – 말투 인지
    # -------------------------------
    tone1 = st.radio("AI의 말투는 격식을 갖춘 공식적인 표현이었다.", scale, index=None)
    tone2 = st.radio("AI의 말투는 일상적인 표현에 가까웠다.", scale, index=None)
    tone3 = st.radio("AI의 언어는 형식적이었다.", scale, index=None)

    # -------------------------------
    # 3️⃣ 종속변수 – 만족도
    # -------------------------------
    sat1 = st.radio("전반적으로 이 AI와의 대화에 만족한다.", scale, index=None)
    sat2 = st.radio("이 상호작용은 긍정적인 경험이었다.", scale, index=None)
    sat3 = st.radio("다시 이런 상황이 있다면 이 AI와 대화하고 싶다.", scale, index=None)

    # -------------------------------
    # 4️⃣ 매개 – 적절성
    # -------------------------------
    app1 = st.radio("이 상황에서 AI의 말투는 적절했다.", scale, index=None)
    app2 = st.radio("AI의 말투는 이 상황에 잘 어울렸다.", scale, index=None)
    app3 = st.radio("AI의 표현 방식은 상황과 조화를 이루었다.", scale, index=None)

    # -------------------------------
    # 5️⃣ 통제 – 무례함
    # -------------------------------
    rude1 = st.radio("AI의 말투는 무례하게 느껴졌다.", scale, index=None)
    rude2 = st.radio("AI의 표현은 나를 충분히 존중하지 않는다고 느꼈다.", scale, index=None)

    # -------------------------------
    # 6️⃣ 통제 – 전문성
    # -------------------------------
    comp1 = st.radio("AI는 전문적으로 보였다.", scale, index=None)
    comp2 = st.radio("AI는 신뢰할 수 있는 역량이 있어 보였다.", scale, index=None)
    comp3 = st.radio("AI는 정확한 판단을 내릴 수 있을 것 같았다.", scale, index=None)

    # -------------------------------
    # 7️⃣ 통제 – AI 노출도
    # -------------------------------
    exp1 = st.radio("나는 AI 기반 기기나 서비스를 자주 이용한다.", scale, index=None)
    exp2 = st.radio("AI는 내 일상생활에서 중요한 부분을 차지한다.", scale, index=None)
    exp3 = st.radio("나는 AI를 자주 사용한다.", scale, index=None)
    exp4 = st.radio("나는 일상생활에서 AI 기술에 익숙한 편이다.", scale, index=None)

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

            power1 is None or power2 is None or power3 is None or
            tone1 is None or tone2 is None or tone3 is None or
            sat1 is None or sat2 is None or sat3 is None or
            app1 is None or app2 is None or app3 is None or
            rude1 is None or rude2 is None or
            comp1 is None or comp2 is None or comp3 is None or
            exp1 is None or exp2 is None or exp3 is None or exp4 is None
        ):
            st.warning("⚠️ 모든 항목에 응답해 주세요. 응답하지 않은 항목이 있습니다.")
        else:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # 🟡 1. 설문 응답 저장 (survey 시트)
            survey_row = [
                timestamp,
                st.session_state.user_id,

                # 실험 조건
                st.session_state.scenario,
                st.session_state.tone,

                # 인구통계
                demo_gender,
                demo_age,
                demo_edu,
                demo_job,

                # 조작점검 – 권력
                power1, power2, power3,

                # 조작점검 – 말투
                tone1, tone2, tone3,

                # 종속
                sat1, sat2, sat3,

                # 매개
                app1, app2, app3,

                # 통제 – 무례함
                rude1, rude2,

                # 통제 – 전문성
                comp1, comp2, comp3,

                # AI 노출
                exp1, exp2, exp3, exp4
            ]

            survey_ws.append_row(survey_row, value_input_option="USER_ENTERED")

            # 🟡 2. 대화 내용 저장 (conversation 시트)
            if save_chat:
                for role, message in st.session_state.chat_log:
                    conversation_ws.append_row([
                        timestamp,
                        st.session_state.user_id,
                        role,
                        message
                    ], value_input_option="USER_ENTERED")

            st.success("✅ 설문과 대화가 각각 Google Sheets에 저장되었습니다!")
