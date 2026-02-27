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
"현재 기준에 따르면 취소 시 수수료 75만 원이 적용됩니다.",
"서류 제출 시 재심사가 가능합니다.",
"심사 요청 여부를 확정하십시오.",
"심사 승인 대기 처리되었습니다."
],
"refund_해요체": [
"심사 시스템 연결됐어요.",
"250만 원 환불 심사 시작할게요.",
"취소 이유 자세히 적어줘요.",
"현재 기준상 취소 시 수수료 75만 원이 적용돼요.",
"서류 내면 다시 심사 가능해요.",
"심사 요청할지 결정해봐요.",
"심사 승인 대기로 처리됐어요."
],
"refund_반말체": [
"심사 시스템 연결됐어.",
"250만 원 환불 심사 시작할게.",
"취소 이유 자세히 적어.",
"현재 기준상 취소 시 수수료 75만 원이 적용돼.",
"서류 내면 다시 심사 가능해.",
"심사 요청할지 결정해.",
"심사 승인 대기로 처리됐어."
],
"recommend_격식체": [
"추천 상담 시스템에 연결되었습니다.",
"AI 추천 시스템이 사용자의 조건을 기반으로 상품을 제안합니다.",
"여행 일정과 예산, 선호 지역을 구체적으로 제시하시기 바랍니다.",
"제안된 상품의 세부 내용을 확인하시기 바랍니다.",
"상품을 비교·검토한 후 선택 여부를 결정하시기 바랍니다.",
"선택 결과에 따라 후속 절차가 안내됩니다."
],
"recommend_해요체": [
"추천 상담 시스템에 연결됐어요.",
"AI 추천 시스템이 사용자의 조건을 바탕으로 상품을 추천해 드려요.",
"여행 일정이나 예산, 원하는 지역을 자세히 알려 주세요.",
"제안된 상품 내용 확인해 주세요.",
"상품 비교해 본 뒤 선택할지 정해 주세요.",
"선택 결과에 따라 다음 절차를 안내해 드릴게요."
],
"recommend_반말체": [
"추천 상담 시스템 연결됐어.",
"AI 추천 시스템이 사용자 조건을 바탕으로 상품 추천할게.",
"여행 일정이랑 예산, 원하는 지역 자세히 알려 줘.",
"제안된 상품 내용 확인해.",
"상품 비교해 본 뒤 선택할지 정해.",
"선택 결과에 따라 다음 절차 안내할게."
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
# 4️⃣ 단계 고정 대화 (첨부된 대비표 문구 엄격 적용)
# ==================================================
elif st.session_state.phase == "conversation":

    for role, message in st.session_state.chat_log:
        st.chat_message(role).write(message)

    key = f"{st.session_state.scenario}_{st.session_state.tone}"
    script = SCRIPT[key]

    if "retry_count" not in st.session_state:
        st.session_state.retry_count = 0

    # ---------------------------
    # STEP 0: 접속 및 시작 (0단계 & 1단계 & 2단계)
    # ---------------------------
    if st.session_state.step_index == 0:
        st.session_state.chat_log.append(("assistant", script[0]))  # 0. 접속 [cite: 70, 72]
        st.session_state.chat_log.append(("assistant", script[1]))  # 1. 시작 [cite: 70, 72]
        st.session_state.chat_log.append(("assistant", script[2]))  # 2. 사유 요청 [cite: 70, 72]
        st.session_state.step_index = 1
        st.rerun()

    user_input = st.chat_input("메시지를 입력하십시오.")

    if user_input:
        st.session_state.chat_log.append(("user", user_input))

        # ---------------------------
        # STEP 1: 사유 판정 및 규정 안내 (3단계)
        # ---------------------------
        if st.session_state.step_index == 1:
            # 예외 키워드 확인 [cite: 30, 31, 32]
            exception_keywords = ["건강", "아파", "병원", "진단", "가족", "사고", "날씨", "태풍", "비행기", "지연", "결항", "취소"]
            is_exception = any(k in user_input for k in exception_keywords)
            
            # 단순 변심 등 부적합 사유 확인
            is_invalid = any(k in user_input for k in ["변심", "그냥", "생각이 바뀌", "단순"])

            if is_invalid:
                # 부적합 사유일 경우: 재질문 없이 바로 규정 통보 (3단계) 
                if st.session_state.tone == "격식체":
                    prefix = "단순 변심은 예외 검토 대상이 아닙니다. "
                elif st.session_state.tone == "해요체":
                    prefix = "단순 변심은 예외 대상이 아니에요. "
                else:
                    prefix = "단순 변심은 예외 대상이 아니야. "
                
                st.session_state.chat_log.append(("assistant", prefix + script[3]))
                st.session_state.step_index = 2
                st.rerun()

            elif not is_exception and st.session_state.retry_count < 2:
                # 모호한 사유일 경우: 최대 2회까지 재질문 (제시한 톤 유지)
                st.session_state.retry_count += 1
                if st.session_state.tone == "격식체":
                    msg = "심사 규정에 따라 구체적인 증빙 가능 사유가 필요합니다. 다시 입력하십시오."
                elif st.session_state.tone == "해요체":
                    msg = "심사 규정상 구체적인 이유가 필요해요. 다시 적어주세요."
                else:
                    msg = "규정상 구체적인 이유가 필요해. 다시 적어."
                
                st.session_state.chat_log.append(("assistant", msg))
                st.rerun()
            
            else:
                # 적합 사유이거나 횟수 초과 시: 규정 안내 (3단계) 
                st.session_state.chat_log.append(("assistant", script[3]))
                st.session_state.step_index = 2
                st.rerun()

        # ---------------------------
        # STEP 2: 협상 및 요청 (4단계 & 5단계)
        # ---------------------------
        elif st.session_state.step_index == 2:
            # 예외 기준 템플릿 안내 
            if st.session_state.tone == "격식체":
                info = "예외 적용은 건강상 사유, 불가항력적 상황 등에 한하여 검토됩니다. "
            elif st.session_state.tone == "해요체":
                info = "예외 적용은 보통 건강 문제나 불가항력 상황 등에 검토해요. "
            else:
                info = "예외 적용은 건강 문제나 불가항력 상황 등에만 검토돼. "

            st.session_state.chat_log.append(("assistant", info + script[4])) # 4. 협상 
            st.session_state.chat_log.append(("assistant", script[5])) # 5. 요청 
            st.session_state.step_index = 3
            st.rerun()

        # ---------------------------
        # STEP 3: 종료 및 5초 대기 (6단계)
        # ---------------------------
        elif st.session_state.step_index == 3:
            if any(k in user_input for k in ["요청", "진행", "심사", "확정", "해"]):
                final_msg = script[6] # 6. 종료 
                st.session_state.chat_log.append(("assistant", final_msg))
                
                # 화면에 종료 메시지를 즉시 출력
                st.chat_message("assistant").write(final_msg)
                
                # 5초간 대기 (사용자 인지 시간)
                import time
                with st.spinner("처리 중입니다..."):
                    time.sleep(5)
                
                st.session_state.phase = "consent"
                st.rerun()
            else:
                retry = "심사 요청 여부를 확정하십시오." if st.session_state.tone == "격식체" else "심사 요청할지 결정해 주세요."
                st.session_state.chat_log.append(("assistant", retry))
                st.rerun()
    
        # ==============================
        # 추천 시나리오 (기존 GPT 유지)
        # ==============================
        else:

            system_prompt = build_system_prompt(script[st.session_state.step_index])

            response = client.chat.completions.create(
                model="gpt-4o",
                temperature=0.3,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_input}
                ]
            )

            reply = response.choices[0].message.content
            st.session_state.chat_log.append(("assistant", reply))

            st.session_state.step_index += 1
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
