import streamlit as st
import os
import shutil
import tempfile
import zipfile
import time
from pathlib import Path
import extra_streamlit_components as stx
import sys

# --- CẤU HÌNH HỆ THỐNG ---
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
try:
    from appword.services.pipeline import run_pipeline
except ImportError as e:
    st.error(f"Lỗi: {e}"); st.stop()

st.set_page_config(page_title="Word to Moodle", page_icon="📝", layout="wide", initial_sidebar_state="expanded")

# --- CSS SIÊU GỌN ---
st.markdown("""
<style>
    /* Thu gọn lề trên cùng */
    .block-container { padding-top: 1rem; padding-bottom: 2rem; }
    /* Thu gọn Sidebar */
    [data-testid="stSidebar"] { padding-top: 1rem; }
    [data-testid="stSidebar"] .block-container { padding-top: 1rem; }
    /* Chỉnh nút bấm nhỏ lại */
    .stButton button { padding: 0.25rem 0.5rem; min-height: 0px; height: auto; }
    /* Tiêu đề nhỏ lại */
    h1 { font-size: 1.5rem !important; margin-bottom: 0px !important; }
    /* Ẩn bớt khoảng trắng của các widget */
    .stRadio { margin-top: -10px; margin-bottom: -10px; }
    .stTextInput { margin-bottom: -10px; }
</style>
""", unsafe_allow_html=True)

# --- AUTH & COOKIE ---
cookie_manager = stx.CookieManager()

def check_auth():
    try: allowed = st.secrets["general"]["allowed_emails"]
    except: allowed = []
    if "user_email" in st.session_state: return True
    time.sleep(0.1)
    saved = cookie_manager.get("user_email")
    if saved and (not allowed or saved in allowed):
        st.session_state["user_email"] = saved; return True
    return False

if not check_auth():
    st.title("🔐 Đăng nhập")
    c1, c2, c3 = st.columns([1,2,1])
    with c2:
        email = st.text_input("Email:", placeholder="admin@gmail.com")
        if st.button("Truy cập", use_container_width=True):
            allowed = st.secrets["general"].get("allowed_emails", [])
            if not allowed or email.strip() in allowed:
                st.session_state["user_email"] = email.strip()
                cookie_manager.set("user_email", email.strip(), key="ck_mail")
                st.rerun()
            else: st.error("Không có quyền.")
    st.stop()

# ================= SIDEBAR (SIÊU GỌN) =================
with st.sidebar:
    # Header: User + Logout (Dùng 2 cột để gọn)
    c_user, c_out = st.columns([4, 1])
    c_user.caption(f"👤 {st.session_state['user_email']}")
    if c_out.button("🚪", help="Đăng xuất"):
        cookie_manager.delete("user_email"); st.session_state.clear(); st.rerun()
    
    st.divider()
    
    # 1. API Key (Gộp Input và Button trên 1 dòng ảo)
    st.markdown("**🔑 API Key ImgBB**")
    cur_key = cookie_manager.get("my_imgbb_key", "")
    api_key = st.text_input("Key", value=cur_key, type="password", label_visibility="collapsed", placeholder="Nhập API Key...")
    
    # Nút Lưu/Xóa nằm ngang
    b1, b2 = st.columns(2)
    if b1.button("💾 Lưu", use_container_width=True):
        cookie_manager.set("my_imgbb_key", api_key, key="save_k"); st.toast("Đã lưu!")
    if b2.button("🗑️ Xóa", use_container_width=True):
        cookie_manager.delete("my_imgbb_key"); st.rerun()

    st.divider()

    # 2. Mapping ID
    st.markdown("**📂 File ID Mapping**")
    repo_path = os.path.join(os.getcwd(), "ID")
    defaults = [f for f in os.listdir(repo_path) if f.endswith(".xlsx")] if os.path.exists(repo_path) else []
    
    # Radio nằm ngang
    map_mode = st.radio("Nguồn", ["Mặc định", "Upload"], horizontal=True, label_visibility="collapsed")
    
    final_map = None
    if map_mode == "Mặc định":
        if defaults:
            sel = st.selectbox("Chọn file", defaults, label_visibility="collapsed")
            final_map = os.path.join(repo_path, sel)
        else: st.warning("Không có file mặc định.")
    else:
        up = st.file_uploader("Excel", type=['xlsx'], label_visibility="collapsed")
        if up: final_map = up

# ================= MAIN SCREEN =================
st.title("📝 Chuyển đổi Word ➡️ Moodle")

# Upload (Container to rõ)
with st.container():
    uploaded_files = st.file_uploader("Kéo thả file .docx vào đây", type=['docx'], accept_multiple_files=True)

if uploaded_files:
    # Nút bấm to màu xanh
    if st.button(f"🚀 XỬ LÝ {len(uploaded_files)} FILE NGAY", type="primary", use_container_width=True):
        
        # Check config
        run_key = api_key if api_key else st.secrets["general"].get("default_imgbb_key")
        if not final_map: st.warning("⚠️ Chọn ID Mapping bên trái trước!"); st.stop()
        
        # Process
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            i_dir, o_dir, m_dir = base/"in", base/"out", base/"map"
            f
