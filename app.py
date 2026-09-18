import gspread
from google.oauth2.service_account import Credentials
import streamlit as st

# 1. 頁面基本設定
st.set_page_config(
    page_title="Shisa Kanko-Shi Examination Portal",
    page_icon="🛡️",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# 隱藏 Streamlit 預設選單與頁尾
hide_streamlit_style = """
    <style>
    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}
    footer {visibility: hidden;}
    [data-testid="stToolbar"] {display: none !important; visibility: hidden !important;}
    [data-testid="stDecoration"] {display: none !important; visibility: hidden !important;}
    [data-testid="stStatusWidget"] {display: none !important; visibility: hidden !important;}
    </style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# 2. 初始化 Session State (確保資料在點擊時不會遺失)
if "authenticated" not in st.session_state:
  st.session_state.authenticated = False
if "candidate_email" not in st.session_state:
  st.session_state.candidate_email = ""
if "candidate_name" not in st.session_state:
  st.session_state.candidate_name = ""
if "exam_step" not in st.session_state:
  st.session_state.exam_step = (
      0  # 0: 驗證登入, 1: 考試須知, 2: 正式考試, 3: 完成交卷
  )


# 3. Google Sheets 連線函式
def get_sheets_connection():
  scope = [
      "https://spreadsheets.google.com/feeds",
      "https://www.googleapis.com/auth/drive",
  ]
  creds_dict = dict(st.secrets["gcp_service_account"])
  creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
  client = gspread.authorize(creds)
  sheet = client.open("ShisaKanko_Exam_Database")
  return sheet


# ==========================================
# 畫面邏輯：Step 0 - 考生身分驗證與憑證確認
# ==========================================
if not st.session_state.authenticated:
  st.markdown(
      "<h1 style='text-align: center;'>Shisa Kanko-Shi Examination Portal</h1>",
      unsafe_allow_html=True,
  )
  st.markdown(
      "<h3 style='text-align: center;'>(Certified Pointing-and-Calling"
      " Specialist)</h3>",
      unsafe_allow_html=True,
  )
  st.write("---")

  st.markdown("### Candidate Authentication")
  st.write(
      "Please enter your registered Email and Voucher Code to enter the"
      " examination room."
  )

  with st.form("auth_form"):
    email_input = st.text_input(
        "Registered Email Address", placeholder="e.g., candidate@example.com"
    )
    voucher_input = st.text_input(
        "Voucher Code", type="password", placeholder="Enter your voucher code"
    )

    submitted = st.form_submit_button("🔓 Verify and Enter Exam Room")

    if submitted:
      if not email_input or not voucher_input:
        st.error("Please enter both your Email and Voucher Code.")
      else:
        try:
          # 連線 Google Sheets 檢查 Vouchers 分頁
          db = get_sheets_connection()
          vouchers_sheet = db.worksheet("Vouchers")
          records = vouchers_sheet.get_all_records()

          matched = False
          for record in records:
            # 檢查 VoucherCode 與 Email 是否匹配，且狀態應為 Used (已由 exam1 鎖定)
            if (
                str(record.get("VoucherCode")).strip() == voucher_input.strip()
                and str(record.get("Email")).strip().lower()
                == email_input.strip().lower()
            ):
              matched = True
              # 記錄考生資料到 session state
              st.session_state.authenticated = True
              st.session_state.candidate_email = email_input
              st.session_state.candidate_name = (
                  f"{record.get('FirstName', '')} {record.get('LastName', '')}"
              )
              st.session_state.exam_step = 1  # 進入考試須知
              st.rerun()

          if not matched:
            st.error(
                "❌ Verification failed. Please check your Email and Voucher"
                " Code, or ensure you have completed registration on exam1."
            )

        except Exception as e:
          st.error(f"Connection error: {e}")

# ==========================================
# 畫面邏輯：Step 1 - 考試須知與守則
# ==========================================
elif st.session_state.authenticated and st.session_state.exam_step == 1:
  st.markdown(
      f"### Welcome, {st.session_state.candidate_name}!"
  )
  st.markdown("### Step 2: Examination Rules & Instructions")
  st.write("Please read the following rules carefully before starting:")

  st.info(
      "1. **Time Limit**: Once started, the timer cannot be paused.\n2."
      " **Anti-Cheat**: Do not switch browser tabs or close the window; doing"
      " so may invalidate your exam.\n3. **Submission**: Ensure you click the"
      " 'Submit Exam' button on the final page before time expires."
  )

  st.markdown("<br>", unsafe_allow_html=True)
  if st.button("🚀 I Understand and Agree. Start Exam Now"):
    st.session_state.exam_step = 2
    st.rerun()

# ==========================================
# 畫面邏輯：Step 2 - 核心問答模組 (開發中)
# ==========================================
elif st.session_state.authenticated and st.session_state.exam_step == 2:
  st.markdown("### Step 3: Shisa Kanko-Shi Core Examination")
  st.write(
      f"Candidate: **{st.session_state.candidate_name}**"
      f" ({st.session_state.candidate_email})"
  )
  st.write("---")

  # 這裡接下來會放入題目與計時器邏輯
  st.info("Exam questionnaire interface is under construction...")

  if st.button("Test Submit Exam"):
    st.session_state.exam_step = 3
    st.rerun()

# ==========================================
# 畫面邏輯：Step 3 - 交卷與完成畫面
# ==========================================
elif st.session_state.authenticated and st.session_state.exam_step == 3:
  st.markdown("<h2 style='text-align: center;'>🎉 Exam Completed!</h2>", unsafe_allow_html=True)
  st.success("Your responses have been successfully recorded to the examination database.")
  st.write(f"Thank you, {st.session_state.candidate_name}. You may now close this window.")