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

# 完成考試時更新狀態
def finalize_exam_submission(voucher_code, warning_count, exam_status, explanation=""):
    try:
        db = get_sheets_connection()
        sheet = db.worksheet("Vouchers")
        cell = sheet.find(voucher_code)
        if cell:
            completed_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            sheet.update_cell(cell.row, 12, completed_time)  # CompletedExam / Photo URL
            sheet.update_cell(cell.row, 11, warning_count) # WarningCount
            sheet.update_cell(cell.row, 13, exam_status)   # ExamStatus / EndTime
            sheet.update_cell(cell.row, 14, explanation)   # Explanation
    except Exception as e:
        print(f"Failed to finalize exam submission: {e}")

 # 取得題庫資料
def get_exam_questions():
    try:
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ]
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        client = gspread.authorize(creds)
        
        # Open the separate Google Sheet file named "Questions"
        spreadsheet = client.open("A")
        # Pull records from the first worksheet (or specify .worksheet("SheetName") if needed)
        sheet = spreadsheet.get_worksheet(0)
        records = sheet.get_all_records()
        return records
    except Exception as e:
        print(f"Failed to fetch questions from separate file: {e}")
        return []


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
            # Fetch direct row values by exact column index to prevent header naming mismatches
            row_vals = vouchers_sheet.row_values(row_index)
            
            committed_time = row_vals[9].strip() if len(row_vals) > 9 else str(matched_record.get("Committed", "")).strip()
            completed_exam_val = row_vals[11].strip() if len(row_vals) > 11 else str(matched_record.get("CompletedExam", "")).strip()
            exam_end_val = row_vals[12].strip() if len(row_vals) > 12 else str(matched_record.get("ExamEndTime", "")).strip()

            # 🛡️ STRICT BLOCK: If the exam was already finished, passed, failed, or DNF'd, deny entry permanently
            if completed_exam_val not in ["", "DNF"] or exam_end_val in ["Pass", "Fail", "DNF"]:
              st.error("❌ **Access Denied:** This examination has already been completed, submitted, or expired using this voucher. Re-entry is strictly prohibited.")
            
            # ⏳ RESTORED DNF & EXPIRED TIME CHECK: Check if already timed out (90 minutes limit)
            elif committed_time != "":
              try:
                committed_dt = datetime.datetime.strptime(committed_time, "%Y-%m-%d %H:%M:%S")
                elapsed_seconds = (datetime.datetime.now() - committed_dt).total_seconds()
                EXAM_TIME_LIMIT = 5400  # 90 minutes

                if elapsed_seconds > EXAM_TIME_LIMIT:
                    if exam_end_val != "DNF":
                        vouchers_sheet.update_cell(row_index, 13, "DNF")
                    st.error("❌ **Access Denied:** Exam session expired (Time limit exceeded). Status updated to DNF.")
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


# 取得題庫資料
def get_exam_questions():
    try:
        db = get_sheets_connection()
        sheet = db.worksheet("Questions")
        records = sheet.get_all_records()
        return records
    except Exception as e:
        print(f"Failed to fetch questions: {e}")
        return []

# --- END OF STEP 3 ---
    b_col1, b_col2, b_col3 = st.columns([2, 3, 2])
    with b_col2:
        if st.button("📋 Review & Finish Exam", type="primary", use_container_width=True):
            st.session_state.exam_step = 4
            st.rerun()
# ==========================================
# Step 3 - Core Examination Room (Questions & Answers)
# ==========================================
if st.session_state.authenticated and st.session_state.exam_step == 3:
    # Fetch questions if not already cached in session state
    if "exam_questions" not in st.session_state or not st.session_state.exam_questions:
        st.session_state.exam_questions = get_exam_questions()

    exam_questions = st.session_state.get("exam_questions", [])
    
    if not exam_questions:
        st.error("❌ Failed to load exam questions from the database. Please check your connection or contact the administrator.")
    else:
        total_q_count = len(exam_questions)
        
        # Initialize current question index pointer if not present
        if "current_q" not in st.session_state:
            st.session_state.current_q = 1

        current_idx = st.session_state.current_q - 1
        current_q_data = exam_questions[current_idx]

        # Top progress bar and header info
        st.markdown(f"### 🛡️ Shisa Kanko-Shi Examination Room")
        progress_val = st.session_state.current_q / total_q_count
        st.progress(progress_val)
        st.write(f"Question **{st.session_state.current_q}** of **{total_q_count}**")
        st.markdown("---")

        # Display question content
        q_text = current_q_data.get("Question", "Question text unavailable.")
        st.markdown(f"#### Q{st.session_state.current_q}. {q_text}")

        # Extract options (assuming columns OptionA, OptionB, OptionC, OptionD)
        options = []
        for opt_key in ["OptionA", "OptionB", "OptionC", "OptionD"]:
            val = current_q_data.get(opt_key, "")
            if val and str(val).strip() != "":
                options.append(str(val).strip())

        # Retrieve saved answers
        if "answers" not in st.session_state:
            st.session_state.answers = {}

        current_answer = st.session_state.answers.get(st.session_state.current_q, None)
        
        # Determine option index for radio button default
        default_index = 0
        if current_answer in options:
            default_index = options.index(current_answer)

        # Radio button selection
        selected_option = st.radio(
            "Select your answer:",
            options,
            index=default_index,
            key=f"q_radio_{st.session_state.current_q}"
        )

        # Save answer on selection update
        if selected_option:
            st.session_state.answers[st.session_state.current_q] = selected_option

        st.markdown("<br>", unsafe_allow_html=True)

        # Navigation and Flagging controls
        col_nav1, col_nav2, col_nav3 = st.columns(3)
        
        with col_nav1:
            if st.session_state.current_q > 1:
                if st.button("⬅️ Previous Question", use_container_width=True):
                    st.session_state.current_q -= 1
                    st.rerun()

        with col_nav2:
            is_flagged = st.session_state.current_q in st.session_state.flagged_questions
            flag_label = "⭐ Unflag Question" if is_flagged else "☆ Flag for Review"
            if st.button(flag_label, use_container_width=True):
                if is_flagged:
                    st.session_state.flagged_questions.remove(st.session_state.current_q)
                else:
                    st.session_state.flagged_questions.add(st.session_state.current_q)
                st.rerun()

        with col_nav3:
            if st.session_state.current_q < total_q_count:
                if st.button("Next Question ➡️", use_container_width=True, type="primary"):
                    st.session_state.current_q += 1
                    st.rerun()

        st.markdown("---")
        
        # Jump or Review trigger footer
        b_col1, b_col2, b_col3 = st.columns([2, 3, 2])
        with b_col2:
            if st.button("📋 Review & Finish Exam", type="primary", use_container_width=True):
                st.session_state.exam_step = 4
                st.rerun()
# ==========================================
# Step 4 - Review and Submit Page
# ==========================================
if st.session_state.authenticated and st.session_state.exam_step == 4:
    st.markdown("### 📋 Examination Review & Submission")
    st.write("Please review your progress below before submitting your final answers.")

    total_q_count = len(st.session_state.get("exam_questions", [])) or 75
    answered_count = len(st.session_state.get("answers", {}))
    flagged_count = len(st.session_state.get("flagged_questions", set()))

    col_stat1, col_stat2, col_stat3 = st.columns(3)
    with col_stat1:
        st.metric("Total Questions", total_q_count)
    with col_stat2:
        st.metric("Answered", answered_count)
    with col_stat3:
        st.metric("Flagged for Review", flagged_count)

    st.markdown("---")
    st.markdown("#### 🔍 Question Status Summary")

    for q_num in range(1, total_q_count + 1):
        has_answered = q_num in st.session_state.get("answers", {})
        is_flagged = q_num in st.session_state.get("flagged_questions", set())
        
        status_icon = "🟢 Answered" if has_answered else "⚪ Unanswered"
        if is_flagged:
            status_icon += " | ⭐ Flagged"

        c1, c2, c3 = st.columns([1, 4, 2])
        with c1:
            st.write(f"**Q{q_num}**")
        with c2:
            st.write(status_icon)
        with c3:
            if st.button(f"Jump to Q{q_num}", key=f"review_jump_{q_num}"):
                st.session_state.current_q = q_num
                st.session_state.exam_step = 3
                st.rerun()

    st.markdown("---")

    col_sub1, col_sub2 = st.columns(2)
    with col_sub1:
        if st.button("⬅️ Return to Exam", use_container_width=True):
            st.session_state.exam_step = 3
            st.rerun()

    with col_sub2:
        if st.button("✅ Confirm and Submit Exam", type="primary", use_container_width=True):
            with st.spinner("Submitting exam and recording results..."):
                try:
                    focus_losses = st.session_state.get("focus_loss_count", 0)
                    correct_count = 0
                    user_answers = st.session_state.get("answers", {})
                    exam_questions = st.session_state.get("exam_questions", [])
                    
                    # Grade dynamically using the 'CorrectAnswer' column from Google Sheets
                    for idx, q_data in enumerate(exam_questions, start=1):
                        user_ans = user_answers.get(idx, "")
                        correct_ans = str(q_data.get("CorrectAnswer", "")).strip()
                        if user_ans and user_ans == correct_ans:
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
    focus_warnings = st.session_state.get("focus_loss_count", 0)
    
    if status == "Pass":
        st.success("🎉 **CONGRATULATIONS! You have PASSED the examination.**")
    else:
        st.error("❌ **EXAMINATION RESULT: FAIL.** You did not meet the passing criteria.")
        
    st.write(f"Candidate: **{st.session_state.get('candidate_name', 'Candidate')}** ({st.session_state.get('candidate_email', '')})")
    
    col_res1, col_res2, col_res3, col_res4 = st.columns(4)
    col_res1.metric("Final Status", status)
    col_res2.metric("Questions Answered", f"{answered_cnt} / 75")
    col_res3.metric("Focus Warnings", focus_warnings)
    col_res4.metric("Exam Outcome", "Completed")
    
    st.markdown("---")
    st.info("💡 Your results and timestamps have been securely recorded in the official examination database (Google Sheets).")
    
    if st.button("🚪 Exit Examination Portal", use_container_width=True):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()
