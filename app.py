import streamlit as st
import time

# 頁面基本設定 (必須為第一個 Streamlit 指令)
st.set_page_config(
    page_title="Professional Certification Exam Engine",
    page_icon="📝",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 初始化 Session State (模擬狀態管理)
if "current_q" not in st.session_state:
    st.session_state.current_q = 1
if "answers" not in st.session_state:
    st.session_state.answers = {}  # 格式: {q_num: selected_option}
if "flags" not in st.session_state:
    st.session_state.flags = set()  # 儲存被標記的題目編號
if "submitted" not in st.session_state:
    st.session_state.submitted = False

TOTAL_QUESTIONS = 75

# --- [1] 頂部標頭區 (Top Header Area) ---
header_col1, header_col2 = st.десь([3, 1]) if 'десь' not in globals() else st.columns([3, 1])
# 修正 Streamlit 寫法
header_col1, header_col2 = st.columns([3, 1])

with header_col1:
    st.markdown("### 👤 Candidate: **John Doe** | ID: **EX-2026-0921**")

with header_col2:
    # 黏性/動態倒數計時器 (此處用簡單的 HTML/JS 或 Streamlit 顯示示範)
    # 90分鐘 = 5400 秒
    st.markdown("""
        <div style="background-color:#1e293b; color:#f8fafc; padding:8px 12px; border-radius:6px; text-align:center; font-weight:bold;">
            ⏳ Time Remaining: <span id="timer" style="color:#38bdf8;">89:45</span>
        </div>
    """, unsafe_allow_html=True)

st.divider()

# --- [2] 側邊欄 (Sidebar: Webcam & Question Palette) ---
with st.sidebar:
    st.markdown("### 📹 Proctoring Monitor")
    # 模擬 Live Webcam 預覽框與狀態指示器
    st.markdown("""
        <div style="border: 2px dashed #22c55e; padding: 10px; border-radius: 8px; text-align: center; background-color: #f0fdf4;">
            <div style="color: #15803d; font-weight: bold; font-size: 14px; margin-bottom: 5px;">🟢 Status: Secure & Active</div>
            <div style="background-color: #000; color: #fff; height: 120px; display: flex; align-items: center; justify-content: center; border-radius: 4px; font-size: 12px;">
                [ Live Webcam Feed ]
            </div>
        </div>
    """, unsafe_allow_html=True)
    
    st.markdown("---")
    st.markdown("### 🗺️ Question Palette (1–75)")
    st.markdown("<small>🟢 Answered | ⚪ Unanswered | ⭐ Flagged</small>", unsafe_allow_html=True)
    
    # 建立 1-75 題的網格導航 (以每行 5 粒按鈕排列)
    cols_per_row = 5
    for i in range(1, TOTAL_QUESTIONS + 1, cols_per_row):
        cols = st.columns(cols_per_row)
        for j in range(cols_per_row):
            q_num = i + j
            if q_num <= TOTAL_QUESTIONS:
                # 決定按鈕顏色/標籤樣式
                label = f"{q_num}"
                if q_num in st.session_state.flags:
                    label = f"⭐{q_num}"
                
                # 檢查是否已作答
                is_answered = q_num in st.session_state.answers
                
                # 用不同顏色按鈕或標準按鈕代表狀態
                if cols[j].button(label, key=f"pal_{q_num}", use_container_width=True):
                    st.session_state.current_q = q_num
                    st.rerun()

# --- [3] 主畫面區域 (Main Content Area) ---
q_idx = st.session_state.current_q

# 題目類型與編號指示
st.markdown(f"#### Question {q_idx} of {TOTAL_QUESTIONS} — Multiple Choice")
st.progress(q_idx / TOTAL_QUESTIONS)

# 模擬題目內容（實際接 Google Sheet 時會從 dataframe 動態讀取）
st.markdown(f"""
> **Scenario / Question Text for Q{q_idx}:**  
> According to the Shisa Kanko (Pointing and Calling) safety protocols, what is the primary physiological and cognitive benefit of executing a physical point paired with a verbal command during a critical operational check?
""")

# 選項互動 (模擬)
options = [
    "A. It reduces muscular fatigue during long shifts.",
    "B. It enhances consciousness and reduces operational errors by synchronizing brain and sensory alertness.",
    "C. It replaces the need for standard digital logging.",
    "D. It is purely ceremonial and has no measurable safety impact."
]

current_answer = st.session_state.answers.get(q_idx, None)
selected = st.radio("Select your answer:", options, index=options.index(current_answer) if current_answer in options else None, key=f"q_radio_{q_idx}")

# 更新作答記錄
if selected:
    st.session_state.answers[q_idx] = selected

st.markdown("<br>", unsafe_allow_html=True)

# 操作按鈕列：⭐ Flag, Previous, Next
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

# --- [4] 底部導航欄 (Bottom Bar) ---
bottom_col1, bottom_col2, bottom_col3 = st.columns([2, 3, 2])
with bottom_col2:
    if st.button("📋 Review & Finish Exam", type="primary", use_container_width=True):
        st.success("Redirecting to Final Summary Checklist...")
        # 這裡之後可以切換頁面狀態至結算清單