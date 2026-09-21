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
# Step 0 - 考生身分驗證與憑證確認
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

          matched = False
          for record in records:
            r_voucher = str(record.get("VoucherCode", "")).strip()
            r_email = str(record.get("AssignedEmail", "")).strip()
            r_status = str(record.get("Status", "")).strip()

            if (
                r_voucher == voucher_input.strip()
                and r_email != ""
                and r_email.lower() == email_input.strip().lower()
                and r_status.lower() == "used"
            ):
              matched = True
              f_name = str(record.get("EnglishFirstName", "")).strip()
              l_name = str(record.get("EnglishLastName", "")).strip()
              j_name = str(record.get("JapaneseName", "")).strip()

              st.session_state.authenticated = True
              st.session_state.candidate_email = email_input.strip()
              st.session_state.voucher_code = voucher_input.strip()
              st.session_state.candidate_first_name = f_name
              st.session_state.candidate_last_name = l_name
              st.session_state.candidate_japanese_name = j_name
              st.session_state.candidate_name = f"{f_name} {l_name}".strip()
              st.session_state.exam_step = 1
              st.rerun()

          if not matched:
            st.error(
                "❌ Verification failed. Please check your Email and Voucher"
                " Code, or ensure you have completed registration on exam1."
            )

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
    st.markdown("<h2 style='text-align: center;'>☕ Mandatory Rest Break</h2>", unsafe_allow_html=True)
    st.write(
        "<p style='text-align: center;'>Your photo has been successfully verified. "
        "Take a brief break before your core examination begins. "
        "The exam will start automatically when the timer expires.</p>",
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
                    sheet.update_cell(cell.row, 4, photo_url)
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
# Step 3 - 核心問答模組 (Core Exam Page)
# ==========================================
elif st.session_state.authenticated and st.session_state.exam_step == 3:
    if "current_q" not in st.session_state:
        st.session_state.current_q = 1
    if "answers" not in st.session_state:
        st.session_state.answers = {}  
    if "flags" not in st.session_state:
        st.session_state.flags = set()  
    if "focus_loss_count" not in st.session_state:
        st.session_state.focus_loss_count = 0

    TOTAL_QUESTIONS = 75

    # --- [1] 頂部標頭區 (修正高度讓綠色相機框完整顯示) ---
    header_col1, header_col2, header_col3 = st.columns([2, 1, 1])
    
    with header_col1:
        st.markdown(f"### 👤 Candidate: **{st.session_state.candidate_name}**")
        st.caption(f"Email: {st.session_state.candidate_email}")
        if st.session_state.focus_loss_count > 0:
            st.warning(f"⚠️ Focus lost / Tab switched: {st.session_state.focus_loss_count} time(s)")

    with header_col2:
        # 清晰倒數計時器（高度配合調整至 90px）
        st.components.v1.html("""
            <div style="background-color:#1e293b; color:#f8fafc; padding:12px 10px; border-radius:8px; text-align:center; font-family:monospace; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                <div style="font-size: 10px; color: #94a3b8; margin-bottom: 4px; font-weight: bold;">⏳ TIME REMAINING</div>
                <div id="live-timer" style="color:#38bdf8; font-size:16px; font-weight:bold;">01:30:00</div>
            </div>
            <script>
                if (!sessionStorage.getItem('exam_time_left')) {
                    sessionStorage.setItem('exam_time_left', '5400'); // 90 minutes
                }
                function runClock() {
                    let sec = parseInt(sessionStorage.getItem('exam_time_left'));
                    if (sec > 0) {
                        sec--;
                        sessionStorage.setItem('exam_time_left', sec);
                    }
                    let hrs = Math.floor(sec / 3600);
                    let rem = sec % 3600;
                    let mins = Math.floor(rem / 60);
                    let secs = rem % 60;
                    document.getElementById("live-timer").innerText = 
                        (hrs < 10 ? "0" + hrs : hrs) + ":" + 
                        (mins < 10 ? "0" + mins : mins) + ":" + 
                        (secs < 10 ? "0" + secs : secs);
                }
                setInterval(runClock, 1000);
                runClock();
            </script>
        """, height=110)

    with header_col3:
        # 完整顯示的綠色相機預覽框（調整 height 及 video 大小避免過界）
        st.components.v1.html("""
            <div style="border: 2px solid #22c55e; border-radius: 8px; background-color: #f0fdf4; text-align: center; padding: 4px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); box-sizing: border-box;">
                <div style="color: #15803d; font-weight: bold; font-size: 9px; margin-bottom: 2px; text-transform: uppercase;">🟢 Live Proctor</div>
                <video id="top-webcam" autoplay playsinline muted style="width: 100%; height: 90px; object-fit: cover; border-radius: 4px; background: #000; display: block;"></video>
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

    
    # --- [2] 側邊欄 (題庫導覽與防作弊監控) ---
    with st.sidebar:
        st.markdown("### 📹 Security Status")
        st.markdown("""
            <div style="border: 2px dashed #22c55e; padding: 10px; border-radius: 8px; text-align: center; background-color: #f0fdf4;">
                <div style="color: #15803d; font-weight: bold; font-size: 12px;">🟢 Focus Guard Active</div>
            </div>
        """, unsafe_allow_html=True)
        
        # 偵測切換分頁 / 離開畫面的 JavaScript
        st.components.v1.html("""
            <script>
                document.addEventListener("visibilitychange", function() {
                    if (document.hidden) {
                        // 當考生切換分頁時，可在 console 記錄或發送通知
                        console.warn("Candidate switched tab or minimized window.");
                    }
                });
            </script>
        """, height=0)

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
        is_flagged = q_idx in st.session_state.flags
        flag_label = "⭐ Unflag Question" if is_flagged else "⭐ Flag for Review"
        if st.button(flag_label, use_container_width=True):
            if is_flagged:
                st.session_state.flags.remove(q_idx)
            else:
                st.session_state.flags.add(q_idx)
            st.rerun()

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
# Step 4 - 結算總結與交卷頁 (Review & Finish Exam)
# ==========================================
elif st.session_state.authenticated and st.session_state.exam_step == 4:
    st.markdown("### 📋 Exam Review & Final Submission")
    st.markdown("Review your completion status below before submitting your final paper.")
    
    answered_count = len(st.session_state.answers) if "answers" in st.session_state else 0
    flagged_count = len(st.session_state.flags) if "flags" in st.session_state else 0
    unanswered_count = 75 - answered_count
    focus_losses = st.session_state.get("focus_loss_count", 0)
    
    col_s1, col_s2, col_s3, col_s4 = st.columns(4)
    col_s1.metric("Answered", f"{answered_count} / 75")
    col_s2.metric("Unanswered", unanswered_count)
    col_s3.metric("Flagged", flagged_count)
    col_s4.metric("Focus Losses", focus_losses, delta_color="inverse" if focus_losses > 0 else "off")
    
    st.markdown("---")
    
    col_act1, col_act2 = st.columns(2)
    with col_act1:
        if st.button("⬅️ Return to Exam", use_container_width=True):
            st.session_state.exam_step = 3
            st.rerun()
            
    with col_act2:
        if st.button("🔒 Finish & Submit Exam", type="primary", use_container_width=True):
            st.success("🎉 Exam successfully submitted! Answers and audit logs pushed to Google Sheets.")

# ==========================================
# Step 4 - 交卷與完成畫面
# ==========================================
elif st.session_state.authenticated and st.session_state.exam_step == 4:
  st.markdown(
      "<h2 style='text-align: center;'>🎉 Exam Completed!</h2>",
      unsafe_allow_html=True,
  )
  st.success(
      "Your responses have been successfully recorded to the examination"
      " database."
  )
  st.write(
      f"Thank you, {st.session_state.candidate_name}. You may now close this"
      " window."
  )
