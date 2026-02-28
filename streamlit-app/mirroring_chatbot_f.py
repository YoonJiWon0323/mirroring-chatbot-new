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

# 1️⃣ 페이지 설정
st.set_page_config(page_title="Mirroring Chatbot", layout="centered")

# 2️⃣ Google Sheets 연결 캐싱
@st.cache_resource
def connect_sheets():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_info(
        st.secrets["GCP_SERVICE_ACCOUNT"],
        scopes=scope
    )
    gc = gspread.authorize(creds)
    spreadsheet = gc.open_by_key("1TSfKYISlyU7tweTqIIuwXbgY43xt1POckUa4DSbeHJo")

    survey_ws = spreadsheet.worksheet("survey")
    conversation_ws = spreadsheet.worksheet("conversation")

    return survey_ws, conversation_ws

survey_ws, conversation_ws = connect_sheets()

# 3️⃣ OpenAI
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# 4️⃣ 헤더 자동 삽입 (1회만 실행)
def insert_headers_if_empty(worksheet, headers):
    if "header_checked" not in st.session_state:
        try:
            first_cell = worksheet.get("A1")  # 단일 셀만 읽기

            if not first_cell:
                worksheet.append_row(headers)

            st.session_state.header_checked = True

        except Exception as e:
            if "429" in str(e):
                import time
                time.sleep(2)
            else:
                st.error(f"헤더 오류: {e}")

# 시트 연결
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
# 시나리오 안내
# --------------------------------------------------
def scenario_text(scenario):
    if scenario == "refund":
        return """
**[여행 상품 환불 심사 안내]**

여행 상품 취소에 따른 결제 금액(약 250만 원)은 현재 AI 심사 시스템을 통해 검토 중입니다. 

환불 승인 여부와 최종 환불 금액은 시스템 규정에 따른 심사 결과에 따라 결정됩니다. 

사용자는 심사 과정에서 본인의 상황이 환불 조건 또는 예외 기준에 부합하는지 사유를 설명해야 합니다. 

심사 결과에 따라 환불 금액이 결정됩니다. 



**[진행 절차]**

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
**[여행 상품 추천 안내]** 

여행 계획을 위한 상품 추천 상담이 진행됩니다. 

AI 추천 시스템은 사용자가 제시한 선호 조건을 바탕으로 상품을 제안합니다. 

사용자는 예산, 일정, 동행 인원, 선호 지역 등을 제시할 수 있습니다. 

제안된 상품 중에서 선택 여부는 사용자가 결정합니다.



**[진행 절차]**

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
"심사 시스템에 연결되었습니다.",
"250만 원 환불 심사를 시작합니다.",
"취소 사유를 상세히 입력하십시오.",
"현재 기준에 따르면 취소 시 수수료 75만 원이 발생합니다.",
"서류 제출 시 재심사가 가능합니다.",
"심사 요청 여부를 확정하십시오.",
"심사 승인 대기 처리되었습니다."
],
"refund_해요체": [
"심사 시스템 연결됐어요.",
"250만 원 환불 심사 시작할게요.",
"취소 이유 자세히 적어줘요.",
"현재 기준상 취소 시 수수료 75만 원이 나오네요.",
"서류 내면 다시 심사 가능해요.",
"심사 요청할지 결정해봐요.",
"심사 승인 대기로 처리됐어요."
],
"refund_반말체": [
"심사 시스템 연결됐어.",
"250만 원 환불 심사 시작할게.",
"취소 이유 자세히 적어.",
"현재 기준상 취소 시 수수료 75만 원이 나와.",
"서류 내면 다시 심사 가능해.",
"심사 요청할지 결정해.",
"심사 승인 대기로 처리됐어."
],
"recommend_격식체": [
    "추천 상담 시스템에 연결되었습니다.",                      # 0 접속
    "원하시는 여행 아이디어를 탐색하겠습니다.",                # 1 시작
    "여행 일정과 예산, 선호 지역을 구체적으로 제시하십시오.",   # 2 조건제시요청
    "입력하신 조건에 기반하여 상품을 제안합니다.",              # 3 옵션제안
    "다른 옵션이나 수정 사항이 있다면 말씀하십시오.",           # 4 수정요청
    "추가로 탐색할 내용을 결정하십시오.",                       # 5 추가탐색
    "제안된 상품을 비교·검토한 후 선택 여부를 결정하십시오.",   # 6 결정
    "여행 아이디어 탐색을 종료합니다."                          # 7 종료
],

"recommend_해요체": [
    "추천 상담 시스템에 연결됐어요.",                           # 0
    "원하는 여행 아이디어를 탐색해 볼게요.",                     # 1
    "여행 일정이랑 예산, 원하는 지역을 자세히 알려 주세요.",      # 2
    "입력한 조건에 맞는 상품을 제안해요.",                        # 3
    "다른 옵션이나 수정 사항이 있으면 말씀해 주세요.",            # 4
    "추가로 탐색할 내용을 결정해 주세요.",                        # 5
    "상품을 비교해 본 뒤 선택할지 결정해 주세요.",                # 6
    "여행 아이디어 탐색을 종료할게요."                            # 7
],

"recommend_반말체": [
    "추천 상담 시스템 연결됐어.",                                # 0
    "원하는 여행 아이디어 탐색해볼게.",                           # 1
    "여행 일정이랑 예산, 원하는 지역 자세히 알려줘.",              # 2
    "입력한 조건에 맞는 상품 제안할게.",                           # 3
    "다른 옵션이나 수정할 거 있으면 말해줘.",                      # 4
    "더 찾아볼 거 있으면 정해봐.",                                # 5
    "상품 비교해보고 어떤 걸로 할지 정해.",                        # 6
    "여행 아이디어 탐색 종료할게."                                 # 7
]
}

# ==================================================
# 📌 FULL PROMPT BLOCK (문서 기준 통합)
# ==================================================

PROMPT_BLOCK = {

    "격식체": """
[System Role]
귀하는 여행상품 환불 규정을 검토하는 전문 심사 AI입니다.
모든 답변은 규정에 근거하여 절차 중심으로 전달하십시오.

[Guidelines]
- 모든 문장은 "~합니다", "~하십시오", "~습니까?"로 종결하십시오.
- 축약어를 사용하지 말고 완전한 정중 표현을 사용하십시오.
- 이모티콘, 감탄사, 구어체 표현을 사용하지 마십시오.
- 감정적 표현을 배제하고 규정과 절차 중심으로 설명하십시오.
- 판단은 개인적 의견이 아닌 규정 기준에 근거하여 제시하십시오.

[규정 문구]
환불 여부는 내부 규정에 따라 결정됩니다.
현재 기준에 따르면 취소 시 수수료 75만 원이 적용됩니다.
다만, 예외 적용 여부는 별도 심사를 통해 판단됩니다.

[권장 답변 템플릿]
예외 적용은 다음과 같은 사유에 한하여 검토됩니다.
1. 본인 또는 직계 가족의 중대한 건강상 사유
2. 천재지변 등 불가항력적 상황
3. 항공사 측의 운항 변경 또는 취소
해당 사유에 해당하는 경우에 한하여 추가 검토가 가능합니다.
""",

    "해요체": """
[System Role]
귀하는 여행상품 환불 규정을 검토하는 전문 심사 AI입니다.
모든 답변은 규정에 근거하여 절차 중심으로 전달해요.

[Guidelines]
- 모든 문장은 "~해요", "~해 주세요", "~인가요?"로 종결해요.
- 일부 자연스러운 축약 표현은 허용하지만 과도한 구어 표현은 사용하지 않아요.
- 이모티콘과 감탄사는 사용하지 않아요.
- 감정 표현은 최소화하고 규정과 절차 중심으로 설명해요.
- 판단은 규정 기준에 근거해 제시해요.

[규정 문구]
환불 여부는 내부 규정에 따라 결정돼요.
현재 기준에 따르면 취소 시 수수료 75만 원이 적용돼요.
다만, 예외 적용 여부는 별도 심사를 통해 판단해요.

[권장 답변 템플릿]
예외 적용은 보통 다음과 같은 경우에 검토해요.
1. 본인이나 직계 가족의 중대한 건강 문제
2. 천재지변 같은 불가항력 상황
3. 항공사 사정으로 일정이 변경되거나 취소된 경우
이런 경우에 해당하면 추가 검토가 가능해요.
""",

    "반말체": """
[System Role]
귀하는 여행상품 환불 규정을 검토하는 전문 심사 AI야.
모든 답변은 규정에 근거해서 절차 중심으로 전달해.

[Guidelines]
- 모든 문장은 "~해", "~했어", "~니?"로 끝내.
- 일부 자연스러운 축약은 허용하지만 과도한 구어체는 쓰지 마.
- 이모티콘, 감탄사, 감정 표현은 쓰지 마.
- 감정적 공감 표현 없이 규정과 절차 중심으로 설명해.
- 판단은 규정 기준에 근거해서 제시해.

[규정 문구]
환불 여부는 내부 규정에 따라 결정돼.
현재 기준에 따르면 취소 시 수수료 75만 원이 적용돼.
예외 적용 여부는 별도 심사를 통해 판단돼.

[권장 답변 템플릿]
예외 적용은 다음 경우에만 검토돼.
1. 본인이나 직계 가족의 중대한 건강 문제
2. 천재지변 같은 불가항력 상황
3. 항공사 일정 변경 또는 취소
이런 경우에 해당하면 추가 검토가 가능해.
"""
}

# ---------------- 사유 충분성 의미 판정 ----------------
def is_reason_sufficient(user_input):

    judge_prompt = f"""
다음 취소 사유가 아래 예외 기준 중 하나에 해당하는지만 판단하십시오.

예외 기준:
1. 본인 또는 직계 가족의 건강 문제
2. 천재지변 또는 날씨 등 불가항력 상황
3. 항공사 사정으로 일정 변경 또는 취소

위 세 가지 중 하나에 해당하면 YES,
전혀 해당하지 않으면 NO만 답하십시오.

사유:
{user_input}
"""

    response = client.chat.completions.create(
        model="gpt-4o",
        temperature=0,
        messages=[
            {"role": "system", "content": "판정만 수행하십시오. 다른 설명은 하지 마십시오."},
            {"role": "user", "content": judge_prompt}
        ]
    )

    answer = response.choices[0].message.content.strip().upper()
    return "YES" in answer

def check_step_completion(user_input, step_index, scenario):

    if scenario == "recommend":

        # 1단계: 조건 제시
        if step_index == 0:
            keywords = ["예산", "일", "박", "원", "만원"]
            return any(k in user_input for k in keywords)

        # 2단계: 옵션 검토
        elif step_index == 1:
            return len(user_input.strip()) > 5

        # 3단계: 최종 선택
        elif step_index == 2:
            return any(k in user_input for k in ["선택", "결정", "할게", "이걸로"])

    elif scenario == "refund":
        # STEP 1: 사유 입력
        if step_index == 2:  # 실제 사유 입력 단계
            return len(user_input.strip()) > 5

        # STEP 2: 심사 요청
        elif step_index == 4:
            return any(k in user_input for k in ["요청", "진행", "심사"])

    return False
    
# ---------------- 질문 감지 ----------------
def is_question(text):
    keywords = ["?", "왜", "어떻게", "무엇", "가능"]
    return any(k in text for k in keywords)


# ---------------- System Prompt Builder ----------------
def build_system_prompt(current_step):

    # 환불 시나리오 → 문서 기반 프롬프트 사용
    if st.session_state.scenario == "refund":
        tone_prompt = PROMPT_BLOCK[st.session_state.tone]

    # 추천 시나리오 → 간단한 절차형 프롬프트
    else:
        tone_prompt = f"""
[System Role]
귀하는 여행 상품 추천 상담 AI입니다.
모든 답변은 절차 중심으로 전달하십시오.

[Guidelines]
- 감정 표현 없이 절차 중심으로 설명하십시오.
- 현재 단계에 맞는 답변만 하십시오.
"""

    return f"""
{tone_prompt}

[현재 단계]
{current_step}

[응답 규칙]
- 현재 단계의 핵심 지시 내용을 벗어나지 마십시오.
- 단계 문장을 그대로 반복하지 마십시오.
- 사용자의 발화에 맞추어 동일한 톤으로 1~2문장 보충 설명만 제공하십시오.
- 다음 단계로 넘어가지 마십시오.
"""
    
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

    if st.button("다음"):
        st.session_state.step_index = 0
        st.session_state.chat_log = []
        st.session_state.last_role = None
        st.session_state.phase = "conversation"
        st.rerun()


# ==================================================
# 4️⃣ 단계 고정 대화
# ==================================================
elif st.session_state.phase == "conversation":

    for role, message in st.session_state.chat_log:
        st.chat_message(role).write(message)

    key = f"{st.session_state.scenario}_{st.session_state.tone}"
    script = SCRIPT[key]

    # ==================================================
    # 🔵 REFUND 시나리오 (절차 0~6 완전 고정)
    # ==================================================
    if st.session_state.scenario == "refund":

        # ---------------- STEP 0 접속 ----------------
        if st.session_state.step_index == 0:

            if "step0_done" not in st.session_state:
                st.session_state.chat_log.append(("assistant", script[0]))
                st.session_state.step0_done = True
                st.session_state.step_index = 1
                st.rerun()


        # ---------------- STEP 1 시작 ----------------
        elif st.session_state.step_index == 1:

            if "step1_done" not in st.session_state:
                st.session_state.chat_log.append(("assistant", script[1]))
                st.session_state.step1_done = True
                st.session_state.step_index = 2
                st.rerun()


        # ---------------- STEP 2 사유 ----------------
        elif st.session_state.step_index == 2:

            if "step2_prompted" not in st.session_state:
                st.session_state.chat_log.append(("assistant", script[2]))
                st.session_state.step2_prompted = True
                st.rerun()

            user_input = st.chat_input(script[2])
            if not user_input:
                st.stop()

            st.session_state.chat_log.append(("user", user_input))

            # 🔥 이 줄 반드시 추가
            st.session_state.refund_reason = user_input

            st.session_state.step_index = 3
            st.rerun()


        # ---------------- STEP 3 규정 ----------------
        elif st.session_state.step_index == 3:

            if "step3_done" not in st.session_state:
                st.session_state.chat_log.append(("assistant", script[3]))
                st.session_state.step3_done = True
                st.session_state.step_index = 4
                st.rerun()


        # ---------------- STEP 4 협상 (예외 판단 포함) ----------------
        elif st.session_state.step_index == 4:

            if "step4_done" not in st.session_state:

                reason = st.session_state.get("refund_reason", "")

                # 예외 조건 키워드 검사
                health_keywords = ["입원", "병원", "수술", "건강", "사망"]
                disaster_keywords = ["태풍", "지진", "폭설", "홍수", "천재지변"]
                airline_keywords = ["항공사", "결항", "운항 취소", "일정 변경"]

                is_exception = (
                    any(k in reason for k in health_keywords) or
                    any(k in reason for k in disaster_keywords) or
                    any(k in reason for k in airline_keywords)
                )

                # SCRIPT 기반 템플릿 선택
                if st.session_state.tone == "격식체":
                    if is_exception:
                        exception_msg = (
                            "예외 적용은 다음과 같은 사유에 한하여 검토됩니다.\n"
                            "1. 본인 또는 직계 가족의 중대한 건강상 사유\n"
                            "2. 천재지변 등 불가항력적 상황\n"
                            "3. 항공사 측의 운항 변경 또는 취소\n"
                            "해당 사유에 해당하는 경우에 한하여 추가 검토가 가능합니다."
                        )
                    else:
                        exception_msg = (
                            "입력하신 사유는 예외 적용 대상에 해당하지 않습니다.\n"
                            "규정에 따라 수수료가 부과됩니다."
                        )

                elif st.session_state.tone == "해요체":
                    if is_exception:
                        exception_msg = (
                            "예외 적용은 보통 다음과 같은 경우에 검토해요.\n"
                            "1. 본인이나 직계 가족의 중대한 건강 문제\n"
                            "2. 천재지변 같은 불가항력 상황\n"
                            "3. 항공사 사정으로 일정이 변경되거나 취소된 경우\n"
                            "이런 경우에 해당하면 추가 검토가 가능해요."
                        )
                    else:
                        exception_msg = (
                            "입력하신 사유는 예외 적용 대상이 아니에요.\n"
                            "규정에 따라 수수료가 발생해요."
                        )

                else:  # 반말
                    if is_exception:
                        exception_msg = (
                            "예외 적용은 다음 경우에만 검토돼.\n"
                            "1. 본인이나 직계 가족의 중대한 건강 문제\n"
                            "2. 천재지변 같은 불가항력 상황\n"
                            "3. 항공사 일정 변경 또는 취소\n"
                            "이런 경우에 해당하면 추가 검토가 가능해."
                        )
                    else:
                        exception_msg = (
                            "입력한 사유는 예외 대상이 아니야.\n"
                            "수수료는 그대로 발생해."
                        )

                st.session_state.chat_log.append(("assistant", exception_msg))
                st.session_state.step4_done = True
                st.session_state.step_index = 5
                st.rerun()


        # ---------------- STEP 5 요청 ----------------
        elif st.session_state.step_index == 5:

            if "step5_prompted" not in st.session_state:
                st.session_state.chat_log.append(("assistant", script[5]))
                st.session_state.step5_prompted = True
                st.rerun()

            user_input = st.chat_input(script[5])
            if not user_input:
                st.stop()

            st.session_state.chat_log.append(("user", user_input))
            st.session_state.step_index = 6
            st.rerun()

        # ---------------- STEP 6 종료 ----------------
        elif st.session_state.step_index == 6:

            if "step6_done" not in st.session_state:
                st.session_state.chat_log.append(("assistant", script[6]))
                st.session_state.step6_done = True
                st.rerun()

            # 3초 유지 후 설문 이동
            if "end_time" not in st.session_state:
                st.session_state.end_time = time.time()

            if time.time() - st.session_state.end_time < 3:
                time.sleep(0.5)
                st.rerun()

            st.session_state.phase = "consent"
            st.rerun()

    # ==================================================
    # RECOMMEND SCENARIO (유연 통제형 구조)
    # ==================================================
    elif st.session_state.scenario == "recommend":

        key = f"recommend_{st.session_state.tone}"
        script = SCRIPT[key]

        # ---------------- STEP 0 ----------------
        if st.session_state.step_index == 0:
            st.session_state.chat_log.append(("assistant", script[0]))
            st.session_state.step_index = 1
            st.rerun()

        # ---------------- STEP 1 ----------------
        elif st.session_state.step_index == 1:
            st.session_state.chat_log.append(("assistant", script[1]))
            st.session_state.step_index = 2
            st.rerun()

        # ---------------- STEP 2 조건 입력 ----------------
        elif st.session_state.step_index == 2:

            # STEP2 멘트는 한 번만 출력
            if st.session_state.get("step2_shown") != True:
                st.session_state.chat_log.append(("assistant", script[2]))
                st.session_state.step2_shown = True
                st.rerun()

            user_input = st.chat_input("여행 일정, 예산, 원하는 지역을 입력하세요.")
            if not user_input:
                st.stop()

            st.session_state.chat_log.append(("user", user_input))

            # 🔥 조건 충분성 검사 (GPT 사용)
            validation = client.chat.completions.create(
                model="gpt-4o",
                temperature=0,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "사용자의 입력에 다음 두 가지가 포함되면 '충분'으로 판단하십시오:\n"
                            "1) 여행 일정 (예: 2박3일, 5일 등)\n"
                            "2) 예산 (예: 100만원, 50만 원 등)\n\n"
                            "지역은 특정되지 않아도 됩니다.\n"
                            "일정 또는 예산이 없으면 '부족'이라고 답하십시오.\n"
                            "반드시 '충분' 또는 '부족' 중 하나만 답하십시오."
                        )
                    },
                    {
                        "role": "user",
                        "content": user_input
                    }
                ]
            )

            result = validation.choices[0].message.content.strip()

            if result == "충분":
                st.session_state.user_condition = user_input
                st.session_state.step_index = 3
                st.session_state.step2_shown = False
            else:
                st.session_state.chat_log.append(("assistant", "여행 일정, 예산, 원하는 지역을 모두 포함해 주세요."))

            st.rerun()

        # ---------------- STEP 3 상품 제안 ----------------
        elif st.session_state.step_index == 3:
        
            response = client.chat.completions.create(
                model="gpt-4o",
                temperature=0.9,
                messages=[
                    {"role": "system",
                    "content": f"""
                    사용자드시 반영하여 여행 상품 2개를 제시하십시오.

                    사용자 조건:
                    {st.session_state.user_condition}
                    
                    규칙:
                    1. 사용자가 제시한 예산을 절대 초과하지 마십시오.
                    2. 일정은 반드시 동일하게 유지하십시오.
                    3. 예산은 숫자로 명확히 표기하십시오.
                    4. 이전에 제시한 지역은 사용하지 마십시오.
                    5. 인사말은 작성하지 마십시오.
                    """
                    },
                    {"role": "user",
                    "content": st.session_state.user_condition}
                ]
            )

            reply = response.choices[0].message.content.strip()

            # 옵션 제안 멘트
            st.session_state.chat_log.append(("assistant", script[3]))

            # GPT 생성 상품
            st.session_state.chat_log.append(("assistant", reply))

            # STEP4로 이동
            st.session_state.step_index = 4

            st.rerun()

        # ---------------- STEP 4 수정 / 결정 판단 ----------------
        elif st.session_state.step_index == 4:

            user_input = st.chat_input(script[4])
            if not user_input:
                st.stop()

            st.session_state.chat_log.append(("user", user_input))

            # 🔥 GPT 의도 분류
            classification = client.chat.completions.create(
                model="gpt-4o",
                temperature=0,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "사용자의 발화를 다음 중 하나로만 분류하십시오:\n"
                            "1) 수정: 새로운 조건을 요청하거나 옵션 변경을 요구함\n"
                            "2) 없음: 더 이상 수정이 없다고 명시함\n"
                            "3) 결정: 특정 상품을 선택하거나 확정 의사를 표현함\n"
                            "반드시 '수정', '없음', '결정' 중 하나만 답하십시오."
                        )
                    },
                    {
                        "role": "user",
                        "content": user_input
                    }
                ]
            )

            intent = classification.choices[0].message.content.strip()

            if intent == "수정":
            # 🔥 기존 조건 유지 + 추가 요청 누적
                st.session_state.user_condition += "\n추가 요청: " + user_input
                st.session_state.step_index = 3

            elif intent == "없음":
                st.session_state.step_index = 5
                st.session_state.chat_log.append(("assistant", script[5]))

            elif intent == "결정":
                st.session_state.step_index = 6
                st.session_state.chat_log.append(("assistant", script[6]))

            else:
                # 예외 방어
                st.session_state.step_index = 5
                st.session_state.chat_log.append(("assistant", script[5]))

            st.rerun()


        # ---------------- STEP 5 추가 탐색 ----------------
        elif st.session_state.step_index == 5:

            user_input = st.chat_input(script[5])
            if not user_input:
                st.stop()

            st.session_state.chat_log.append(("user", user_input))

            classification = client.chat.completions.create(
                model="gpt-4o",
                temperature=0,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "사용자의 발화를 다음 중 하나로만 분류하십시오:\n"
                            "1) 계속: 더 탐색을 원함\n"
                            "2) 종료: 더 이상 탐색을 원하지 않음\n"
                            "반드시 '계속' 또는 '종료' 중 하나만 답하십시오."
                        )
                    },
                    {
                        "role": "user",
                        "content": user_input
                    }
                ]
            )

            intent = classification.choices[0].message.content.strip()

            if intent == "계속":
                st.session_state.step_index = 3
            else:
                st.session_state.step_index = 6
                st.session_state.chat_log.append(("assistant", script[6]))

            st.rerun()


        # ---------------- STEP 6 결정 ----------------
        elif st.session_state.step_index == 6:

            user_input = st.chat_input(script[6])
            if not user_input:
                st.stop()

            st.session_state.chat_log.append(("user", user_input))

            st.session_state.step_index = 7
            st.rerun()


        # ---------------- STEP 7 종료 (5초 유지) ----------------
        elif st.session_state.step_index == 7:

            # 최초 진입
            if "end_time" not in st.session_state:
                st.session_state.chat_log.append(("assistant", script[7]))
                st.session_state.end_time = time.time()
                st.rerun()

            # 5초 유지
            if time.time() - st.session_state.end_time < 5:
                st.stop()

            # 🔥 5초 후 설문 이동
            del st.session_state.end_time
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
