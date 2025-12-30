import streamlit as st
import os
import shutil
import tempfile
import zipfile
import time
from pathlib import Path
import extra_streamlit_components as stx

# --- CẤU HÌNH ĐƯỜNG DẪN ĐỂ IMPORT MODULE ---
import sys
# Thêm thư mục hiện tại vào path để tìm thấy 'appword'
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import logic xử lý chính
try:
    from appword.services.pipeline import run_pipeline
except ImportError as e:
    st.error(f"Lỗi Import: Không tìm thấy module 'appword'. Hãy đảm bảo cấu trúc thư mục đúng.\nChi tiết: {e}")
    st.stop()

# --- CẤU HÌNH TRANG WEB ---
st.set_page_config(
    page_title="Word to Moodle XML",
    page_icon="📝",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CSS TÙY CHỈNH CHO ĐẸP ---
st.markdown("""
<style>
    .main {background-color: #f8f9fa;}
    div.stButton > button:first-child {
        background-color: #0068c9; color: white; border-radius: 8px; font-weight: bold;
    }
    div.stButton > button:first-child:hover {
        background-color: #0053a0; border-color: #0053a0;
    }
    .stSuccess {background-color: #d4edda; color: #155724;}
</style>
""", unsafe_allow_html=True)

# --- KHỞI TẠO COOKIE MANAGER (ĐÃ SỬA LỖI CACHE) ---
# Lưu ý: Không dùng @st.cache_resource ở đây để tránh lỗi CachedWidgetWarning
cookie_manager = stx.CookieManager()

# --- HÀM KIỂM TRA ĐĂNG NHẬP (EMAIL) ---
def check_authentication():
    # 1. Lấy danh sách email từ Secrets
    try:
        allowed_emails = st.secrets["general"]["allowed_emails"]
    except Exception:
        st.warning("⚠️ Chưa cấu hình 'allowed_emails' trong Secrets. Đang dùng chế độ mở (Demo).")
        # Chế độ demo cho phép mọi email (hoặc bạn có thể return False để chặn)
        allowed_emails = [] 

    # 2. Kiểm tra Session (Phiên làm việc hiện tại)
    if "user_email" in st.session_state:
        return True

    # 3. Kiểm tra Cookie (Phiên làm việc cũ đã lưu)
    # Cần chờ cookie load xong
    time.sleep(0.1) 
    saved_email = cookie_manager.get("user_email")
    
    if saved_email:
        # Nếu danh sách rỗng (chưa cấu hình) hoặc email nằm trong danh sách cho phép
        if not allowed_emails or saved_email in allowed_emails:
            st.session_state["user_email"] = saved_email
            return True
    
    return False

def login_screen():
    st.title("🔐 Đăng nhập hệ thống")
    st.markdown("---")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.info("Vui lòng nhập Email đã được cấp quyền để truy cập.")
        email_input = st.text_input("Email của bạn:", placeholder="example@school.edu.vn")
        
        if st.button("Đăng nhập", use_container_width=True):
            try:
                allowed_emails = st.secrets["general"]["allowed_emails"]
                # Chuẩn hóa email
                email_check = email_input.strip()
                
                if email_check in allowed_emails:
                    st.session_state["user_email"] = email_check
                    # Lưu cookie 30 ngày
                    cookie_manager.set("user_email", email_check, key="set_email_cookie")
                    st.success("Đăng nhập thành công! Đang chuyển hướng...")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("🚫 Email này chưa được cấp quyền truy cập.")
            except:
                # Fallback nếu chưa cấu hình secrets (Cho phép vào luôn để test)
                st.session_state["user_email"] = email_input
                st.rerun()

# --- LOGIC CHÍNH: NẾU CHƯA LOGIN THÌ HIỆN FORM ---
if not check_authentication():
    login_screen()
    st.stop()

# ================= GIAO DIỆN CHÍNH (SAU KHI ĐĂNG NHẬP) =================

user_email = st.session_state.get("user_email", "User")

# --- SIDEBAR ---
with st.sidebar:
    st.title("Word ➡️ Moodle")
    st.write(f"Xin chào, **{user_email}** 👋")
    
    if st.button("Đăng xuất"):
        cookie_manager.delete("user_email")
        st.session_state.clear()
        st.rerun()
        
    st.divider()
    st.markdown("### Hướng dẫn nhanh")
    st.markdown("""
    1. Nhập **API Key ImgBB** (Lưu lại để dùng lần sau).
    2. Chọn **File Mapping ID** (Upload hoặc dùng mặc định).
    3. Upload file **Word (.docx)**.
    4. Bấm **Bắt đầu xử lý**.
    """)
    st.info("Phiên bản Web v1.2")

st.title("📝 Hệ thống chuyển đổi đề trắc nghiệm")
st.caption("Tự động tách câu hỏi, upload ảnh lên Cloud và xuất file XML chuẩn Moodle.")
st.divider()

col_config, col_process = st.columns([1, 1.5], gap="large")

with col_config:
    st.subheader("1. Cấu hình")
    
    # --- A. XỬ LÝ API KEY ---
    # Lấy key từ cookie
    cookie_api_key = cookie_manager.get("my_imgbb_key")
    default_key_val = cookie_api_key if cookie_api_key else ""

    api_key_input = st.text_input(
        "ImgBB API Key", 
        value=default_key_val, 
        type="password",
        help="Lấy key tại: https://api.imgbb.com/"
    )

    c1, c2 = st.columns(2)
    with c1:
        if st.button("💾 Lưu Key"):
            if api_key_input:
                cookie_manager.set("my_imgbb_key", api_key_input, key="set_api_cookie")
                st.toast("Đã lưu API Key!", icon="✅")
                time.sleep(1) # Đợi cookie ghi
            else:
                st.warning("Hãy nhập Key trước.")
    with c2:
        if st.button("🗑️ Xóa Key"):
            cookie_manager.delete("my_imgbb_key")
            st.toast("Đã xóa API Key.", icon="🗑️")
            # Clear input visual
            st.rerun()

    st.markdown("---")

    # --- B. XỬ LÝ FILE ID MAPPING ---
    st.subheader("File ID Mapping (.xlsx)")
    
    # Tìm file mặc định trong thư mục 'ID' của repo
    repo_default_path = os.path.join(os.getcwd(), "ID")
    default_files = []
    if os.path.exists(repo_default_path):
        default_files = [f for f in os.listdir(repo_default_path) if f.endswith(".xlsx") and not f.startswith("~$")]
    
    has_default = len(default_files) > 0
    
    mapping_mode = st.radio(
        "Nguồn dữ liệu ID:",
        options=["Upload file mới", "Dùng file hệ thống (Mặc định)"] if has_default else ["Upload file mới"],
        horizontal=True
    )
    
    final_mapping_source = None # Biến lưu đường dẫn hoặc file upload
    
    if mapping_mode == "Upload file mới":
        uploaded_mapping = st.file_uploader("Upload file Excel ID", type=['xlsx'])
        if uploaded_mapping:
            final_mapping_source = uploaded_mapping
            
    elif mapping_mode == "Dùng file hệ thống (Mặc định)":
        selected_default = st.selectbox("Chọn file có sẵn:", default_files)
        if selected_default:
            final_mapping_source = os.path.join(repo_default_path, selected_default)
            st.success(f"Đang dùng: {selected_default}")

with col_process:
    st.subheader("2. Upload & Xử lý")
    
    uploaded_word_files = st.file_uploader(
        "Chọn file đề Word (.docx)", 
        type=['docx'], 
        accept_multiple_files=True,
        help="Bạn có thể chọn nhiều file cùng lúc."
    )

    if uploaded_word_files:
        st.write(f"📂 Đã chọn: **{len(uploaded_word_files)}** file.")
        
        # Nút Chạy
        if st.button("🚀 BẮT ĐẦU XỬ LÝ", type="primary", use_container_width=True):
            
            # --- KIỂM TRA ĐẦU VÀO ---
            # 1. API Key
            # Ưu tiên input > cookie > secrets default
            run_api_key = api_key_input
            if not run_api_key:
                try: run_api_key = st.secrets["general"]["default_imgbb_key"]
                except: pass
            
            # 2. File Mapping
            if not final_mapping_source:
                st.warning("⚠️ Cảnh báo: Chưa có file ID Mapping. ID câu hỏi có thể bị lỗi.")

            # --- TẠO MÔI TRƯỜNG TẠM THỜI ---
            with tempfile.TemporaryDirectory() as temp_dir:
                base_path = Path(temp_dir)
                input_dir = base_path / "input"
                output_dir = base_path / "output"
                mapping_dir = base_path / "mapping"
                
                input_dir.mkdir()
                output_dir.mkdir()
                mapping_dir.mkdir()

                # --- LƯU FILE VÀO MÔI TRƯỜNG TẠM ---
                status_box = st.status("Đang xử lý...", expanded=True)
                
                # 1. Prepare Mapping
                real_mapping_path_arg = None
                if final_mapping_source:
                    if isinstance(final_mapping_source, str): 
                        # Là đường dẫn file có sẵn trên server -> Copy vào temp
                        shutil.copy(final_mapping_source, mapping_dir / os.path.basename(final_mapping_source))
                    else:
                        # Là file upload -> Save bytes
                        with open(mapping_dir / final_mapping_source.name, "wb") as f:
                            f.write(final_mapping_source.getbuffer())
                    real_mapping_path_arg = str(mapping_dir)
                    status_box.write("✅ Đã nạp file ID Mapping.")

                # 2. Prepare Input Docs
                for uf in uploaded_word_files:
                    with open(input_dir / uf.name, "wb") as f:
                        f.write(uf.getbuffer())
                status_box.write(f"✅ Đã tải lên {len(uploaded_word_files)} file Word.")

                # 3. RUN PIPELINE
                progress_bar = status_box.progress(0)
                
                def update_progress_ui(curr, total, msg):
                    pct = int((curr / total) * 100)
                    progress_bar.progress(min(pct, 100))
                    # st.write(f"Log: {msg}") # Uncomment để debug

                try:
                    status_box.write("⚙️ Đang chạy pipeline (Tách ảnh, Upload, Tạo XML)...")
                    
                    run_pipeline(
                        input_folder=str(input_dir),
                        output_folder=str(output_dir),
                        api_key=run_api_key,
                        progress_cb=update_progress_ui,
                        mapping_dir=real_mapping_path_arg
                    )
                    
                    status_box.update(label="✅ Xử lý hoàn tất!", state="complete", expanded=False)
                    st.success("Đã chuyển đổi thành công!")

                    # 4. ZIP RESULT
                    zip_filename = "ket_qua_moodle.zip"
                    zip_path = base_path / zip_filename
                    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                        for root, dirs, files in os.walk(output_dir):
                            for file in files:
                                p = os.path.join(root, file)
                                arcname = os.path.relpath(p, output_dir)
                                zipf.write(p, arcname)

                    # 5. DOWNLOAD BUTTON
                    with open(zip_path, "rb") as f:
                        st.download_button(
                            label="📥 TẢI XUỐNG KẾT QUẢ (.ZIP)",
                            data=f,
                            file_name=zip_filename,
                            mime="application/zip",
                            type="primary",
                            use_container_width=True
                        )
                    
                    # 6. HIỂN THỊ KẾT QUẢ SƠ BỘ
                    st.markdown("### 📄 Danh sách file kết quả:")
                    result_files = []
                    for root, dirs, files in os.walk(output_dir):
                        for file in files:
                            result_files.append(file)
                    st.json(result_files)

                except Exception as e:
                    status_box.update(label="❌ Có lỗi xảy ra!", state="error")
                    st.error(f"Chi tiết lỗi: {str(e)}")
                    # st.exception(e) # Hiện traceback đầy đủ nếu cần debug
