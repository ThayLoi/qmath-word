import streamlit as st
import os
import shutil
import tempfile
import zipfile
import time
from pathlib import Path
import extra_streamlit_components as stx # Thư viện xử lý Cookie

# Import logic cũ
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from appword.services.pipeline import run_pipeline

# --- CẤU HÌNH TRANG WEB ---
st.set_page_config(page_title="Word to Moodle XML", page_icon="📝", layout="wide")

# --- CSS TÙY CHỈNH ---
st.markdown("""
<style>
    .main {background-color: #f8f9fa;}
    .block-container {padding-top: 2rem;}
    div.stButton > button:first-child {
        background-color: #0068c9; color: white; border-radius: 8px;
    }
    .success-box {padding: 1rem; background-color: #d4edda; border-radius: 8px; color: #155724;}
</style>
""", unsafe_allow_html=True)

# --- KHỞI TẠO COOKIE MANAGER ---
# Cái này giúp lưu API Key vào trình duyệt người dùng
@st.cache_resource
def get_manager():
    return stx.CookieManager()

cookie_manager = get_manager()

# --- HÀM KIỂM TRA ĐĂNG NHẬP (EMAIL) ---
def check_authentication():
    # Lấy danh sách email từ Secrets
    try:
        allowed_emails = st.secrets["general"]["allowed_emails"]
    except:
        allowed_emails = [] # Nếu chưa cấu hình thì rỗng

    # Kiểm tra xem đã đăng nhập chưa (trong Session hoặc Cookie)
    if "user_email" not in st.session_state:
        # Thử lấy từ cookie xem lần trước có đăng nhập không
        cookie_email = cookie_manager.get("user_email")
        if cookie_email and cookie_email in allowed_emails:
            st.session_state["user_email"] = cookie_email
            return True
        return False
    return True

def login_screen():
    st.title("🔐 Đăng nhập hệ thống")
    st.write("Vui lòng nhập Email đã được cấp quyền để sử dụng.")
    
    email_input = st.text_input("Email của bạn:")
    
    if st.button("Đăng nhập"):
        try:
            allowed_emails = st.secrets["general"]["allowed_emails"]
        except:
            st.error("Lỗi cấu hình Server (Thiếu Secrets). Liên hệ Admin.")
            return

        if email_input.strip() in allowed_emails:
            # Đăng nhập thành công
            st.session_state["user_email"] = email_input
            # Lưu vào cookie để lần sau tự vào (Hạn 30 ngày)
            cookie_manager.set("user_email", email_input, key="set_email", expires_at=None)
            st.success("Đăng nhập thành công! Đang chuyển hướng...")
            time.sleep(1)
            st.rerun()
        else:
            st.error("🚫 Email này chưa được kích hoạt hoặc không có quyền truy cập.")

# --- NẾU CHƯA ĐĂNG NHẬP THÌ HIỆN FORM ---
if not check_authentication():
    login_screen()
    st.stop()

# ================= GIAO DIỆN CHÍNH (SAU KHI LOGIN) =================

# Lấy email đang dùng
current_user = st.session_state["user_email"]

# Sidebar: Thông tin người dùng & Đăng xuất
with st.sidebar:
    st.write(f"Xin chào, **{current_user}** 👋")
    if st.button("Đăng xuất"):
        # Xóa cookie và session
        cookie_manager.delete("user_email")
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()
    st.markdown("---")
    st.info("Hệ thống chuyển đổi Word sang Moodle XML tự động tách ảnh và upload.")

st.title("📝 Chuyển đổi Word sang Moodle XML")
st.markdown("---")

col1, col2 = st.columns([1, 2])

with col1:
    st.header("1. Cấu hình")
    
    # --- XỬ LÝ API KEY (LƯU/ĐỌC COOKIE) ---
    # Thử lấy key từ cookie trước
    saved_api_key = cookie_manager.get("my_imgbb_key")
    if saved_api_key is None: saved_api_key = ""

    api_key_input = st.text_input(
        "ImgBB API Key", 
        value=saved_api_key, 
        type="password", 
        help="Nhập key xong bấm Lưu để lần sau không phải nhập lại."
    )

    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("💾 Lưu Key"):
            if api_key_input:
                cookie_manager.set("my_imgbb_key", api_key_input, key="save_key")
                st.toast("Đã lưu API Key vào trình duyệt!", icon="✅")
                time.sleep(0.5)
            else:
                st.warning("Chưa nhập Key.")

    with col_btn2:
        if st.button("🗑️ Xóa Key"):
            cookie_manager.delete("my_imgbb_key")
            st.toast("Đã xóa API Key.", icon="🗑️")
            time.sleep(1)
            st.rerun()

    st.markdown("---")
    
    # --- XỬ LÝ FILE ID MAPPING ---
    st.subheader("File ID Mapping")
    
    # Kiểm tra xem Admin có để file mặc định trong GitHub không
    default_mapping_path = "ID/ID10.xlsx" # Giả sử bạn để file mặc định ở đây trong repo
    has_default = os.path.exists(default_mapping_path)
    
    mapping_option = st.radio(
        "Chọn nguồn ID:",
        options=["Upload file mới", "Dùng file mặc định của hệ thống"] if has_default else ["Upload file mới"]
    )
    
    uploaded_mapping = None
    if mapping_option == "Upload file mới":
        uploaded_mapping = st.file_uploader("Chọn file .xlsx", type=['xlsx'], key="map_up")
    elif mapping_option == "Dùng file mặc định của hệ thống":
        st.caption(f"Đang dùng file: `{default_mapping_path}` trên server.")

with col2:
    st.header("2. Upload & Xử lý")
    uploaded_files = st.file_uploader("Chọn file Word (.docx)", type=['docx'], accept_multiple_files=True)

    if uploaded_files:
        if st.button(f"🚀 BẮT ĐẦU XỬ LÝ ({len(uploaded_files)} file)", type="primary"):
            
            # --- TẠO MÔI TRƯỜNG TẠM ---
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                input_dir = temp_path / "input"
                output_dir = temp_path / "output"
                mapping_dir = temp_path / "mapping"
                
                input_dir.mkdir()
                output_dir.mkdir()
                mapping_dir.mkdir()

                # 1. Xử lý file Mapping
                final_mapping_path = None
                
                if mapping_option == "Upload file mới" and uploaded_mapping:
                    # User upload file riêng
                    with open(mapping_dir / uploaded_mapping.name, "wb") as f:
                        f.write(uploaded_mapping.getbuffer())
                    final_mapping_path = mapping_dir
                    
                elif mapping_option == "Dùng file mặc định của hệ thống" and has_default:
                    # Copy file mặc định từ source code vào thư mục tạm
                    shutil.copy(default_mapping_path, mapping_dir / "default.xlsx")
                    final_mapping_path = mapping_dir
                
                # Nếu không có mapping nào
                if not final_mapping_path:
                    st.warning("⚠️ Cảnh báo: Chưa có file ID Mapping. Các câu hỏi có thể không được gán ID đúng.")

                # 2. Lưu file Word
                status_text = st.empty()
                status_text.text("Đang chuẩn bị file...")
                
                for uploaded_file in uploaded_files:
                    with open(input_dir / uploaded_file.name, "wb") as f:
                        f.write(uploaded_file.getbuffer())

                # 3. CHẠY PIPELINE
                progress_bar = st.progress(0)

                def update_progress(current, total, msg):
                    percent = int((current / total) * 100)
                    progress_bar.progress(min(percent, 100))
                    status_text.text(f"Đang xử lý: {msg}")

                try:
                    # Xác định API Key: Ưu tiên ô nhập, nếu không thì lấy key mặc định trong Secrets
                    final_api_key = api_key_input if api_key_input else st.secrets["general"].get("default_imgbb_key")

                    run_pipeline(
                        input_folder=str(input_dir),
                        output_folder=str(output_dir),
                        api_key=final_api_key,
                        progress_cb=update_progress,
                        mapping_dir=str(final_mapping_path) if final_mapping_path else None
                    )

                    st.balloons()
                    st.success("✅ Xử lý hoàn tất!")
                    status_text.text("Hoàn tất!")

                    # 4. Nén ZIP
                    zip_path = temp_path / "ket_qua_moodle.zip"
                    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                        for root, dirs, files in os.walk(output_dir):
                            for file in files:
                                file_path = os.path.join(root, file)
                                arcname = os.path.relpath(file_path, output_dir)
                                zipf.write(file_path, arcname)

                    # 5. Download
                    with open(zip_path, "rb") as f:
                        st.download_button(
                            label="📥 TẢI XUỐNG KẾT QUẢ (.ZIP)",
                            data=f,
                            file_name="ket_qua_moodle.zip",
                            mime="application/zip",
                            type="primary"
                        )
                    
                    # Thống kê
                    with st.expander("Xem chi tiết file kết quả"):
                        st.json(os.listdir(output_dir))

                except Exception as e:
                    st.error(f"Có lỗi xảy ra: {str(e)}")
