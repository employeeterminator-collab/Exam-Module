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
    
    /* 隱藏所有 Markdown 標題的錨點連結圖示 */
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

# 🟢 記錄第一次開始考試的時間 (Committed)
def update_voucher_committed(voucher_code):
    try:
        db = get_sheets_connection()
        sheet = db.worksheet("Vouchers")
        cell = sheet.find(voucher_code)
        if cell:
            # 檢查目前 Column 10 (Committed) 是否已經有值，如果沒有才寫入
            current_value = sheet.cell(cell.row, 10).value
            if not current_value or str(current_value).strip() == "":
                current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                sheet.update_cell(cell.row, 10, current_time)
    except Exception as e:
        print(f"Failed to update Committed time: {e}")

# 🟢 【新加入】記錄單次違規事件到 ViolationLogs Tab
def log_violation_to_sheet(voucher_code):
    try:
        db = get_sheets_connection()
        logs_sheet = db.worksheet("ViolationLogs")
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # 寫入新的一行：[Voucher, Offended Timestamp]
        logs_sheet.append_row([voucher_code, current_time])
    except Exception as e:
        print(f"Failed to log violation: {e}")


# 🟢 【新加入】完成考試時更新狀態 (CompletedExam, WarningCount, ExamStatus, CandidateExplanation)
def finalize_exam_submission(voucher_code, warning_count, exam_status, explanation=""):
    try:
        db = get_sheets_connection()
        sheet = db.worksheet("Vouchers")
        cell = sheet.find(voucher_code)
        if cell:
            completed_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # 請根據你的 Google Sheets 實際欄位順序調整：
            # 假設 Column J: CompletedExam, Column K: WarningCount, Column L: ExamStatus, Column M: CandidateExplanation
            sheet.update_cell(cell.row, 9, completed_time)  # CompletedExam 時間
            sheet.update_cell(cell.row, 11, warning_count)   # WarningCount
            sheet.update_cell(cell.row, 12, exam_status)     # ExamStatus (Pass / Fail / Pending)
            sheet.update_cell(cell.row, 13, explanation)     # CandidateExplanation
    except Exception as e:
        print(f"Failed to finalize exam submission: {e}")

# 🟢 放在頂部的 Helper 函式區塊
def update_exam_end_time(voucher_code, status_text):
    try:
        db = get_sheets_connection()
        sheet = db.worksheet("Vouchers")
        cell = sheet.find(voucher_code)
        if cell:
            # 檢查 Column 12 (ExamEndTime) 是否已經有記錄，避免重複覆寫
            current_val = sheet.cell(cell.row, 12).value
            if not current_val or str(current_val).strip() == "":
                current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                sheet.update_cell(cell.row, 12, current_time)
    except Exception as e:
        print(f"Failed to update ExamEndTime: {e}")

def log_violation_to_sheet(voucher_code):
    try:
        db = get_sheets_connection()
        # 確保你的 Google Sheets 裡面有一個叫做 "ViolationLogs" 的分頁
        sheet = db.worksheet("ViolationLogs")
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 寫入格式：[Voucher Code, 違規時間, 違規類型]
        sheet.append_row([voucher_code, current_time, "Focus Lost / Tab Switched"])
    except Exception as e:
        print(f"Error logging violation to Google Sheets: {e}")

# ==========================================
# Step 0 - 考生身分驗證、重連與憑證確認
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
      if (
          not email_input
          or not voucher_input
          or not email_input.strip()
          or not voucher_input.strip()
      ):
        st.error("Please enter both your Email and Voucher Code.")
      else:
        try:
          db = get_sheets_connection()
          vouchers_sheet = db.worksheet("Vouchers")
          records = vouchers_sheet.get_all_records()

          matched_record = None
          row_index = None

          # 尋找匹配的記錄（比對 Voucher 與 Email）
          for idx, record in enumerate(records, start=2): # gspread row 從 2 開始 (含 Header)
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
            completed_exam = str(matched_record.get("CompletedExam", "")).strip()
            committed_time = str(matched_record.get("Committed", "")).strip()

            # 1. 檢查是否已經完成過考試（永久鎖定）
            if completed_exam != "":
              st.error("❌ This exam has already been completed. You cannot log in again with this voucher.")
            else:
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

             # 2. 判斷是否為中途斷線重連 (Resume Exam 情況)
              if committed_time != "":
                try:
                    committed_dt = datetime.datetime.strptime(committed_time, "%Y-%m-%d %H:%M:%S")
                    elapsed_seconds = (datetime.datetime.now() - committed_dt).total_seconds()
                    
                    # 超過 90 分鐘 (5400秒) 判定為 DNF（若你的考試時間是 60 分鐘則改為 3600）
                    EXAM_TIME_LIMIT = 5400 
                    
                    if elapsed_seconds > EXAM_TIME_LIMIT:
                        # 檢查 Column 12 (ExamStatus) 是否已經寫入過，避免重複寫入
                        exam_end_val = vouchers_sheet.cell(row_index, 12).value  
                        if not exam_end_val or str(exam_end_val).strip() == "":
                            vouchers_sheet.update_cell(row_index, 12, "DNF")
                            
                        st.error("❌ **Exam Expired:** Your examination window has elapsed. Your status has been recorded as **DNF** (Did Not Finish). Please contact the exam administrator.")
                        st.stop()  # 阻斷後續程式碼，禁止進入
                    else:
                        # 仍在時限內，允許重連繼續考試
                        st.session_state.exam_step = 3
                        st.success("🔄 Detected an active session. Resuming your exam...")
                        time.sleep(1)
                        st.rerun()
                except Exception as e:
                    print(f"Failed to check DNF: {e}")
                    # 若時間解析發生例外，安全起見仍導向考題或報錯
                    st.session_state.exam_step = 3
                    st.rerun()
              else:
                # 尚未開始過考試，正常進入 Step 1 (身分核對與考試須知)
                st.session_state.exam_step = 1
                st.rerun()
                  
        except Exception as e:
          st.error(f"Connection error: {e}")

# ==========================================
# Step 1 - 身分核對與考試須知
# ==========================================
elif st.session_state.authenticated and st.session_state.exam_step == 1:
  st.markdown(
      f"### Welcome, {st.session_state.candidate_first_name}"
      f" {st.session_state.candidate_last_name}!"
  )
  st.write("---")

  st.markdown("### Step 1: Candidate Information Verification")
  st.write("Please carefully verify your registered information below:")

  st.markdown(f"""
    - **1. Last Name:** {st.session_state.candidate_last_name}
    - **2. First Name:** {st.session_state.candidate_first_name}
    - **3. Japanese Name:** {st.session_state.candidate_japanese_name}
    - **4. Email Address:** {st.session_state.candidate_email}
    """)

  st.warning(
      "⚠️ If the above information is incorrect or missing, please end the"
      " exam now and contact administrator."
  )

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
  
  # 如果正在休息，顯示倒數計時畫面
  if st.session_state.on_break:
    st.markdown("<h2 style='text-align: center;'>Pre-Exam Candidate Transition Pause</h2>", unsafe_allow_html=True)
    st.write(
        "<p style='text-align: center;'>Your photo has been successfully verified. "
        "Take a brief break before your core examination begins. "
        "The exam will start automatically when the timer expires."
        "Once the exam started, your voucher will be count as used and committed.</p>",
        unsafe_allow_html=True,
    )
    st.write("---")

    TOTAL_SECONDS = 5 * 60  # 5 分鐘
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

  # 否則，顯示拍照驗證畫面
  else:
    st.markdown("### Step 3: Candidate Photo Verification")
    st.write(
        f"Candidate: **{st.session_state.candidate_name}**"
        f" ({st.session_state.candidate_email})"
    )

    if "photo_attempts" not in st.session_state:
      st.session_state.photo_attempts = 0

    MAX_ATTEMPTS = 3
    remaining_attempts = MAX_ATTEMPTS - st.session_state.photo_attempts

    if remaining_attempts <= 0:
      st.error(
          "❌ You have exceeded the maximum allowed photo verification attempts"
          f" ({MAX_ATTEMPTS}/{MAX_ATTEMPTS}). Your session is locked. Please"
          " contact the administrator."
      )
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

                # 啟動休息倒數，並切換狀態
                st.session_state.on_break = True
                st.session_state.break_start_time = time.time()
                st.rerun()
              else:
                error_msg = result.get("error", {}).get("message", "Unknown error")
                st.error(
                    f"Upload failed: {error_msg}. Please try again."
                    f" ({MAX_ATTEMPTS - st.session_state.photo_attempts} attempts left)"
                )
                st.rerun()

            except Exception as e:
              st.error(
                  f"An unexpected error occurred: {e}."
                  f" ({MAX_ATTEMPTS - st.session_state.photo_attempts} attempts left)"
              )
              st.rerun()

# ==========================================
# Step 3 - 核心問答模組 (含全螢幕前置解鎖屏)
# ==========================================
elif st.session_state.authenticated and st.session_state.exam_step == 3:
    
    # 🚨 1. 優先檢查是否有來自前端的違規訊號 (放這裡最安全、最優先)
    query_params = st.query_params
    if "violation_triggered" in query_params:
        # 本地計數器 +1
        st.session_state.focus_loss_count = st.session_state.get("focus_loss_count", 0) + 1
        
        # 寫入 Google Sheets 的 ViolationLogs Tab
        voucher = st.session_state.get("voucher_code", "UNKNOWN")
        log_violation_to_sheet(voucher)
        
        # 清除 query param 並重新整理畫面，避免重複觸發
        st.query_params.clear()
        st.rerun()

    # 2. 初始化 Step 3 變數
    if "current_q" not in st.session_state:
        st.session_state.current_q = 1
    if "answers" not in st.session_state:
        st.session_state.answers = {}  
    if "flags" not in st.session_state:
        st.session_state.flags = set()  
    if "focus_loss_count" not in st.session_state:
        st.session_state.focus_loss_count = 0

    # 注入頂部防作弊警告 Banner
    st.components.v1.html("""
        <script>
            if (!parent.document.getElementById('global-warning-banner')) {
                const banner = parent.document.createElement('div');
                banner.id = 'global-warning-banner';
                banner.style.cssText = `
                    position: fixed; top: 0; left: 0; width: 100vw;
                    background-color: #dc2626; color: white; text-align: center; 
                    padding: 16px 20px; font-family: sans-serif; font-weight: bold; 
                    font-size: 15px; box-shadow: 0 4px 15px rgba(0,0,0,0.4);
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
                    bannerTimer = setTimeout(() => { b.style.display = 'none'; }, 8000);
                }
            }
            parent.document.addEventListener("visibilitychange", function() { if (parent.document.hidden) triggerGlobalWarning(); });
            parent.window.addEventListener("blur", function() { triggerGlobalWarning(); });
        </script>
    """, height=0)

    # 接下來接你原本的標頭區、時鐘、題目導航與 75 題內容... 

    
    
# ==========================================
# Step 3 - 核心問答模組
# ==========================================


    # --- [1] 初始化 Step 3 變數 ---
    if "current_q" not in st.session_state:
        st.session_state.current_q = 1
    if "answers" not in st.session_state:
        st.session_state.answers = {}  
    if "flags" not in st.session_state:
        st.session_state.flags = set()  
    if "focus_loss_count" not in st.session_state:
        st.session_state.focus_loss_count = 0

    

    # --- [3] 接下來接你原本的計時器與題目介面 ---
    TOTAL_QUESTIONS = 75
    # ... (其餘程式碼)

    
    EXAM_DURATION_SECONDS = 5400
    # --- [2] 注入頂部防作弊監控 Banner (純淨執行，絕不干擾計時器) ---
    st.components.v1.html("""
        <script>
            // 確保只建立一次頂部警告 Banner
            if (!parent.document.getElementById('global-warning-banner')) {
                const banner = parent.document.createElement('div');
                banner.id = 'global-warning-banner';
                banner.style.cssText = `
                    position: fixed;
                    top: 0; 
                    left: 0; 
                    width: 100vw;
                    background-color: #dc2626; 
                    color: white;
                    text-align: center; 
                    padding: 16px 20px;
                    font-family: sans-serif; 
                    font-weight: bold; 
                    font-size: 15px;
                    line-height: 1.4;
                    box-shadow: 0 4px 15px rgba(0,0,0,0.4);
                    z-index: 2147483647; 
                    display: none; 
                    box-sizing: border-box;
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
                    }, 8000); // 顯示 8 秒後自動隱藏
                }
            }

            // A. 偵測開新分頁 / 隱藏畫面
            parent.document.addEventListener("visibilitychange", function() {
                if (parent.document.hidden) {
                    triggerGlobalWarning();
                }
            });

            // B. 偵測視窗失去焦點 (Blur)
            parent.window.addEventListener("blur", function() {
                triggerGlobalWarning();
            });

            // C. 偵測滑鼠移出視窗邊界
            parent.document.addEventListener("mouseleave", function(e) {
                if (e.clientY <= 0 || e.clientX <= 0 || e.clientX >= parent.window.innerWidth || e.clientY >= parent.window.innerHeight) {
                    triggerGlobalWarning();
                }
            });
        </script>
    """, height=0)



    TOTAL_QUESTIONS = 75

    # --- [4] 頂部標頭區 (候選人資訊、時鐘、相機) ---
    header_col1, header_col2, header_col3 = st.columns([2, 1, 1])
    
    with header_col1:
        st.markdown(f"### 👤 Candidate: {st.session_state.get('candidate_name', 'User')}")
        st.write(f"Email: {st.session_state.get('candidate_email', '')}")

    # (接下來接你原本的題目選單、計時器邏輯與答題介面...)
        if st.session_state.focus_loss_count > 0:
            st.error(f"🚨 Inappropriate movement detected: {st.session_state.focus_loss_count} time(s)")
   
    with header_col2:
        # 🟢 快取機制：只在第一次進入考試時向 Google Sheets 查詢一次，之後直接從 session_state 讀取
        if "exam_remaining_seconds" not in st.session_state:
            initial_remaining = 5400
            try:
                db = get_sheets_connection()
                sheet = db.worksheet("Vouchers")
                cell = sheet.find(st.session_state.voucher_code)
                if cell:
                    committed_str = sheet.cell(cell.row, 10).value  # Column 10 是 Committed
                    if committed_str and str(committed_str).strip() != "":
                        committed_time = datetime.datetime.strptime(str(committed_str).strip(), "%Y-%m-%d %H:%M:%S")
                        elapsed_seconds = int((datetime.datetime.now() - committed_time).total_seconds())
                        initial_remaining = max(0, 5400 - elapsed_seconds)
            except Exception as e:
                print(f"Error calculating initial remaining time: {e}")
            
            st.session_state.exam_remaining_seconds = initial_remaining
            st.session_state.exam_timer_start_local = time.time()

        # 根據本地流逝的時間精準扣減，不再頻繁打 Google Sheets API
        elapsed_local = int(time.time() - st.session_state.exam_timer_start_local)
        remaining_seconds = max(0, st.session_state.exam_remaining_seconds - elapsed_local)

        # 使用普通字串搭配 .replace()，完美解決 JavaScript 大括號與 Python f-string 衝突的問題
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

                function updateCountdown() {
                    const now = Date.now();
                    let timeLeft = Math.floor((endTime - now) / 1000);
                    if (timeLeft < 0) timeLeft = 0;

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
        
        # 安全替換變數
        timer_html = timer_html.replace('VOUCHER_PLACEHOLDER', str(st.session_state.voucher_code))
        timer_html = timer_html.replace('SERVER_REMAINING_PLACEHOLDER', str(remaining_seconds))

        st.components.v1.html(timer_html, height=75)
           
    with header_col3:
        # 放大 20% 的綠色相機預覽框
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

    # --- [2] 側邊欄 (防作弊與導覽) ---
    with st.sidebar:
        st.markdown("### 📹 Security Status")
        st.markdown("""
            <div style="border: 2px dashed #22c55e; padding: 10px; border-radius: 8px; text-align: center; background-color: #f0fdf4;">
                <div style="color: #15803d; font-weight: bold; font-size: 12px;">🟢 Focus Guard Active</div>
            </div>
        """, unsafe_allow_html=True)

        st.markdown("---")
        st.markdown("### 🗺️ Question Palette (1–75)")
        st.markdown("<small>🟢 Answered | ⚪ Unanswered | ⭐ Flagged</small>", unsafe_allow_html=True)
        
        cols_per_row = 5
        for i in range(1, TOTAL_QUESTIONS + 1, cols_per_row):
            cols = st.columns(cols_per_row)
            for j in range(cols_per_row):
                q_num = i + j
                if q_num <= TOTAL_QUESTIONS:
                    label = f"⭐{q_num}" if q_num in st.session_state.flags else f"{q_num}"
                    if cols[j].button(label, key=f"pal_{q_num}", use_container_width=True):
                        st.session_state.current_q = q_num
                        st.rerun()

    # --- [3] 主畫面區域 (Main Content Area) ---
    q_idx = st.session_state.current_q

    st.markdown(f"#### Question {q_idx} of {TOTAL_QUESTIONS} — Multiple Choice")
    st.progress(q_idx / TOTAL_QUESTIONS)

    st.markdown(f"""
    > **Scenario / Question Text for Q{q_idx}:**  
    > According to the Shisa Kanko (Pointing and Calling) safety protocols, what is the primary cognitive benefit of executing a physical point paired with a verbal command during a critical operational check?
    """)

    options = [
        "A. It reduces muscular fatigue during long shifts.",
        "B. It enhances consciousness and reduces operational errors by synchronizing brain and sensory alertness.",
        "C. It replaces the need for standard digital logging.",
        "D. It is purely ceremonial and has no measurable safety impact."
    ]

    current_answer = st.session_state.answers.get(q_idx, None)
    selected = st.radio(
        "Select your answer:", 
        options, 
        index=options.index(current_answer) if current_answer in options else None, 
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

# --- [4] 僅保留頂部防作弊警告監控（絕不干擾計時器與畫面） ---
    st.components.v1.html("""
        <script>
            if (!parent.document.getElementById('global-warning-banner')) {
                const banner = parent.document.createElement('div');
                banner.id = 'global-warning-banner';
                banner.style.cssText = `
                    position: fixed;
                    top: 0; left: 0; width: 100vw;
                    background-color: #dc2626; color: white;
                    text-align: center; padding: 16px 20px;
                    font-family: sans-serif; font-weight: bold; font-size: 15px;
                    box-shadow: 0 4px 15px rgba(0,0,0,0.4);
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
                    bannerTimer = setTimeout(() => { b.style.display = 'none'; }, 8000);
                }
            }

            // 僅純粹監控分頁切換與視窗失去焦點
            parent.document.addEventListener("visibilitychange", function() { if (parent.document.hidden) triggerGlobalWarning(); });
            parent.window.addEventListener("blur", function() { triggerGlobalWarning(); });
        </script>
    """, height=0)

# ==========================================
# Step 4 - Exam Review & Final Submission (檢視與交卷前確認頁面)
# ==========================================
elif st.session_state.authenticated and st.session_state.exam_step == 4:
    
    st.markdown("<h2 style='text-align: left;'>📋 Exam Review & Final Submission</h2>", unsafe_allow_html=True)
    st.write("Review your completion status below before submitting your final paper.")
    st.write("---")
    
    # 1. 統計各項數據
    total_questions = 75
    user_answers = st.session_state.get("answers", {})
    answered_count = len(user_answers)
    unanswered_count = total_questions - answered_count
    
    # 統計被標記 (Flagged) 的題數
    flagged_questions = st.session_state.get("flagged_questions", set())
    flagged_count = len(flagged_questions)
    
    # 專注度警告次數
    focus_losses = st.session_state.get("focus_loss_count", 0)
    
    # 2. 呈現數據指標看板
    col_v1, col_v2, col_v3, col_v4 = st.columns(4)
    col_v1.metric("Answered", f"{answered_count} / {total_questions}")
    col_v2.metric("Unanswered", unanswered_count)
    col_v3.metric("Flagged", flagged_count)
    col_v4.metric("Focus Losses", focus_losses)
    
    # 若有未作答或被標記的題目，給予溫馨提醒
    if unanswered_count > 0:
        st.warning(f"⚠️ You currently have **{unanswered_count}** unanswered question(s). You can still return to answer them.")
    if flagged_count > 0:
        # 🟢 修正此處：移除了原本卡在裡面的多餘 📤 字元
        st.info(f"📌 You have flagged **{flagged_count}** question(s) for review.")
        
    st.write("---")
    
    # 3. 底部操作按鈕：返回考試 vs 確認交卷
    col_act1, col_act2 = st.columns(2)
    
    with col_act1:
        if st.button("⬅️ Return to Exam", use_container_width=True):
            st.session_state.exam_step = 3  # 回到答題頁面
            st.rerun()
            
    with col_act2:
        if st.button("🔒 Finish & Submit Exam", type="primary", use_container_width=True):
            # 點擊後推進到結算與評分頁面 (Step 5)
            st.session_state.exam_step = 5 
            st.rerun()


# ==========================================
# Step 4 - 考試結果與結算頁面 (Pass / Fail & Result Page)
# ==========================================
elif st.session_state.authenticated and st.session_state.exam_step == 5:
    
    # 確保寫入 Google Sheets 的動作在整個 Session 中只執行一次，防止雙重寫入或覆蓋
    if not st.session_state.get("exam_sheets_updated", False):
        try:
            answered_count = len(st.session_state.get("answers", {}))
            focus_losses = st.session_state.get("focus_loss_count", 0)
            
            # 💡 範例評分邏輯：假設總題數 75 題，你可以比對答案算出正確題數
            # 這裡示範如何計算分數與判定 Pass / Fail（可根據你的答題對照表調整）
            correct_count = 0
            user_answers = st.session_state.get("answers", {})
            correct_answer_key = st.session_state.get("correct_answers", {}) # 假設你有正確答案字典
            
            for q_idx, user_ans in user_answers.items():
                if correct_answer_key.get(q_idx) == user_ans:
                    correct_count += 1
            
            # 若沒有設定對照表，這裡先以答對率或預設邏輯為例（例如答對幾題及格，門檻可自行調整）
            passing_score_percentage = 70.0 # 70% 及格
            score_percentage = (correct_count / 75.0) * 100 if 75 > 0 else 0
            
            final_status = "Pass" if score_percentage >= passing_score_percentage else "Fail"
            
            # 連線 Google Sheets 寫入資料
            db = get_sheets_connection()
            sheet = db.worksheet("Vouchers")
            cell = sheet.find(st.session_state.voucher_code)
            if cell:
                current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                # 1. 寫入交卷時間到 Column 12 (ExamEndTime)
                sheet.update_cell(cell.row, 12, current_time) 
                
                # 2. 寫入 Pass 或 Fail 狀態到 Column 13 (ExamStatus)
                sheet.update_cell(cell.row, 13, final_status)
            
            # 鎖定標記，避免重複寫入
            st.session_state.exam_sheets_updated = True
            st.session_state.exam_final_status = final_status
            st.session_state.exam_correct_count = correct_count
            
        except Exception as e:
            print(f"Error updating exam result to Google Sheets: {e}")

    # --- 畫面呈現：Exam Result Page ---
    st.markdown("<h2 style='text-align: center;'>📋 Examination Result & Summary</h2>", unsafe_allow_html=True)
    st.write("---")
    
    # 取得存在 session 中的最終狀態
    status = st.session_state.get("exam_final_status", "Submitted")
    correct_cnt = st.session_state.get("exam_correct_count", 0)
    answered_cnt = len(st.session_state.get("answers", {}))
    focus_warnings = st.session_state.get("focus_loss_count", 0)
    
    # 呈現大大的 Pass / Fail 狀態提醒框
    if status == "Pass":
        st.success("🎉 **CONGRATULATIONS! You have PASSED the examination.**")
    else:
        st.error("❌ **EXAMINATION RESULT: FAIL.** You did not meet the passing criteria.")
        
    st.write(f"Candidate: **{st.session_state.get('candidate_name', 'Candidate')}** ({st.session_state.get('candidate_email', '')})")
    
    # 數據指標看板
    col_res1, col_res2, col_res3, col_res4 = st.columns(4)
    col_res1.metric("Final Status", status)
    col_res2.metric("Questions Answered", f"{answered_cnt} / 75")
    col_res3.metric("Focus Warnings", focus_warnings)
    col_res4.metric("Exam Outcome", "Completed")
    
    st.markdown("---")
    st.info("💡 Your results and timestamps have been securely recorded in the official examination database (Google Sheets).")
    
    # 離開按鈕
    if st.button("🚪 Exit Examination Portal", use_container_width=True):
        # 清除所有 Session 狀態，安全登出
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()
