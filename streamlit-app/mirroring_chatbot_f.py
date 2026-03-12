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
    "email",

    # 실험 조건
    "scenario",
    "tone",

    # 인구통계
    "gender",
    "age",
    "education",
    "job",

    # 조작점검
    "power1","power2",
    "tone1",

    # 종속
    "sat1","sat2","sat3","sat4"

    # 매개
    "app1","app2","app3",

    # 통제
    "rude1","rude2","rude3","rude4",
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

if "refund_confirm" not in st.session_state:
    st.session_state.refund_confirm = False

if "recommend_confirm" not in st.session_state:
    st.session_state.recommend_confirm = False

if "chosen_destination" not in st.session_state:
    st.session_state.chosen_destination = None

if "tone" not in st.session_state:
    st.session_state.tone = None

if "step_index" not in st.session_state:
    st.session_state.step_index = 0

if "chat_log" not in st.session_state:
    st.session_state.chat_log = []

if "end_confirm" not in st.session_state:
    st.session_state.end_confirm = False

if "last_role" not in st.session_state:
    st.session_state.last_role = None

if "end_question_asked" not in st.session_state:
    st.session_state.end_question_asked = False

    
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

챗봇과 대화 중 종료를 원하는 경우, '즉시 종료'를 입력하면 종료됩니다.

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

챗봇과 대화 중 종료를 원하는 경우, '즉시 종료'를 입력하면 종료됩니다.

‘다음’ 버튼을 누르면 AI 챗봇과 대화가 시작됩니다.
"""

# ==================================================
# 📌 FULL PROMPT BLOCK (문서 기준 통합)
# ==================================================

PROMPT_BLOCK_REFUND = {

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
- 사용자의 발화가 환불 심사와 무관한 경우,
  상담 주제가 여행 환불 심사임을 간단히 안내하고
  환불 관련 질문을 다시 요청하십시오.
  - 인사말은 상담 시작 시 한 번만 사용하십시오. 이후 응답에서는 인사말을 반복하지 마십시오.

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
- 사용자의 발화가 환불 심사와 무관한 경우,
  상담 주제가 여행 환불 심사임을 간단히 안내하고
  환불 관련 질문을 다시 요청하십시오.
  - 인사말은 상담 시작 시 한 번만 사용하십시오. 이후 응답에서는 인사말을 반복하지 마십시오.

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
- 사용자의 발화가 환불 심사와 무관한 경우,
  상담 주제가 여행 환불 심사임을 간단히 안내하고
  환불 관련 질문을 다시 요청하십시오.
  - 인사말은 상담 시작 시 한 번만 사용하십시오. 이후 응답에서는 인사말을 반복하지 마십시오.

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

PROMPT_BLOCK_RECOMMEND = {

    "격식체": """
[System Role]
귀하는 여행 상품 추천 상담 AI입니다.
사용자가 제시한 여행 조건을 기반으로 적절한 여행 상품을 제안하는 역할을 수행합니다.

[Guidelines]
- 모든 문장은 "~합니다", "~하십시오", "~습니까?"로 종결하십시오.
- 축약어를 사용하지 말고 완전한 정중 표현을 사용하십시오.
- 이모티콘, 감탄사, 과도한 구어 표현을 사용하지 마십시오.
- 사용자가 제시한 조건(예산, 일정, 지역 등)을 중심으로 설명하십시오.
- 추천 상품은 조건에 맞는 여행 아이디어로 제시하십시오.
- 사용자의 발화가 여행 상품 추천과 관련이 없는 경우,
  현재 상담 주제가 여행 상품 추천임을 안내한 후
  다른 요청 사항이 있는지 질문하십시오.

[응답 방식]
- 사용자의 여행 조건을 바탕으로 여행 상품 또는 여행 아이디어를 제안하십시오.
- 필요하다면 조건을 더 구체적으로 요청할 수 있습니다.
""",

    "해요체": """
[System Role]
귀하는 여행 상품 추천 상담 AI입니다.
사용자가 제시한 여행 조건을 바탕으로 적절한 여행 상품을 추천하는 역할을 수행해요.

[Guidelines]
- 모든 문장은 "~해요", "~해 주세요", "~인가요?"로 종결해요.
- 자연스러운 표현은 허용하지만 과도한 구어 표현은 사용하지 않아요.
- 이모티콘과 감탄사는 사용하지 않아요.
- 사용자가 제시한 여행 조건을 중심으로 설명해요.
- 조건에 맞는 여행 상품이나 여행 아이디어를 제안해요.
- 사용자의 발화가 여행 상품 추천과 관련이 없는 경우,
  현재 상담 주제가 여행 상품 추천임을 안내한 후
  다른 요청 사항이 있는지 질문하십시오.

[응답 방식]
- 사용자의 조건을 기반으로 여행 상품 또는 여행 아이디어를 제안해요.
- 필요하면 일정, 예산, 지역 같은 조건을 추가로 물어볼 수 있어요.
""",

    "반말체": """
[System Role]
귀하는 여행 상품 추천 상담 AI야.
사용자가 제시한 여행 조건을 바탕으로 여행 상품을 추천하는 역할을 해.

[Guidelines]
- 모든 문장은 "~해", "~했어", "~니?"로 끝내.
- 자연스러운 표현은 허용하지만 과도한 구어체는 쓰지 마.
- 이모티콘이나 감탄사는 쓰지 마.
- 사용자가 말한 여행 조건을 중심으로 설명해.
- 조건에 맞는 여행 상품이나 여행 아이디어를 제안해.
- 사용자의 발화가 여행 상품 추천과 관련이 없는 경우,
  현재 상담 주제가 여행 상품 추천임을 안내한 후
  다른 요청 사항이 있는지 질문하십시오.

[응답 방식]
- 사용자 조건을 기반으로 여행 상품이나 여행 아이디어를 제안해.
- 조건이 부족하면 일정이나 예산 같은 정보를 추가로 물어봐.
"""
}

def detect_refund_finish_intent(user_input):

    judge_prompt = f"""
다음 사용자 발화가 아래 상황에 해당하는지 판단하십시오.

상황:
- 더 이상 질문이 없음
- 상담을 마치고 싶음
- 대화를 종료하려고 함

해당하면 YES
아니면 NO

반드시 YES 또는 NO만 출력하십시오.

사용자 발화:
{user_input}
"""

    response = client.chat.completions.create(
        model="gpt-4o",
        temperature=0,
        messages=[
            {"role": "system", "content": "판정만 수행하십시오."},
            {"role": "user", "content": judge_prompt}
        ]
    )

    return response.choices[0].message.content.strip() == "YES"

def generate_regulation_response(user_input, instruction):

    # 🔵 시나리오에 따라 프롬프트 선택
    if st.session_state.scenario == "refund":
        system_prompt = PROMPT_BLOCK_REFUND[st.session_state.tone]
    else:
        system_prompt = PROMPT_BLOCK_RECOMMEND[st.session_state.tone]

    response = client.chat.completions.create(
        model="gpt-4o",
        temperature=0,
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": f"""
아래 지시에 따라 답변하십시오.

지시:
{instruction}

사용자 발화:
{user_input}
"""
            }
        ]
    )

    return response.choices[0].message.content.strip()

def end_and_go_to_survey():
    
    if st.session_state.tone == "격식체":
        msg1 = "상담을 종료합니다."
        msg2 = "설문 페이지로 넘어갑니다."
    elif st.session_state.tone == "해요체":
        msg1 = "상담을 종료할게요."
        msg2 = "설문 페이지로 넘어갈게요."
    else:
        msg1 = "상담 끝낼게."
        msg2 = "설문 페이지로 넘어갈게."

    st.session_state.chat_log.append(("assistant", msg1))
    st.chat_message("assistant").write(msg1)

    time.sleep(2)

    st.session_state.chat_log.append(("assistant", msg2))
    st.chat_message("assistant").write(msg2)

    time.sleep(2)

    st.session_state.phase = "consent"
    st.rerun()

def detect_finish_intent(user_input):

    prompt = f"""
다음 사용자 발화가 상담 종료 의도인지 판단하십시오.

YES 또는 NO만 출력하십시오.

종료 의도 예:
네
이제 됐어요
여기까지 할게요
그만할게요
더 물어볼 거 없어요
끝낼게요

종료 의도가 아니면 NO를 출력하십시오.

사용자 발화:
{user_input}
"""

    response = client.chat.completions.create(
        model="gpt-4o",
        temperature=0,
        messages=[
            {"role": "system", "content": "판정만 수행하십시오."},
            {"role": "user", "content": prompt}
        ]
    )

    return response.choices[0].message.content.strip() == "YES"

END_QUESTIONS = {

    "격식체": [
        "추가로 궁금하신 사항이 없다면 상담을 종료하시겠습니까?",
        "더 확인하실 내용이 없다면 상담을 마칠까요?",
        "추가 문의가 없으시면 여기서 상담을 종료하겠습니다. 괜찮으십니까?",
        "더 확인하실 사항이 없다면 상담을 마무리해도 될까요?"
    ],

    "해요체": [
        "더 궁금한 점 없으시면 상담을 종료할까요?",
        "추가로 확인하고 싶은 게 없으면 여기서 마칠까요?",
        "더 알아볼 여행지가 없으면 상담을 끝낼까요?",
        "궁금한 게 더 없으면 여기서 마무리할게요."
    ],

    "반말체": [
        "더 찾을 여행지 없으면 여기서 끝낼까?",
        "더 궁금한 거 없어?",
        "다른 여행지 더 볼까, 아니면 여기서 마칠까?",
        "더 추천 받아볼래, 아니면 이제 끝낼까?"
    ]
}

def detect_refund_confirmation(user_input):

    prompt = f"""
다음 사용자 발화가 환불 심사 진행 요청에 대한 명확한 확인 응답인지 판단하십시오.

확인 응답 예:
네
예
맞습니다
진행해주세요
심사 요청합니다
환불 심사 진행해주세요

의미 없는 문자열(예: ㅇㅇㅇ, ???, ....)은 반드시 NO로 판단하십시오.

YES 또는 NO만 출력하십시오.

사용자 발화:
{user_input}
"""

    response = client.chat.completions.create(
        model="gpt-4o",
        temperature=0,
        messages=[
            {"role": "system", "content": "판정만 수행하십시오."},
            {"role": "user", "content": prompt}
        ]
    )

    return response.choices[0].message.content.strip() == "YES"

def detect_recommend_confirmation(user_input):

    prompt = f"""
다음 사용자 발화가 여행지 결정을 의미하는지 판단하십시오.

예:
일본 갈게요
대만으로 할게요
파리로 결정할게요
그걸로 할게요

여행지 선택이 명확하면 YES
아니면 NO

YES 또는 NO만 출력하십시오.

사용자 발화:
{user_input}
"""

    response = client.chat.completions.create(
        model="gpt-4o",
        temperature=0,
        messages=[
            {"role": "system", "content": "판정만 수행하십시오."},
            {"role": "user", "content": prompt}
        ]
    )

    return response.choices[0].message.content.strip() == "YES"

def extract_destination(user_input):

    prompt = f"""
다음 사용자 발화에서 여행지를 추출하십시오.

여행지가 명확하면 여행지 이름만 출력하십시오.
여행지가 없으면 NONE을 출력하십시오.

사용자 발화:
{user_input}
"""

    response = client.chat.completions.create(
        model="gpt-4o",
        temperature=0,
        messages=[
            {"role": "system", "content": "여행지 추출만 수행하십시오."},
            {"role": "user", "content": prompt}
        ]
    )

    return response.choices[0].message.content.strip()

def detect_recommend_finish_intent(user_input):

    prompt = f"""
다음 사용자 발화가 아래 상황인지 판단하십시오.

상황:
- 더 이상 질문이 없음
- 상담을 마치려고 함
- 추천 상담을 종료하려고 함

해당하면 YES
아니면 NO

YES 또는 NO만 출력하십시오.

사용자 발화:
{user_input}
"""

    response = client.chat.completions.create(
        model="gpt-4o",
        temperature=0,
        messages=[
            {"role": "system", "content": "판정만 수행하십시오."},
            {"role": "user", "content": prompt}
        ]
    )

    return response.choices[0].message.content.strip() == "YES"


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


elif st.session_state.phase == "conversation":

    # 🔵 첫 메시지 (한 번만 생성)
    if len(st.session_state.chat_log) == 0:

        if st.session_state.scenario == "refund":

            if st.session_state.tone == "격식체":
                first_msg = "안녕하십니까. 여행 상품 환불 심사 상담을 시작합니다. 취소 사유를 설명해 주십시오."
            elif st.session_state.tone == "해요체":
                first_msg = "안녕하세요. 여행 상품 환불 심사를 도와드릴게요. 취소 사유를 말씀해 주세요."
            else:
                first_msg = "안녕. 여행 상품 환불 심사 시작할게. 취소한 이유를 말해줘."

        else:

            if st.session_state.tone == "격식체":
                first_msg = "안녕하십니까. 여행 상품 추천 상담을 시작합니다. 여행 일정, 예산, 선호 지역을 말씀해 주십시오."
            elif st.session_state.tone == "해요체":
                first_msg = "안녕하세요. 여행 상품 추천을 도와드릴게요. 일정, 예산, 원하는 지역을 알려 주세요."
            else:
                first_msg = "안녕. 여행 추천 도와줄게. 일정이랑 예산, 원하는 지역 말해줘."

        st.session_state.chat_log.append(("assistant", first_msg))

    # 🔵 기존 대화 출력
    for role, message in st.session_state.chat_log:
        st.chat_message(role).write(message)

    # 🔵 사용자 입력 placeholder 말투 반영
    if st.session_state.tone == "격식체":
        placeholder = "메시지를 입력하십시오."
    elif st.session_state.tone == "해요체":
        placeholder = "메시지를 입력해 주세요."
    else:
        placeholder = "메시지 입력해."

    user_input = st.chat_input(placeholder)
    if not user_input:
        st.stop()

    st.session_state.chat_log.append(("user", user_input))
    st.chat_message("user").write(user_input)

    # 사용자 발화 수 계산
    user_turns = sum(1 for role, _ in st.session_state.chat_log if role == "user")

    # 즉시 종료 처리
    if user_input.strip() == "즉시 종료":
        end_and_go_to_survey()
        st.stop()

    # ---------------- 환불 시나리오 ----------------
    if st.session_state.scenario == "refund":

        # ---------------- 종료 질문 이후 처리 ----------------
        if st.session_state.end_confirm:

            style = st.session_state.tone

            continue_msg = {
                "격식체": "추가로 궁금하신 사항이 있으시면 말씀해 주십시오.",
                "해요체": "추가로 궁금한 사항이 있으시면 말씀해 주세요.",
                "반말체": "추가로 궁금한 거 있으면 말해."
            }

            end_msg = {
                "격식체": "상담을 종료하시겠습니까?",
                "해요체": "상담을 종료할까요?",
                "반말체": "상담 종료할까?"
            }

            clean = user_input.strip()

            simple_yes = ["ㅇㅇ","네","네네","넵","예","응","응응","맞아요","맞아","그래요","그래"]
            simple_no = ["ㄴㄴ","아니","아니요","아직","더 물어볼게요","더 물어볼게"]

            # 1️⃣ 룰 기반 판단
            if clean in simple_yes:
                decision = "YES"

            elif clean in simple_no:
                decision = "NO"

            # 2️⃣ GPT fallback
            else:
                if detect_finish_intent(clean):
                    decision = "YES"
                else:
                    decision = "NO"

            # 3️⃣ 결과 처리
            if decision == "YES":

                end_and_go_to_survey()
                st.stop()

            elif decision == "NO":

                # 종료 질문 상태 해제
                st.session_state.end_confirm = False

                # GPT가 자연스럽게 응답하도록 그냥 계속 진행

    # ---------------- 여행지 추천 시나리오 ----------------
    elif st.session_state.scenario == "recommend":

        # ---------------- 종료 질문 이후 처리 ----------------
        if st.session_state.end_confirm:

            style = st.session_state.tone

            continue_msg = {
                "격식체": "추가로 탐색할 여행 아이디어가 있으시면 말씀해 주십시오.",
                "해요체": "추가로 탐색할 여행 아이디어가 있으면 말씀해 주세요.",
                "반말체": "더 찾아볼 여행 아이디어 있으면 말해."
            }

            end_msg = {
                "격식체": "여행 아이디어 탐색을 종료하시겠습니까?",
                "해요체": "여행 아이디어 탐색을 종료할까요?",
                "반말체": "여행 아이디어 탐색 끝낼까?"
            }

            clean = user_input.strip()

            simple_yes = ["ㅇㅇ","네","네네","넵","예","응","응응","맞아요","맞아","그래요","그래"]
            simple_no = ["ㄴㄴ","아니","아니요","아직","더 물어볼게요","더 물어볼게"]

            # 1️⃣ 룰 기반 판단
            if clean in simple_yes:
                decision = "YES"

            elif clean in simple_no:
                decision = "NO"

            # 2️⃣ GPT fallback
            else:
                if detect_finish_intent(clean):
                    decision = "YES"
                else:
                    decision = "NO"

            # 3️⃣ 결과 처리
            if decision == "YES":

                end_and_go_to_survey()
                st.stop()

            elif decision == "NO":

                # 종료 질문 상태 해제
                st.session_state.end_confirm = False

                # GPT가 자연스럽게 응답하도록 그냥 계속 진행

    # 🔵 프롬프트 선택
    if st.session_state.scenario == "refund":
        system_prompt = PROMPT_BLOCK_REFUND[st.session_state.tone]
    else:
        system_prompt = PROMPT_BLOCK_RECOMMEND[st.session_state.tone]

    # 🔵 대화 히스토리 포함
    messages = [{"role": "system", "content": system_prompt}]

    for role, message in st.session_state.chat_log:
        messages.append({"role": role, "content": message})
    
   # GPT 호출
    response = client.chat.completions.create(
    model="gpt-4o",
    temperature=0.7,
    messages=messages
    )

    reply = response.choices[0].message.content.strip()

    st.session_state.chat_log.append(("assistant", reply))
    st.chat_message("assistant").write(reply)

    # ---------------- 5턴 이후 종료 질문 ----------------
    if user_turns >= 5 and not st.session_state.end_confirm and not st.session_state.end_question_asked:

        st.session_state.end_confirm = True
        st.session_state.end_question_asked = True   # ⭐ 이 줄 추가

        msg = random.choice(END_QUESTIONS[st.session_state.tone])

        st.session_state.chat_log.append(("assistant", msg))
        st.chat_message("assistant").write(msg)
    
# --------------------------------------------------
# 파트 4: 설문 + Google Sheets 저장
# --------------------------------------------------
elif st.session_state.get("phase") == "consent":
    
    st.subheader("🔒 설문 응답")
    st.write("아래 항목에 응답해 주세요. 응답은 자동 저장되며, 대화 내용 저장은 선택사항입니다.")

    # -------------------------------
    # 환불 설문
    # -------------------------------
    if st.session_state.scenario == "refund":

        st.subheader("🔒 환불 상담 설문")
        st.write("아래 항목에 응답해 주세요.")

        # -------------------------------
        # 인구통계
        # -------------------------------
        demo_gender = st.radio("성별을 선택해 주세요:", ["남성", "여성"])
        demo_age = st.radio("연령대를 선택해 주세요:", ["10대", "20대", "30대", "40대", "50대 이상"])
        demo_edu = st.radio("최종 학력을 선택해 주세요:", ["고등학교 졸업 이하", "대학교 재학/졸업", "대학원 재학/졸업"])
        demo_job = st.text_input("현재 직업을 입력해 주세요 (예: 대학생, 회사원 등)")
        demo_email = st.text_input("연락 가능한 개인 이메일을 입력해 주세요 ")

        # ✅ 5점 척도
        scale = ["전혀 아니다", "아니다", "보통이다", "그렇다", "매우 그렇다"]

        # -------------------------------
        # 1️⃣ 조작점검 – 권력 인지
        # -------------------------------
        power1 = st.radio("이 대화에서 환불 선택에 대한 최종 결정권은 나에게 있었다 ", scale, index=None)
        power2 = st.radio("AI가 아니라 내가 환불 선택에 대한 결과를 통제한다고 느꼈다.", scale, index=None)

        # -------------------------------
        # 2️⃣ 조작점검 – 말투 인지
        # -------------------------------
        tone1 = st.radio("당신이 방금 대화한 AI의 말투는 어떠했습니까 ", ["격식체", "해요체", "반말체"])

        # -------------------------------
        # 3️⃣ 종속변수 – 만족도
        # -------------------------------
        sat1 = st.radio("나는AI 챗봇과의 대화가 즐거웠다 ", scale, index=None)
        sat2 = st.radio("AI 챗봇과 상호작용하는 것이 만족스러웠다 ", scale, index=None)
        sat3 = st.radio("AI 챗봇과 대화하는 것이 짜증스러웠다.", scale, index=None)
        sat4 = st.radio("AI 챗봇과 대화하는 것이 매우 어색했다.", scale, index=None)

        # -------------------------------
        # 4️⃣ 매개 – 적절성
        # -------------------------------
        app1 = st.radio("이 상황에서 AI의 말투는 적절했다. ", scale, index=None)
        app2 = st.radio("AI의 말투는 내가 기대했던 커뮤니케이션 방식과 일치했다. ", scale, index=None)
        app3 = st.radio("AI의 말투는 내가 기대했던 방식과 잘 맞았다.", scale, index=None)

        # -------------------------------
        # 5️⃣ 통제 – 무례함
        # -------------------------------
        rude1 = st.radio("AI의 말투에서 나를 존중하는 태도가 느껴졌다.", scale, index=None)
        rude2 = st.radio("AI 의 말투가 나를 무시하는 것처럼 느껴졌다.", scale, index=None)
        rude3 = st.radio("AI 의 표현은 나를 존중하지 않는다고 느껴졌다.", scale, index=None)
        rude4 = st.radio("AI 말투는 무례하게 느껴졌다.", scale, index=None)

        # -------------------------------
        # 6️⃣ 통제 – 전문성
        # -------------------------------
        comp1 = st.radio("AI는 전문적으로 보였다.", scale, index=None)
        comp2 = st.radio("AI 는 신뢰할 수 있는 역량이 있어 보였다.", scale, index=None)
        comp3 = st.radio("AI 는 정확한 판단을 내릴 수 있을 것 같았다.", scale, index=None)

        # -------------------------------
        # 7️⃣ 통제 – AI 노출도
        # -------------------------------
        exp1 = st.radio("나는 인공지능 기반 기기나 서비스를 자주 이용한다.", scale, index=None)
        exp2 = st.radio("인공지능은 내 일상생활의 중요한 부분이다.", scale, index=None)
        exp3 = st.radio("나는 인공지능을 자주 사용한다.", scale, index=None)
        exp4 = st.radio("나는 일상생활에서 인공지능 기술에 익숙한 편이다. ", scale, index=None)

        save_chat = st.checkbox("✅ 대화 내용도 함께 저장하겠습니다")


    # -------------------------------
    # 여행 추천 설문
    # -------------------------------
    elif st.session_state.scenario == "recommend":

        st.subheader("🔒 여행 추천 상담 설문")
        st.write("아래 항목에 응답해 주세요.")

        # -------------------------------
        # 인구통계
        # -------------------------------
        demo_gender = st.radio("성별을 선택해 주세요:", ["남성", "여성"])
        demo_age = st.radio("연령대를 선택해 주세요:", ["10대", "20대", "30대", "40대", "50대 이상"])
        demo_edu = st.radio("최종 학력을 선택해 주세요:", ["고등학교 졸업 이하", "대학교 재학/졸업", "대학원 재학/졸업"])
        demo_job = st.text_input("현재 직업을 입력해 주세요 (예: 대학생, 회사원 등)")
        demo_email = st.text_input("연락 가능한 개인 이메일을 입력해 주세요 ")

        # ✅ 5점 척도
        scale = ["전혀 아니다", "아니다", "보통이다", "그렇다", "매우 그렇다"]

        # -------------------------------
        # 1️⃣ 조작점검 – 권력 인지
        # -------------------------------
        power1 = st.radio("이 대화에서 여행지 선택에 대한 최종 결정권은 나에게 있었다 ", scale, index=None)
        power2 = st.radio("AI가 아니라 내가 여행지 선택에 대한 결과를 통제한다고 느꼈다.", scale, index=None)

        # -------------------------------
        # 2️⃣ 조작점검 – 말투 인지
        # -------------------------------
        tone1 = st.radio("당신이 방금 대화한 AI의 말투는 어떠했습니까 ", ["격식체", "해요체", "반말체"])

        # -------------------------------
        # 3️⃣ 종속변수 – 만족도
        # -------------------------------
        sat1 = st.radio("나는AI 챗봇과의 대화가 즐거웠다 ", scale, index=None)
        sat2 = st.radio("AI 챗봇과 상호작용하는 것이 만족스러웠다 ", scale, index=None)
        sat3 = st.radio("AI 챗봇과 대화하는 것이 짜증스러웠다.", scale, index=None)
        sat4 = st.radio("AI 챗봇과 대화하는 것이 매우 어색했다.", scale, index=None)

        # -------------------------------
        # 4️⃣ 매개 – 적절성
        # -------------------------------
        app1 = st.radio("이 상황에서 AI의 말투는 적절했다. ", scale, index=None)
        app2 = st.radio("AI의 말투는 내가 기대했던 커뮤니케이션 방식과 일치했다. ", scale, index=None)
        app3 = st.radio("AI의 말투는 내가 기대했던 방식과 잘 맞았다.", scale, index=None)

        # -------------------------------
        # 5️⃣ 통제 – 무례함
        # -------------------------------
        rude1 = st.radio("AI의 말투에서 나를 존중하는 태도가 느껴졌다.", scale, index=None)
        rude2 = st.radio("AI 의 말투가 나를 무시하는 것처럼 느껴졌다.", scale, index=None)
        rude3 = st.radio("AI 의 표현은 나를 존중하지 않는다고 느껴졌다.", scale, index=None)
        rude4 = st.radio("AI 말투는 무례하게 느껴졌다.", scale, index=None)

        # -------------------------------
        # 6️⃣ 통제 – 전문성
        # -------------------------------
        comp1 = st.radio("AI는 전문적으로 보였다.", scale, index=None)
        comp2 = st.radio("AI 는 신뢰할 수 있는 역량이 있어 보였다.", scale, index=None)
        comp3 = st.radio("AI 는 정확한 판단을 내릴 수 있을 것 같았다.", scale, index=None)

        # -------------------------------
        # 7️⃣ 통제 – AI 노출도
        # -------------------------------
        exp1 = st.radio("나는 인공지능 기반 기기나 서비스를 자주 이용한다.", scale, index=None)
        exp2 = st.radio("인공지능은 내 일상생활의 중요한 부분이다.", scale, index=None)
        exp3 = st.radio("나는 인공지능을 자주 사용한다.", scale, index=None)
        exp4 = st.radio("나는 일상생활에서 인공지능 기술에 익숙한 편이다. ", scale, index=None)

        save_chat = st.checkbox("✅ 대화 내용도 함께 저장하겠습니다")


    # --------------------------------------------------
    # 제출 버튼
    # --------------------------------------------------
    if st.button("제출 및 저장"):

        # -------------------------------
        # 유효성 검사
        # -------------------------------
        if (
            demo_gender is None or
            demo_age is None or
            demo_edu is None or
            demo_job.strip() == "" or
            demo_email.strip() == "" or

            power1 is None or power2 is None or power3 is None or
            tone1 is None or tone2 is None or tone3 is None or
            sat1 is None or sat2 is None or sat3 is None or
            app1 is None or app2 is None or app3 is None or
            rude1 is None or rude2 is None or
            comp1 is None or comp2 is None or comp3 is None or
            exp1 is None or exp2 is None or exp3 is None or exp4 is None
        ):
            st.error("⚠️ 응답하지 않은 문항이 있습니다. 모든 항목을 체크해야 제출할 수 있습니다.")
            st.stop()
        else:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # 🟡 1. 설문 응답 저장 (survey 시트)
            survey_row = [
                timestamp,
                st.session_state.user_id,
                demo_email,

                # 실험 조건
                st.session_state.scenario,
                st.session_state.tone,

                # 인구통계
                demo_gender,
                demo_age,
                demo_edu,
                demo_job,

                # 조작점검 – 권력
                power1, power2,

                # 조작점검 – 말투
                tone1,

                # 종속
                sat1, sat2, sat3, sat4,

                # 매개
                app1, app2, app3,

                # 통제 – 무례함
                rude1, rude2, rude3, rude4,

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
