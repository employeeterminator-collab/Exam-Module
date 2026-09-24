import base64
import datetime
import time
import gspread
from google.oauth2.service_account import Credentials
import streamlit as st
import streamlit.components.v1 as components

# 1. 頁面基本設定
st.set_page_config(
    page_title="Shisa Kanko-Shi Examination Portal",
    page_icon="🛡️",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# 隱藏 Streamlit 預設選單、頁尾與標題的錨點連結符號
hide_streamlit_style = """
    <style>
    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}
    footer {visibility: hidden;}
    [data-testid="stToolbar"] {display: none !important; visibility: hidden !important;}
    [data-testid="stDecoration"] {display: none !important; visibility: hidden !important;}
    [data-testid="stStatusWidget"] {display: none !important; visibility: hidden !important;}
    
    .stMarkdown h1 a, .stMarkdown h2 a, .stMarkdown h3 a, .stMarkdown h4 a {
        display: none !important;
    }
    h1 a, h2 a, h3 a, h4 a {
        display: none !important;
    }
    </style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# 2. 初始化 Session State
if "authenticated" not in st.session_state:
  st.session_state.authenticated = False
if "candidate_email" not in st.session_state:
  st.session_state.candidate_email = ""
if "voucher_code" not in st.session_state:
  st.session_state.voucher_code = ""
if "candidate_first_name" not in st.session_state:
  st.session_state.candidate_first_name = ""
if "candidate_last_name" not in st.session_state:
  st.session_state.candidate_last_name = ""
if "candidate_japanese_name" not in st.session_state:
  st.session_state.candidate_japanese_name = ""
if "candidate_name" not in st.session_state:
  st.session_state.candidate_name = ""
if "exam_step" not in st.session_state:
  st.session_state.exam_step = 0
if "on_break" not in st.session_state:
  st.session_state.on_break = False
if "break_start_time" not in st.session_state:
  st.session_state.break_start_time = None
if "flagged_questions" not in st.session_state:
    st.session_state.flagged_questions = set()
if "focus_loss_count" not in st.session_state:
    st.session_state.focus_loss_count = 0
if "exam_questions" not in st.session_state:
    st.session_state.exam_questions = []

# ==========================================
# 3. Google Sheets 連線與資料庫輔助函式
# ==========================================
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

# 動態載入獨立題庫檔案資料 (從 Google Sheet "Questions", 頁籤 "A")
def get_exam_questions():
    try:
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ]
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        client = gspread.authorize(creds)
        
        spreadsheet = client.open("Questions")
        sheet = spreadsheet.worksheet("A")
        records = sheet.get_all_records()
        
        normalized_records = []
        for r in records:
            q_text = r.get("QuestionText", r.get("Question", ""))
            if not str(q_text).strip():
                continue
            normalized_records.append({
                "Question": q_text,
                "OptionA": r.get("OptionA", ""),
                "OptionB": r.get("OptionB", ""),
                "OptionC": r.get("OptionC", ""),
                "OptionD": r.get("OptionD", ""),
                "CorrectAnswer": r.get("CorrectAnswer", "")
            })
            
        if normalized_records:
            return normalized_records
            
    except Exception as e:
        st.error(f"Google Sheets Debug Error: {e}")
        
    return []

# 記錄第一次開始考試的時間 (Committed)
def update_voucher_committed(voucher_code):
    try:
        db = get_sheets_connection()
        sheet = db.worksheet("Vouchers")
        cell = sheet.find(voucher_code)
        if cell:
            current_value = sheet.cell(cell.row, 10).value
            if not current_value or str(current_value).strip() == "":
                current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                sheet.update_cell(cell.row, 10, current_time)
    except Exception as e:
        print(f"Failed to update Committed time: {e}")

# 記錄違規事件到 ViolationLogs Tab 同時即時更新 Vouchers 上的警告次數
def log_violation_to_sheet(voucher_code):
    try:
        db = get_sheets_connection()
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 1. 強制寫入一筆獨立紀錄到 ViolationLogs 頁籤
        try:
            logs_sheet = db.worksheet("ViolationLogs")
            logs_sheet.append_row([voucher_code, current_time, "Focus Lost / Tab Switched"])
        except Exception as log_err:
            print(f"Failed to append row to ViolationLogs: {log_err}")
        
        # 2. 同步累加 Vouchers 表格中的 WarningCount 欄位 (第 11 欄)
        vouchers_sheet = db.worksheet("Vouchers")
        cell = vouchers_sheet.find(voucher_code)
        if cell:
            current_warnings = vouchers_sheet.cell(cell.row, 11).value
            try:
                new_count = int(current_warnings) + 1 if current_warnings and str(current_warnings).isdigit() else 1
            except:
                new_count = 1
            vouchers_sheet.update_cell(cell.row, 11, new_count)
            st.session_state.focus_loss_count = new_count
    except Exception as e:
        print(f"Failed to log violation globally: {e}")

# 完成考試時更新狀態 (修改後：即使 Timeout 自動交卷，也正常計分並寫入 Pass 或 Fail)
def finalize_exam_submission(voucher_code, warning_count, exam_status, explanation=""):
    try:
        db = get_sheets_connection()
        sheet = db.worksheet("Vouchers")
        cell = sheet.find(voucher_code)
        if cell:
            completed_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            sheet.update_cell(cell.row, 12, completed_time)  # CompletedExam time
            sheet.update_cell(cell.row, 11, warning_count) # WarningCount
            sheet.update_cell(cell.row, 13, exam_status)   # ExamStatus / EndTime ("Pass" or "Fail")
            sheet.update_cell(cell.row, 14, explanation)   # Explanation
    except Exception as e:
        print(f"Failed to finalize exam submission: {e}")


# ==========================================
# Step 0 - 考生身分驗證與精準 DNF 檢查
# ==========================================
if not st.session_state.authenticated:
  st.markdown(
      "<h1 style='text-align: center;'>Shisa Kanko-Shi Examination Portal</h1>",
      unsafe_allow_html=True,
  )
  st.markdown(
      "<h3 style='text-align: center;'>(Certified Pointing-and-Calling Specialist)</h3>",
      unsafe_allow_html=True,
  )
  st.write("---")

  st.markdown("### Candidate Authentication")
  st.write("Please enter your registered Email and Voucher Code to enter the examination room.")

  with st.form("auth_form"):
    email_input = st.text_input("Registered Email Address", placeholder="e.g., candidate@example.com")
    voucher_input = st.text_input("Voucher Code", type="password", placeholder="Enter your voucher code")

    submitted = st.form_submit_button("🔓 Verify and Enter Exam Room")

    if submitted:
      if not email_input or not voucher_input or not email_input.strip() or not voucher_input.strip():
        st.error("Please enter both your Email and Voucher Code.")
      else:
        try:
          db = get_sheets_connection()
          vouchers_sheet = db.worksheet("Vouchers")
          records = vouchers_sheet.get_all_records()

          matched_record = None
          row_index = None

          for idx, record in enumerate(records, start=2):
            r_voucher = str(record.get("VoucherCode", "")).strip()
            r_email = str(record.get("AssignedEmail", "")).strip()
            r_status = str(record.get("Status", "")).strip()

            if (
                r_voucher == voucher_input.strip()
                and r_email != ""
                and r_email.lower() == email_input.strip().lower()
                and r_status.lower() == "used"
            ):
              matched_record = record
              row_index = idx
              break

          if matched_record:
            completed_exam_val = str(matched_record.get("CompletedExam", "")).strip()
            exam_end_val = str(matched_record.get("ExamEndTime", "")).strip()
            committed_time = str(matched_record.get("Committed", "")).strip()

            # 🛡️ STRICT BLOCK: If the exam was already completed, passed, failed, or DNF'd, deny entry permanently
            if exam_end_val in ["Pass", "Fail", "DNF"] or (completed_exam_val != "" and completed_exam_val != "DNF"):
              st.error("❌ **Access Denied:** This examination has already been completed, submitted, or expired using this voucher. Re-entry is strictly prohibited.")
            
            # Check if already timed out (DNF)
            elif committed_time != "":
              try:
                committed_dt = datetime.datetime.strptime(committed_time, "%Y-%m-%d %H:%M:%S")
                elapsed_seconds = (datetime.datetime.now() - committed_dt).total_seconds()
                EXAM_TIME_LIMIT = 5400  # 90 minutes

                if elapsed_seconds > EXAM_TIME_LIMIT:
                    if exam_end_val != "DNF":
                        vouchers_sheet.update_cell(row_index, 13, "DNF")
                    st.error("❌ **Access Denied:** Exam session expired (Time limit exceeded). Please contact Administrator.")
                else:
                    # Within valid active session window, resume
                    f_name = str(matched_record.get("EnglishFirstName", "")).strip()
                    l_name = str(matched_record.get("EnglishLastName", "")).strip()
                    j_name = str(matched_record.get("JapaneseName", "")).strip()

                    st.session_state.authenticated = True
                    st.session_state.candidate_email = email_input.strip()
                    st.session_state.voucher_code = voucher_input.strip()
                    st.session_state.candidate_first_name = f_name
                    st.session_state.candidate_last_name = l_name
                    st.session_state.candidate_japanese_name = j_name
                    st.session_state.candidate_name = f"{f_name} {l_name}".strip()

                    st.session_state.exam_step = 3
                    st.success("🔄 Detected an active session. Resuming your exam...")
                    time.sleep(1)
                    st.rerun()
              except Exception as e:
                st.error(f"Time validation error: {e}")
            else:
              # Brand new session, start Step 1
              f_name = str(matched_record.get("EnglishFirstName", "")).strip()
              l_name = str(matched_record.get("EnglishLastName", "")).strip()
              j_name = str(matched_record.get("JapaneseName", "")).strip()

              st.session_state.authenticated = True
              st.session_state.candidate_email = email_input.strip()
              st.session_state.voucher_code = voucher_input.strip()
              st.session_state.candidate_first_name = f_name
              st.session_state.candidate_last_name = l_name
              st.session_state.candidate_japanese_name = j_name
              st.session_state.candidate_name = f"{f_name} {l_name}".strip()

              st.session_state.exam_step = 1
              st.rerun()
          else:
            st.error("❌ Invalid Email, Voucher Code, or the voucher has not been activated yet.")
        except Exception as e:
          st.error(f"Connection error: {e}")
                

# ==========================================
# Step 1 - 身分核對與考試須知
# ==========================================
elif st.session_state.authenticated and st.session_state.exam_step == 1:
  st.markdown(f"### Welcome, {st.session_state.candidate_first_name} {st.session_state.candidate_last_name}!")
  st.write("---")

  st.markdown("### Step 1: Candidate Information Verification")
  st.write("Please carefully verify your registered information below:")

  st.markdown(f"""
    - **1. Last Name:** {st.session_state.candidate_last_name}
    - **2. First Name:** {st.session_state.candidate_first_name}
    - **3. Japanese Name:** {st.session_state.candidate_japanese_name}
    - **4. Email Address:** {st.session_state.candidate_email}
    """)

  st.warning("⚠️ If the above information is incorrect or missing, please end the exam now and contact administrator.")

  st.markdown(
      """
        <div style="text-align: left; margin-top: 10px; margin-bottom: 20px;">
            <a href="https://shisakanko.org/contact" target="_self" style="
                display: inline-block;
                background-color: #ffffff;
                color: #212529;
                border: 1px solid #ced4da;
                padding: 10px 20px;
                text-decoration: none;
                border-radius: 4px;
                font-weight: 600;
                font-family: sans-serif;
                box-shadow: 0 1px 2px rgba(0,0,0,0.05);
            ">🚪 Quit and Contact Administrator</a>
        </div>
    """,
      unsafe_allow_html=True,
  )
  st.write("---")
  st.markdown("### Step 2: Examination Rules & Instructions")
  st.write("Please read the following rules carefully before starting:")

  try:
    with open("examinstruction.txt", "r", encoding="utf-8") as f:
      exam_instructions = f.read()
  except FileNotFoundError:
    exam_instructions = (
        "1. Time Limit: Once started, the timer cannot be paused.\n2. Anti-Cheat:"
        " Do not switch browser tabs or close the window.\n3. Submission:"
        " Ensure you click the submit button before time expires."
    )

  st.markdown(
      f"""
      <div style="
          background-color: #ffffff;
          color: #212529;
          border: 1px solid #ced4da;
          border-radius: 6px;
          padding: 15px;
          height: 200px;
          overflow-y: auto;
          white-space: pre-line;
          font-size: 15px;
          line-height: 1.6;
          box-shadow: inset 0 1px 2px rgba(0,0,0,0.075);
      ">
      {exam_instructions}
  """,
      unsafe_allow_html=True,
  )

  st.markdown("<br>", unsafe_allow_html=True)
  if st.button("🚀 I Understand and Agree"):
    st.session_state.exam_step = 2
    st.rerun()

  st.write("---")


# ==========================================
# Step 2 - 考生拍照驗證與倒數休息頁面
# ==========================================
elif st.session_state.authenticated and st.session_state.exam_step == 2:
  
  if st.session_state.on_break:
    st.markdown("<h2 style='text-align: center;'>Pre-Exam Candidate Transition Pause</h2>", unsafe_allow_html=True)
    st.write(
        "<p style='text-align: center;'>Your photo has been successfully verified. "
        "Take a brief break before your core examination begins. "
        "The exam will start automatically when the timer expires. "
        "Once the exam started, your voucher will be count as used and committed.</p>",
        unsafe_allow_html=True,
    )
    st.write("---")

    TOTAL_SECONDS = 5 * 60
    elapsed = int(time.time() - st.session_state.break_start_time)
    remaining = TOTAL_SECONDS - elapsed

    if remaining <= 0:
      st.session_state.on_break = False
      st.session_state.exam_step = 3
      st.rerun()

    mins, secs = divmod(remaining, 60)
    st.markdown(
        f"<h1 style='text-align: center; font-size: 70px; color: #0066cc;'>⏳ {mins:02d}:{secs:02d}</h1>",
        unsafe_allow_html=True,
    )

    if 20 <= remaining <= 30:
      st.warning("⚠️ **Warning:** Only 30 seconds remaining before the core examination starts automatically!")

    st.markdown("<br>", unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
      if st.button("🚀 Start Exam Now", use_container_width=True, key="start_exam_btn"):
        update_voucher_committed(st.session_state.voucher_code)
        st.session_state.on_break = False
        st.session_state.exam_step = 3
        st.rerun()

    time.sleep(1)
    st.rerun()

  else:
    st.markdown("### Step 3: Candidate Photo Verification")
    st.write(f"Candidate: **{st.session_state.candidate_name}** ({st.session_state.candidate_email})")

    if "photo_attempts" not in st.session_state:
      st.session_state.photo_attempts = 0

    MAX_ATTEMPTS = 3
    remaining_attempts = MAX_ATTEMPTS - st.session_state.photo_attempts

    if remaining_attempts <= 0:
      st.error(f"❌ You have exceeded the maximum allowed photo verification attempts ({MAX_ATTEMPTS}/{MAX_ATTEMPTS}). Your session is locked. Please contact the administrator.")
    else:
      st.write("Please take a photo for identity verification records prior to starting the exam.")
      photo_file = st.camera_input("Capture Your Photo", key="exam_camera_input")

      if photo_file is not None:
        st.success("✅ Photo captured successfully!")
        st.markdown("<br>", unsafe_allow_html=True)

        if st.button("🚀 Proceed to Next Step", key="proceed_btn"):
          st.session_state.photo_attempts += 1

          with st.spinner("Uploading verification photo to secure storage and proceeding..."):
            try:
              import requests
              imgbb_key = st.secrets["imgbb"]["api_key"]
              upload_url = "https://api.imgbb.com/1/upload"

              image_bytes = photo_file.getvalue()
              voucher_code = st.session_state.get("voucher_code", "EXAM")
              file_name = f"{voucher_code}-Verified"

              payload = {"key": imgbb_key, "name": file_name}
              files = {"image": image_bytes}

              response = requests.post(upload_url, data=payload, files=files)
              result = response.json()

              if result.get("success"):
                photo_url = result["data"]["url"]
                try:
                  db = get_sheets_connection()
                  sheet = db.worksheet("Vouchers")
                  cell = sheet.find(st.session_state.candidate_email)
                  if cell:
                    sheet.update_cell(cell.row, 9, photo_url)
                except Exception:
                  pass

                st.session_state.on_break = True
                st.session_state.break_start_time = time.time()
                st.rerun()
              else:
                error_msg = result.get("error", {}).get("message", "Unknown error")
                st.error(f"Upload failed: {error_msg}. Please try again. ({MAX_ATTEMPTS - st.session_state.photo_attempts} attempts left)")
                st.rerun()

            except Exception as e:
              st.error(f"An unexpected error occurred: {e}. ({MAX_ATTEMPTS - st.session_state.photo_attempts} attempts left)")
              st.rerun()


# ==========================================
# Step 3 - 核心問答模組 (連線 Google Sheets 題庫、Phantom 警告、Webcam、計時器)
# ==========================================
elif st.session_state.authenticated and st.session_state.exam_step == 3:

    if "current_q" not in st.session_state:
        st.session_state.current_q = 1
    if "answers" not in st.session_state:
        st.session_state.answers = {}  
    if "flagged_questions" not in st.session_state:
        st.session_state.flagged_questions = set()  

    # Fetch questions from Google Sheets if not already cached
    if not st.session_state.exam_questions:
        st.session_state.exam_questions = get_exam_questions()

    exam_questions = st.session_state.exam_questions
    TOTAL_QUESTIONS = len(exam_questions) if exam_questions else 75

    def handle_focus_loss():
        log_violation_to_sheet(st.session_state.voucher_code)

    # 1. Hidden backend trigger button for violation counting & sheet logging
    if st.button("TriggerViolationBackend", key="hidden-violation-trigger", on_click=handle_focus_loss):
        pass

    # 2. Hidden backend trigger button for auto-submission on timeout
    def handle_auto_submit():
        user_answers = st.session_state.get("answers", {})
        focus_losses = st.session_state.get("focus_loss_count", 0)
        
        correct_count = 0
        for idx, q_data in enumerate(exam_questions, start=1):
            user_ans = str(user_answers.get(idx, "")).strip()
            correct_letter = str(q_data.get("CorrectAnswer", "")).strip().upper()
            correct_text = str(q_data.get(f"Option{correct_letter}", "")).strip()
            if user_ans and (user_ans.upper() == correct_letter or user_ans == correct_text):
                correct_count += 1
        
        passing_score_percentage = 70.0
        score_percentage = (correct_count / TOTAL_QUESTIONS) * 100 if TOTAL_QUESTIONS > 0 else 0
        
        # 評分標準：夠分數就係 Pass，唔夠就係 Fail，不再寫 DNF
        final_status = "Pass" if score_percentage >= passing_score_percentage else "Fail"
        
        answered_count = len(user_answers)
        finalize_exam_submission(
            st.session_state.voucher_code,
            focus_losses,
            final_status,
            explanation=f"Auto-submitted on timeout. Answered {answered_count}/{TOTAL_QUESTIONS}, Correct {correct_count}"
        )
        
        st.session_state.exam_final_status = final_status
        st.session_state.exam_correct_count = correct_count
        st.session_state.exam_step = 5
        st.rerun()

    if st.button("AutoSubmitBackend", key="hidden-auto-submit-trigger", on_click=handle_auto_submit):
        pass

    # 3. JavaScript handles auto-hiding buttons, global warning banner, timeout auto-submission, etc.
    st.components.v1.html("""
        <script>
            function hideTriggerButtons() {
                const buttons = parent.document.querySelectorAll('button');
                buttons.forEach(btn => {
                    if (btn.innerText.includes('TriggerViolationBackend') || btn.innerText.includes('AutoSubmitBackend')) {
                        let container = btn.closest('[data-testid="stVerticalBlock"] > div') || btn.closest('.element-container') || btn.parentElement;
                        if (container) {
                            container.style.display = 'none';
                        }
                    }
                });
            }
            
            setTimeout(hideTriggerButtons, 50);
            setInterval(hideTriggerButtons, 300);

            if (!parent.document.getElementById('global-warning-banner')) {
                const banner = parent.document.createElement('div');
                banner.id = 'global-warning-banner';
                banner.style.cssText = `
                    position: fixed; top: 0; left: 0; width: 100vw;
                    background-color: #dc2626; color: white; text-align: center; 
                    padding: 16px 20px; font-family: sans-serif; font-weight: bold; 
                    font-size: 15px; line-height: 1.4; box-shadow: 0 4px 15px rgba(0,0,0,0.4);
                    z-index: 2147483647; display: none; box-sizing: border-box;
                `;
                banner.innerHTML = "🚨 WARNING: Tab switch, screen blur, or cursor out of bounds detected! Please remain focused on the exam.";
                parent.document.body.appendChild(banner);
            }

            let bannerTimer;
            function triggerGlobalWarning() {
                const b = parent.document.getElementById('global-warning-banner');
                if (b) {
                    b.style.display = 'block';
                    clearTimeout(bannerTimer);
                    bannerTimer = setTimeout(() => {
                        b.style.display = 'none';
                    }, 8000);
                }
                
                const buttons = parent.document.querySelectorAll('button');
                buttons.forEach(btn => {
                    if (btn.innerText.includes('TriggerViolationBackend')) {
                        btn.click();
                    }
                });
            }

            parent.document.addEventListener("visibilitychange", function() {
                if (parent.document.hidden) {
                    triggerGlobalWarning();
                }
            });

            parent.window.addEventListener("blur", function() {
                triggerGlobalWarning();
            });

            parent.document.addEventListener("mouseleave", function(e) {
                if (e.clientY <= 0 || e.clientX <= 0 || e.clientX >= parent.window.innerWidth || e.clientY >= parent.window.innerHeight) {
                    triggerGlobalWarning();
                }
            });
        </script>
    """, height=0)

    header_col1, header_col2, header_col3 = st.columns([2, 1, 1])
    
    with header_col1:
        st.markdown(f"### 👤 Candidate: {st.session_state.get('candidate_name', 'User')}")
        st.write(f"Email: {st.session_state.get('candidate_email', '')}")
   
    with header_col2:
        if "exam_remaining_seconds" not in st.session_state:
            initial_remaining = 5400
            try:
                db = get_sheets_connection()
                sheet = db.worksheet("Vouchers")
                cell = sheet.find(st.session_state.voucher_code)
                if cell:
                    committed_str = sheet.cell(cell.row, 10).value
                    if committed_str and str(committed_str).strip() != "":
                        committed_time = datetime.datetime.strptime(str(committed_str).strip(), "%Y-%m-%d %H:%M:%S")
                        elapsed_seconds = int((datetime.datetime.now() - committed_time).total_seconds())
                        initial_remaining = max(0, 5400 - elapsed_seconds)
            except Exception as e:
                print(f"Error calculating initial remaining time: {e}")
            
            st.session_state.exam_remaining_seconds = initial_remaining
            st.session_state.exam_timer_start_local = time.time()

        elapsed_local = int(time.time() - st.session_state.exam_timer_start_local)
        remaining_seconds = max(0, st.session_state.exam_remaining_seconds - elapsed_local)

        timer_html = """
            <div style="background-color: #1e293b; padding: 10px; border-radius: 8px; text-align: center; color: white; font-family: sans-serif;">
                <div style="font-size: 10px; color: #94a3b8; letter-spacing: 1px; margin-bottom: 4px;">⏳ TIME REMAINING</div>
                <div id="native-js-timer" style="font-size: 20px; font-weight: bold; font-family: monospace; color: #38bdf8;">01:30:00</div>
            </div>
            <script>
                const STORAGE_KEY = 'exam_end_time_VOUCHER_PLACEHOLDER';
                const serverRemaining = SERVER_REMAINING_PLACEHOLDER;
                
                let endTime = Date.now() + (serverRemaining * 1000);
                parent.sessionStorage.setItem(STORAGE_KEY, endTime);

                let hasAutoSubmitted = false;

                function updateCountdown() {
                    const now = Date.now();
                    let timeLeft = Math.floor((endTime - now) / 1000);
                    if (timeLeft <= 0) {
                        timeLeft = 0;
                        if (!hasAutoSubmitted) {
                            hasAutoSubmitted = true;
                            // Trigger auto-submit button click in parent
                            const buttons = parent.document.querySelectorAll('button');
                            buttons.forEach(btn => {
                                if (btn.innerText.includes('AutoSubmitBackend')) {
                                    btn.click();
                                }
                            });
                        }
                    }

                    const h = String(Math.floor(timeLeft / 3600)).padStart(2, '0');
                    const m = String(Math.floor((timeLeft % 3600) / 60)).padStart(2, '0');
                    const s = String(timeLeft % 60).padStart(2, '0');

                    const target = document.getElementById('native-js-timer');
                    if (target) {
                        target.innerText = h + ":" + m + ":" + s;
                    }
                }

                updateCountdown();
                setInterval(updateCountdown, 1000);
            </script>
        """
        timer_html = timer_html.replace('VOUCHER_PLACEHOLDER', str(st.session_state.voucher_code))
        timer_html = timer_html.replace('SERVER_REMAINING_PLACEHOLDER', str(remaining_seconds))

        st.components.v1.html(timer_html, height=75)
           
    with header_col3:
        st.components.v1.html("""
            <div style="border: 2px solid #22c55e; border-radius: 8px; background-color: #f0fdf4; text-align: center; padding: 4px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); box-sizing: border-box;">
                <div style="color: #15803d; font-weight: bold; font-size: 10px; margin-bottom: 2px; text-transform: uppercase;">🟢 Live Proctor</div>
                <video id="top-webcam" autoplay playsinline muted style="width: 100%; height: 72px; object-fit: cover; border-radius: 4px; background: #000; display: block;"></video>
            </div>
            <script>
                async function initCam() {
                    try {
                        const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
                        document.getElementById('top-webcam').srcObject = stream;
                    } catch (e) {
                        console.error("Camera access error", e);
                    }
                }
                initCam();
            </script>
        """, height=110)

    st.divider()

    with st.sidebar:
        st.markdown("### 📹 Security Status")
        st.markdown(f"""
            <div style="border: 2px dashed #22c55e; padding: 10px; border-radius: 8px; text-align: center; background-color: #f0fdf4;">
                <div style="color: #15803d; font-weight: bold; font-size: 12px;">🟢 Focus Guard Active</div>
                <div style="color: #475569; font-size: 11px; margin-top: 4px;">Warnings: {st.session_state.focus_loss_count}</div>
            </div>
        """, unsafe_allow_html=True)

        st.markdown("---")
        st.markdown(f"### 🗺️ Question Palette (1–{TOTAL_QUESTIONS})")
        st.markdown("<small>🟢 Answered | ⚪ Unanswered | ⭐ Flagged</small>", unsafe_allow_html=True)
        
        cols_per_row = 5
        for i in range(1, TOTAL_QUESTIONS + 1, cols_per_row):
            cols = st.columns(cols_per_row)
            for j in range(cols_per_row):
                q_num = i + j
                if q_num <= TOTAL_QUESTIONS:
                    label = f"⭐{q_num}" if q_num in st.session_state.flagged_questions else f"{q_num}"
                    if cols[j].button(label, key=f"pal_{q_num}", use_container_width=True):
                        st.session_state.current_q = q_num
                        st.rerun()

    if not exam_questions:
        st.error("❌ Failed to load exam questions from the database. Please check your connection or contact the administrator.")
    else:
        q_idx = st.session_state.current_q
        current_q_data = exam_questions[q_idx - 1]

        st.markdown(f"#### Question {q_idx} of {TOTAL_QUESTIONS} — Multiple Choice")
        st.progress(q_idx / TOTAL_QUESTIONS)

        q_text = current_q_data.get("Question", "Question text unavailable.")
        st.markdown(f"#### Q{q_idx}. {q_text}")

        options = []
        for opt_key in ["OptionA", "OptionB", "OptionC", "OptionD"]:
            val = current_q_data.get(opt_key, "")
            if val and str(val).strip() != "":
                options.append(str(val).strip())

        current_answer = st.session_state.answers.get(q_idx, None)
        default_index = 0
        if current_answer in options:
            default_index = options.index(current_answer)

        selected = st.radio(
            "Select your answer:", 
            options, 
            index=default_index, 
            key=f"q_radio_{q_idx}"
        )

        if selected:
            st.session_state.answers[q_idx] = selected

        st.markdown("<br>", unsafe_allow_html=True)

        col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 1])

        with col_btn1:
            is_flagged = q_idx in st.session_state.flagged_questions
            flag_label = "🚩 Flagged for Review" if is_flagged else "🏳️ Flag Question"

            if st.checkbox(flag_label, value=is_flagged, key=f"flag_box_{q_idx}"):
                st.session_state.flagged_questions.add(q_idx)
            else:
                st.session_state.flagged_questions.discard(q_idx)

        with col_btn2:
            if st.button("⬅️ Previous", use_container_width=True, disabled=(q_idx == 1)):
                st.session_state.current_q -= 1
                st.rerun()

        with col_btn3:
            if st.button("Next ➡️", use_container_width=True, disabled=(q_idx == TOTAL_QUESTIONS)):
                st.session_state.current_q += 1
                st.rerun()

        st.markdown("---")

        b_col1, b_col2, b_col3 = st.columns([2, 3, 2])
        with b_col2:
            if st.button("📋 Review & Finish Exam", type="primary", use_container_width=True):
                st.session_state.exam_step = 4
                st.rerun()


# ==========================================
# Step 4 - 考試總結與詳細清單確認頁面 (Upgraded Review Page)
# ==========================================
elif st.session_state.authenticated and st.session_state.exam_step == 4:
    st.markdown("<h2 style='text-align: center;'>📋 Exam Review & Question Checklist</h2>", unsafe_allow_html=True)
    st.write("Review your answered, unanswered, and flagged questions below. Click **'Go to Q...'** next to any question to instantly jump back to it and revise your answer.")
    st.write("---")

    total_q_count = len(st.session_state.get("exam_questions", [])) or 75
    answered_cnt = len(st.session_state.get("answers", {}))
    unanswered_cnt = total_q_count - answered_cnt
    flagged_cnt = len(st.session_state.get("flagged_questions", set()))
    focus_warnings = st.session_state.get("focus_loss_count", 0)

    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
    col_m1.metric("Answered", answered_cnt)
    col_m2.metric("Unanswered", unanswered_cnt)
    col_m3.metric("Flagged", flagged_cnt)
    col_m4.metric("Warnings", focus_warnings)

    st.markdown("---")
    st.markdown("### Detailed Question Status List")

    # Render an itemized review list with jump buttons for every question
    user_answers = st.session_state.get("answers", {})
    flagged_set = st.session_state.get("flagged_questions", set())

    for q_num in range(1, total_q_count + 1):
        is_answered = q_num in user_answers
        is_flagged = q_num in flagged_set
        
        status_badge = "🟢 Answered" if is_answered else "⚪ Unanswered"
        if is_flagged:
            status_badge += " | ⭐ Flagged"

        ans_preview = user_answers.get(q_num, "No answer selected yet")
        if len(str(ans_preview)) > 60:
            ans_preview = str(ans_preview)[:57] + "..."

        with st.container():
            col_info, col_action = st.columns([4, 1])
            with col_info:
                st.markdown(f"**Q{q_num}** [{status_badge}]<br><small style='color: #64748b;'>Selected: {ans_preview}</small>", unsafe_allow_html=True)
            with col_action:
                if st.button(f"Go to Q{q_num}", key=f"review_jump_{q_num}", use_container_width=True):
                    st.session_state.current_q = q_num
                    st.session_state.exam_step = 3
                    st.rerun()
            st.divider()

    st.markdown("---")
    st.warning("⚠️ Once you click **Confirm and Submit Exam**, your answers will be finalized and sent to the examination database. You cannot make any further changes.")

    col_sub1, col_sub2 = st.columns(2)
    with col_sub1:
        if st.button("⬅️ Return to Exam", use_container_width=True):
            st.session_state.exam_step = 3
            st.rerun()

    with col_sub2:
        if st.button("✅ Confirm and Submit Exam", type="primary", use_container_width=True):
            with st.spinner("Submitting exam and recording results..."):
                try:
                    answered_count = len(st.session_state.get("answers", {}))
                    focus_losses = st.session_state.get("focus_loss_count", 0)
                    
                    correct_count = 0
                    exam_questions = st.session_state.get("exam_questions", [])
                    
                    for idx, q_data in enumerate(exam_questions, start=1):
                        user_ans = str(user_answers.get(idx, "")).strip()
                        correct_letter = str(q_data.get("CorrectAnswer", "")).strip().upper()
                        correct_text = str(q_data.get(f"Option{correct_letter}", "")).strip()
                        if user_ans and (user_ans.upper() == correct_letter or user_ans == correct_text):
                            correct_count += 1
                    
                    passing_score_percentage = 70.0
                    score_percentage = (correct_count / total_q_count) * 100 if total_q_count > 0 else 0
                    final_status = "Pass" if score_percentage >= passing_score_percentage else "Fail"
                    
                    finalize_exam_submission(
                        st.session_state.voucher_code,
                        focus_losses,
                        final_status,
                        explanation=f"Answered {answered_count}/{total_q_count}, Correct {correct_count}"
                    )
                    
                    st.session_state.exam_final_status = final_status
                    st.session_state.exam_correct_count = correct_count
                    st.session_state.exam_step = 5
                    st.rerun()
                except Exception as e:
                    st.error(f"Submission error: {e}")


# ==========================================
# Step 5 - 考試結果與結算頁面
# ==========================================
elif st.session_state.authenticated and st.session_state.exam_step == 5:
    st.markdown("<h2 style='text-align: center;'>📋 Examination Result & Summary</h2>", unsafe_allow_html=True)
    st.write("---")
    
    status = st.session_state.get("exam_final_status", "Submitted")
    correct_cnt = st.session_state.get("exam_correct_count", 0)
    answered_cnt = len(st.session_state.get("answers", {}))
    total_q_count = len(st.session_state.get("exam_questions", [])) or 75
    focus_warnings = st.session_state.get("focus_loss_count", 0)
    
    if status == "Pass":
        st.success("🎉 **CONGRATULATIONS! You have PASSED the examination.**")
    else:
        st.error("❌ **EXAMINATION RESULT: FAIL.** You did not meet the passing criteria.")
        
    st.write(f"Candidate: **{st.session_state.get('candidate_name', 'Candidate')}** ({st.session_state.get('candidate_email', '')})")
    
    col_res1, col_res2, col_res3, col_res4 = st.columns(4)
    col_res1.metric("Final Status", status)
    col_res2.metric("Questions Answered", f"{answered_cnt} / {total_q_count}")
    col_res3.metric("Focus Warnings", focus_warnings)
    col_res4.metric("Exam Outcome", "Completed")
    
    st.markdown("---")
    st.info("💡 Your results and timestamps have been securely recorded in the official examination database (Google Sheets).")
    
    if st.button("🚪 Exit Examination Portal", use_container_width=True):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()
