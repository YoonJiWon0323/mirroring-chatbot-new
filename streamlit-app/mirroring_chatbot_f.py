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
    st.session_state.spreadsheet = gc.open_by_key("1J9_hUfp4KIvZMfu7grEKmhbnScNPc91PKgWD4cZPIwE")
    st.session_state.survey_ws = st.session_state.spreadsheet.worksheet("survey")
    st.session_state.conversation_ws = st.session_state.spreadsheet.worksheet("conversation")

spreadsheet = st.session_state.spreadsheet
survey_ws = st.session_state.survey_ws
conversation_ws = st.session_state.conversation_ws

# 시트가 비어 있다면 헤더 자동 삽입
insert_headers_if_empty(survey_ws, [
    "timestamp", "user_id", "mode",
    "gender", "age", "education", "job",
    # Moderator: AI Exposure
    "ae1", "ae2", "ae3", "ae4",
    # Mediator 1: Social Presence
    "sp1", "sp2", "sp3", "sp4", "sp5",
    # Mediator 2: Perceived Warmth
    "pw1", "pw2", "pw3", "pw4",
    # Mediator 3: Perceived Competence
    "pc1", "pc2", "pc3", "pc4",
    # Mediator 4: Trust
    "tr1", "tr2", "tr3",
    # DV: Continuance Usage Intention
    "ci1", "ci2", "ci3", "ci4",
    # Style summary
    "style_prompt"
])

insert_headers_if_empty(conversation_ws, [
    "timestamp", "user_id", "role", "message"
])

# 세션 초기화
if "messages" not in st.session_state:
    st.session_state.messages = []
if "user_history" not in st.session_state:
    st.session_state.user_history = []
if st.session_state.get("phase") == "mode_selection":
    st.session_state.user_history = []
    st.session_state.style_prompt = ""
if "style_prompt" not in st.session_state:
    st.session_state.style_prompt = ""
if "phase" not in st.session_state:
    st.session_state.phase = "mode_selection"
if "consent_given" not in st.session_state:
    st.session_state.consent_given = False
if "start_time" not in st.session_state:
    st.session_state.start_time = None
if "user_id" not in st.session_state:
    st.session_state.user_id = str(uuid.uuid4())[:8]

# 파트 0: 모드 선택
if st.session_state.phase == "mode_selection":
    st.subheader("시작하기 전에 한 가지를 선택해 주세요:")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("옵션 A"):
            st.session_state.chatbot_mode = "fixed"
            st.session_state.phase = "moderator_survey"
            st.rerun()
    with col2:
        if st.button("옵션 B"):
            st.session_state.chatbot_mode = "mirroring"
            st.session_state.phase = "moderator_survey"
            st.rerun()

# 파트 0.5: Moderator(AI Exposure) 설문
elif st.session_state.phase == "moderator_survey":
    st.subheader("AI 사용 경험에 대해 알려주세요 (AI Exposure)")
    scale = ["선택 안 함", "전혀 아니다", "아니다", "보통이다", "그렇다", "매우 그렇다"]

    ae = [st.radio(q, scale) for q in [
        "나는 AI 기반 기기나 서비스를 자주 사용한다.",
        "AI는 내 일상생활에서 중요한 부분을 차지한다.",
        "나는 AI를 자주 활용한다.",
        "나는 일상생활에서 AI 기술에 익숙하다."
    ]]

    if st.button("다음 단계로 이동"):
        if any(v == "선택 안 함" for v in ae):
            st.warning("⚠️ 모든 문항에 응답해 주세요.")
            st.stop()

        st.session_state.ai_exposure = ae
        st.session_state.phase = "style_collection"
        st.rerun()

# 말투 분석
if "chatbot_mode" in st.session_state:
    def update_style_prompt():
        history = "\n".join(st.session_state.user_history[-3:])
        prompt = f"""Analyze the user's writing style based on the following utterances:\n{history}\n\nSummarize the user's tone, formality, and personality. Be concise, and express the tone in Korean if possible."""
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}]
        )
        st.session_state.style_prompt = response.choices[0].message.content

# 파트 1: 말투 수집
if st.session_state.get("phase") == "style_collection":
    if "collection_index" not in st.session_state:
        st.session_state.collection_index = 0
    if st.session_state.collection_index == 0:
        st.session_state.messages = []
        initial_prompt = "안녕하세요! 오늘 하루 어땠는지 궁금해요. 날씨나 기분 같은 걸 말해줘요 :)"
        st.session_state.messages.append({"role": "assistant", "content": initial_prompt})
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
    user_input = st.chat_input("챗봇과 대화해보세요")
    if user_input:
        st.session_state.messages.append({"role": "user", "content": user_input})
        st.session_state.user_history.append(user_input)
        with st.chat_message("user"):
            st.markdown(user_input)
        if st.session_state.collection_index < 2:
            system_prompt = "You are a friendly chatbot collecting natural language samples from the user. Ask a new, casual and personal question each time based on their last reply."
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "system", "content": system_prompt}, *st.session_state.messages]
            )
            bot_reply = response.choices[0].message.content
            st.session_state.messages.append({"role": "assistant", "content": bot_reply})
            with st.chat_message("assistant"):
                st.markdown(bot_reply)
            st.session_state.collection_index += 1
        else:
            update_style_prompt()
            st.session_state.phase = "pre_task_notice"
            st.rerun()

# 파트 1.5: 과업 안내
elif st.session_state.get("phase") == "pre_task_notice":
    if st.session_state.chatbot_mode == "fixed":
        notice_text = "안녕하세요. 챗봇과 함께 3분 동안 여행 계획을 세워보세요. 궁금한 점이 있으면 언제든지 물어보셔도 됩니다."
    else:
        prompt = f"다음 말투에 맞춰, 사용자에게 3분간 여행 계획 대화를 시작하도록 제안하는 한국어 문장을 만들어줘.\n말투 요약: {st.session_state.style_prompt}"
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}]
        )
        notice_text = response.choices[0].message.content.strip()
    st.session_state.notice_text = notice_text
    st.session_state.phase = "task_conversation"
    st.session_state.start_time = time.time()
    st.rerun()

# 파트 2: 여행 대화
elif st.session_state.get("phase") == "task_conversation":
    if "notice_inserted" not in st.session_state:
        st.session_state.messages.append({"role": "assistant", "content": st.session_state.notice_text})
        st.session_state.notice_inserted = True
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
    user_input = st.chat_input("챗봇과 여행 계획을 대화해보세요")
    if user_input:
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)
        system_instruction = (
            "You are a formal, concise Korean chatbot. Respond politely in 존댓말, and avoid casual or playful expressions."
            if st.session_state.chatbot_mode == "fixed"
            else f"""You are a Korean chatbot that mirrors the user's style.\nHere is the style guide:\n{st.session_state.style_prompt}\nRespond naturally in that style."""
        )
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": system_instruction}, *st.session_state.messages[-6:]]
        )
        bot_reply = response.choices[0].message.content
        st.session_state.messages.append({"role": "assistant", "content": bot_reply})
        with st.chat_message("assistant"):
            st.markdown(bot_reply)
    if st.session_state.start_time and time.time() - st.session_state.start_time > 180:
        st.markdown("⏰ 시간이 다 되어 챗봇 대화를 종료합니다. 설문지로 이동합니다.")
        time.sleep(5)
        st.session_state.phase = "consent"
        st.rerun()

# 파트 3: 설문 + Google Sheets 저장
elif st.session_state.get("phase") == "consent":
    st.subheader("🔒 설문 응답")
    scale = ["선택 안 함", "전혀 아니다", "아니다", "보통이다", "그렇다", "매우 그렇다"]

    # ----------------------------
    # Mediator 1: Social Presence
    # ----------------------------
    sp = [st.radio(q, scale) for q in [
        "이 챗봇과의 상호작용에서 사람과 대화하는 듯한 느낌이 들었다.",
        "이 챗봇과의 상호작용에서 개인적인 느낌이 들었다.",
        "이 챗봇과의 상호작용이 사교적이라고 느껴졌다.",
        "이 챗봇과의 상호작용에서 인간적인 따뜻함이 느껴졌다.",
        "이 챗봇이 민감하고 배려 있게 반응한다고 느껴졌다."
    ]]

    # ----------------------------
    # Mediator 2: Perceived Warmth
    # ----------------------------
    pw = [st.radio(q, scale) for q in [
        "이 챗봇은 따뜻하게 느껴진다.",
        "이 챗봇은 상냥하게 느껴진다.",
        "이 챗봇은 친근하게 느껴진다.",
        "이 챗봇은 진실되게 느껴진다."
    ]]

    # ----------------------------
    # Mediator 3: Perceived Competence
    # ----------------------------
    pc = [st.radio(q, scale) for q in [
        "이 챗봇은 서비스 제공 과정에서 유능하게 느껴진다.",
        "이 챗봇은 서비스 제공 과정에서 숙련되어 있다고 느껴진다.",
        "이 챗봇은 서비스 제공 과정에서 지능적이라고 느껴진다.",
        "이 챗봇은 서비스 제공 과정에서 능력이 있다고 느껴진다."
    ]]

    # ----------------------------
    # Mediator 4: Trust
    # ----------------------------
    tr = [st.radio(q, scale) for q in [
        "나는 이 챗봇을 신뢰한다.",
        "나는 이 챗봇이 말하는 내용을 믿는다.",
        "이 챗봇은 사실에 기반한 진실된 정보를 제공한다고 느낀다."
    ]]

    # ----------------------------
    # DV: Continuance Usage Intention
    # ----------------------------
    ci = [st.radio(q, scale) for q in [
        "앞으로도 이 챗봇과 계속 상호작용하고 싶다.",
        "앞으로도 이 챗봇이 제공하는 서비스를 계속 이용하고 싶다.",
        "사람 상담보다 이 챗봇을 계속 사용할 의향이 있다.",
        "미래에도 이 챗봇을 계속 사용할 것이다."
    ]]

    # 인구통계
    demo_gender = st.radio("성별:", ["선택 안 함", "남성", "여성", "기타"])
    demo_age = st.selectbox("연령대:", ["선택 안 함", "10대", "20대", "30대", "40대", "50대 이상"])
    demo_edu = st.selectbox("학력:", ["선택 안 함", "고졸 이하", "대학 재학·졸업", "대학원 재학·졸업"])
    demo_job = st.text_input("직업을 입력해 주세요:")

    save_chat = st.checkbox("✅ 대화 내용도 함께 저장하겠습니다")

    if st.button("제출 및 저장"):

        if (
            demo_gender == "선택 안 함" or
            demo_age == "선택 안 함" or
            demo_edu == "선택 안 함" or
            demo_job.strip() == ""
        ):
            st.warning("⚠️ 인구통계 항목을 모두 입력해 주세요.")
            st.stop()


        # 응답 체크
        if any(v == "선택 안 함" for v in (sp + pw + pc + tr + ci)):
            st.warning("⚠️ 모든 설문 문항에 응답해 주세요.")
            st.stop()

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        mode_label = "A" if st.session_state.chatbot_mode == "fixed" else "B"

        survey_row = [
            timestamp,
            st.session_state.user_id,
            mode_label,
            demo_gender, demo_age, demo_edu, demo_job,
            # Moderator
            *st.session_state.ai_exposure,
            # Mediators & DV
            *sp, *pw, *pc, *tr, *ci,
            st.session_state.style_prompt
        ]
        survey_ws.append_row(survey_row, value_input_option="USER_ENTERED")

        if save_chat:
            for msg in st.session_state.messages:
                conversation_ws.append_row([
                    timestamp,
                    st.session_state.user_id,
                    msg["role"],
                    msg["content"]
                ], value_input_option="USER_ENTERED")

        st.success("✅ 설문과 대화가 성공적으로 저장되었습니다!")

