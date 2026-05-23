import io
import requests
import streamlit as st
from PIL import Image
from pathlib import Path
import shutil

# ── Backend URL ───────────────────────────────────────────────────────────────
API = "http://localhost:8000"

st.set_page_config(
    page_title="Teachable Machine",
    page_icon="🤖",
    layout="wide",
)

# ── Custom Premium Styling ───────────────────────────────────────────────────
st.markdown(
    """
    <style>
    /* Import modern typography */
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap');
    
    /* Apply globally */
    html, body, [class*="css"], .stApp {
        font-family: 'Outfit', sans-serif !important;
    }
    
    /* Sleek gradient headers */
    h1, h2, h3, h4 {
        font-family: 'Outfit', sans-serif !important;
        font-weight: 700 !important;
        letter-spacing: -0.5px !important;
    }
    
    /* Glassmorphism style cards */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 16px !important;
        border: 1px solid rgba(128, 128, 128, 0.18) !important;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.04) !important;
        padding: 24px !important;
        margin-bottom: 20px !important;
        transition: all 0.25s ease-in-out;
        background-color: rgba(255, 255, 255, 0.02) !important;
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:hover {
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.08) !important;
        border-color: rgba(66, 153, 225, 0.4) !important;
    }
    
    /* Stylized buttons with smooth feedback */
    .stButton > button {
        border-radius: 10px !important;
        font-weight: 600 !important;
        padding: 8px 16px !important;
        transition: all 0.2s ease-in-out !important;
    }
    .stButton > button:hover {
        transform: translateY(-1px) !important;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05) !important;
    }
    
    /* Prediction highlight */
    .winning-bar-text {
        font-weight: 700 !important;
        color: #3B82F6 !important;
    }
    
    /* Add a class button styling */
    .add-class-btn {
        margin-top: 15px;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# ── Session State Bootstrap ───────────────────────────────────────────────────
defaults = {
    "trained":          False,
    "classes":          [],
    "counts":           {},
    "train_result":     None,
    "local_classes":    [],
    "last_test_hash":   None,
    "last_prediction":  None,
    "burst_counts":     {},      # tracks burst capture progress per class index
    "burst_frames":     {},      # tracks captured frame hashes to avoid duplicates
}
for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value

# Helper functions for filesystem operations
def rename_backend_class_folder(old_name: str, new_name: str):
    """Rename the backend folder for a class if it exists on disk."""
    dataset_path = Path(__file__).parent.parent / "backend" / "dataset"
    old_folder = dataset_path / old_name
    new_folder = dataset_path / new_name
    try:
        if old_folder.exists() and old_folder.is_dir():
            if not new_folder.exists():
                old_folder.rename(new_folder)
    except Exception as e:
        st.error(f"Error renaming folder: {e}")

def delete_backend_class_folder(class_name: str):
    """Delete the backend folder for a class if it exists on disk."""
    dataset_path = Path(__file__).parent.parent / "backend" / "dataset"
    folder = dataset_path / class_name
    try:
        if folder.exists() and folder.is_dir():
            shutil.rmtree(folder)
    except Exception as e:
        st.error(f"Error deleting folder: {e}")

# ── HTTP API Helper ────────────────────────────────────────────────────────────
def call_api(method: str, path: str, **kwargs) -> tuple:
    """Generic HTTP helper. Returns (response_dict, status_code)."""
    # Simple retry loop to handle transient multipart upload issues
    last_exc = None
    last_response = None
    for attempt in range(2):
        try:
            # Ensure kwargs is fresh per-attempt (requests may consume file-like objects)
            r = requests.request(method, f"{API}{path}", **kwargs)
            last_response = r
            break
        except requests.exceptions.ConnectionError:
            st.error(
                "Cannot connect to backend. "
                "Make sure you ran: cd backend && uvicorn app.main:app --reload"
            )
            return None, 0
        except Exception as e:
            last_exc = e
            # retry once on unexpected errors (e.g., multipart encoding hiccup)
            if attempt == 0:
                continue
            st.error(f"Unexpected error: {e}")
            return None, 0

    if last_response is None:
        if last_exc:
            st.error(f"Unexpected error: {last_exc}")
        return None, 0

    try:
        payload = last_response.json()
    except ValueError:
        payload = {"detail": last_response.text or f"HTTP {last_response.status_code}"}

    return payload, last_response.status_code

def refresh_classes():
    """Pull current class names and counts from the backend and merge with local state."""
    data, status = call_api("GET", "/classes", timeout=5)
    if data and status == 200:
        st.session_state.classes = data["classes"]
        st.session_state.counts  = data["counts"]
        
        # Smart merge: sync local list with backend data
        for cls in data["classes"]:
            if cls not in st.session_state.local_classes:
                # Try to replace empty default classes ("Class X") first, or append
                replaced = False
                for idx, l_cls in enumerate(st.session_state.local_classes):
                    if l_cls.startswith("Class ") and st.session_state.counts.get(l_cls, 0) == 0:
                        st.session_state.local_classes[idx] = cls
                        replaced = True
                        break
                if not replaced:
                    st.session_state.local_classes.append(cls)

# Sync local_classes with backend classes initially
if not st.session_state.local_classes:
    refresh_classes()
    if st.session_state.classes:
        st.session_state.local_classes = list(st.session_state.classes)
    else:
        st.session_state.local_classes = ["Class 1", "Class 2"]
    
    # Ensure at least 2 classes exist initially
    while len(st.session_state.local_classes) < 2:
        next_num = len(st.session_state.local_classes) + 1
        new_default = f"Class {next_num}"
        while new_default in st.session_state.local_classes:
            next_num += 1
            new_default = f"Class {next_num}"
        st.session_state.local_classes.append(new_default)


# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.header("⚡ System Control")
    
    # Connection Indicator
    data, status = call_api("GET", "/", timeout=3)
    if status == 200:
        st.markdown(
            '<div style="background-color:rgba(16, 185, 129, 0.15); border: 1px solid rgb(16, 185, 129); '
            'padding: 10px; border-radius: 8px; color: rgb(16, 185, 129); font-weight: 600; text-align: center;">'
            '● Backend Connected</div>', 
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            '<div style="background-color:rgba(239, 68, 68, 0.15); border: 1px solid rgb(239, 68, 68); '
            'padding: 10px; border-radius: 8px; color: rgb(239, 68, 68); font-weight: 600; text-align: center;">'
            '● Backend Offline</div>', 
            unsafe_allow_html=True
        )
        st.code("cd backend\nuvicorn app.main:app --reload", language="bash")
        
    st.divider()
    
    # Global Reset
    if st.button("Reset Everything", type="secondary", use_container_width=True):
        data, status = call_api("DELETE", "/reset", timeout=10)
        if status == 200:
            st.session_state.trained          = False
            st.session_state.classes          = []
            st.session_state.counts           = {}
            st.session_state.train_result     = None
            st.session_state.local_classes    = ["Class 1", "Class 2"]
            st.session_state.last_test_hash   = None
            st.session_state.last_prediction  = None
            st.session_state.burst_counts     = {}
            st.session_state.burst_frames     = {}
            st.success("Wiped all datasets & models!")
            st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# MAIN APP - 3 COLUMN LAYOUT
# ══════════════════════════════════════════════════════════════════════════════
st.title("🤖 Teachable Machine")
st.caption("Train a custom image classifier in your browser — instant, beautiful, and no coding required.")
st.divider()

col_classes, col_training, col_preview = st.columns([1.8, 1.0, 1.2])


# ══════════════════════════════════════════════════════════════════════════════
# COLUMN 1: CLASSES DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
with col_classes:
    st.subheader("📁 Custom Classes")
    st.caption("Define your classes and upload or capture training images.")
    
    for idx, cls_name in enumerate(list(st.session_state.local_classes)):
        with st.container(border=True):
            # 1. Edit Name & Delete button header
            c_name, c_del = st.columns([5, 1])
            with c_name:
                new_name = st.text_input(
                    "Class Name",
                    value=cls_name,
                    key=f"name_input_{idx}",
                    label_visibility="collapsed",
                    placeholder="Class name (e.g. Cat)"
                )
                if new_name.strip() and new_name.strip() != cls_name:
                    cleaned_name = new_name.strip()
                    if cleaned_name not in st.session_state.local_classes:
                        # Rename folder on disk
                        rename_backend_class_folder(cls_name, cleaned_name)
                        st.session_state.local_classes[idx] = cleaned_name
                        if cls_name in st.session_state.counts:
                            st.session_state.counts[cleaned_name] = st.session_state.counts.pop(cls_name)
                        st.rerun()
                    elif cleaned_name != cls_name:
                        st.error("Class name already exists!")
                        
            with c_del:
                if st.button("🗑️", key=f"del_class_{idx}", help="Delete this class", use_container_width=True):
                    # Delete folder on disk
                    delete_backend_class_folder(cls_name)
                    st.session_state.local_classes.pop(idx)
                    st.session_state.counts.pop(cls_name, None)
                    st.rerun()
            
            # 2. Display sample counts
            cnt = st.session_state.counts.get(cls_name, 0)
            if cnt >= 5:
                st.markdown(f'<span style="color:#10B981; font-weight:600;">🟢 {cnt} Image Samples</span>', unsafe_allow_html=True)
            else:
                st.markdown(f'<span style="color:#F59E0B; font-weight:600;">⚠️ {cnt} Image Samples</span> <span style="font-size:12px; opacity:0.7;">(Need ≥ 5)</span>', unsafe_allow_html=True)
            
            # 3. Webcam / Upload controls inside class card
            mode_key = f"input_mode_{idx}"
            if mode_key not in st.session_state:
                st.session_state[mode_key] = "Upload"
                
            c_btn_up, c_btn_web = st.columns(2)
            with c_btn_up:
                if st.button("📁 Upload", key=f"mode_up_btn_{idx}", use_container_width=True,
                             type="primary" if st.session_state[mode_key] == "Upload" else "secondary"):
                    st.session_state[mode_key] = "Upload"
                    st.rerun()
            with c_btn_web:
                if st.button("📷 Webcam", key=f"mode_web_btn_{idx}", use_container_width=True,
                             type="primary" if st.session_state[mode_key] == "Webcam" else "secondary"):
                    st.session_state[mode_key] = "Webcam"
                    st.rerun()
            
            st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)
            
            # 4. Render Input area
            if st.session_state[mode_key] == "Upload":
                uploaded_files = st.file_uploader(
                    f"Choose images for {cls_name}",
                    type=["jpg", "jpeg", "png", "bmp", "webp"],
                    accept_multiple_files=True,
                    key=f"uploader_{idx}",
                    label_visibility="collapsed"
                )
                if uploaded_files:
                    # Brief gallery of selected files
                    preview_cols = st.columns(min(len(uploaded_files), 4))
                    for p_idx, f in enumerate(uploaded_files[:4]):
                        with preview_cols[p_idx]:
                            st.image(f, use_container_width=True)
                    if len(uploaded_files) > 4:
                        st.caption(f"... and {len(uploaded_files) - 4} more")
                        
                    if st.button(f"Add {len(uploaded_files)} images to '{cls_name}'", key=f"save_btn_{idx}", type="primary", use_container_width=True):
                        with st.spinner("Uploading images..."):
                            files_payload = [
                                ("files", (f.name, io.BytesIO(f.getvalue()), f.type))
                                for f in uploaded_files
                            ]
                            data, status = call_api(
                                "POST", "/upload-sample",
                                data={"class_name": cls_name},
                                files=files_payload,
                                timeout=30,
                            )
                        if status == 200:
                            # Sync local class name with backend's sanitized name
                            backend_name = data.get("class_name", cls_name)
                            if backend_name != cls_name:
                                st.session_state.local_classes[idx] = backend_name
                                if cls_name in st.session_state.counts:
                                    st.session_state.counts[backend_name] = st.session_state.counts.pop(cls_name)
                            st.toast("Images uploaded successfully!", icon="✅")
                            refresh_classes()
                            st.rerun()
                        elif data:
                            st.error(data.get("detail", "Upload failed."))
                            
            elif st.session_state[mode_key] == "Webcam":
                # ── 4-Photo Burst Capture Flow ────────────────────────────
                burst_key = f"burst_{idx}"
                burst_hash_key = f"burst_hash_{idx}"
                if burst_key not in st.session_state.burst_counts:
                    st.session_state.burst_counts[burst_key] = 0
                if burst_hash_key not in st.session_state.burst_frames:
                    st.session_state.burst_frames[burst_hash_key] = None

                current_burst = st.session_state.burst_counts[burst_key]
                total_burst = 4

                if current_burst < total_burst:
                    # Show progress indicator
                    remaining = total_burst - current_burst
                    if current_burst > 0:
                        st.markdown(
                            f'<div style="background-color:rgba(59, 130, 246, 0.1); border:1px solid #3B82F6; '
                            f'padding:10px; border-radius:8px; margin-bottom:10px; text-align:center;">'
                            f'<strong style="color:#1E3A8A;">📸 Photo {current_burst}/{total_burst} captured</strong><br/>'
                            f'<span style="font-size:12px; color:#1E3A8A;">Take {remaining} more photo(s) to complete the burst.</span></div>',
                            unsafe_allow_html=True
                        )
                        st.progress(current_burst / total_burst)
                    else:
                        st.markdown(
                            f'<div style="background-color:rgba(107, 114, 128, 0.1); border:1px solid #9CA3AF; '
                            f'padding:10px; border-radius:8px; margin-bottom:10px; text-align:center;">'
                            f'<strong style="color:#374151;">📷 Burst Capture Mode</strong><br/>'
                            f'<span style="font-size:12px; color:#6B7280;">Take 4 photos — each will be auto-uploaded.</span></div>',
                            unsafe_allow_html=True
                        )

                    cam_frame = st.camera_input(
                        f"Capture photo {current_burst + 1} of {total_burst} for {cls_name}",
                        key=f"cam_{idx}",
                        label_visibility="collapsed"
                    )

                    if cam_frame:
                        # Check if this is a new frame (not the same one from last rerun)
                        frame_hash = hash(cam_frame.getvalue())
                        if frame_hash != st.session_state.burst_frames[burst_hash_key]:
                            st.session_state.burst_frames[burst_hash_key] = frame_hash
                            # Auto-upload this frame immediately
                            with st.spinner(f"Uploading photo {current_burst + 1}/{total_burst}..."):
                                data, status = call_api(
                                    "POST", "/upload-sample",
                                    data={"class_name": cls_name},
                                    files=[("files", (f"webcam_{current_burst+1}.jpg", io.BytesIO(cam_frame.getvalue()), "image/jpeg"))],
                                    timeout=15,
                                )
                            if status == 200:
                                # Sync local class name with backend's sanitized name
                                backend_name = data.get("class_name", cls_name)
                                if backend_name != cls_name:
                                    st.session_state.local_classes[idx] = backend_name
                                    if cls_name in st.session_state.counts:
                                        st.session_state.counts[backend_name] = st.session_state.counts.pop(cls_name)
                                st.session_state.burst_counts[burst_key] = current_burst + 1
                                st.toast(f"📸 Photo {current_burst + 1}/{total_burst} captured!", icon="✅")
                                # Clear the camera widget so user can take next photo
                                if f"cam_{idx}" in st.session_state:
                                    del st.session_state[f"cam_{idx}"]
                                refresh_classes()
                                st.rerun()
                            elif data:
                                st.error(data.get("detail", "Upload failed."))
                else:
                    # All 4 photos captured — show success
                    st.markdown(
                        f'<div style="background-color:rgba(16, 185, 129, 0.12); border:1px solid #10B981; '
                        f'padding:12px; border-radius:8px; text-align:center; margin-bottom:10px;">'
                        f'<strong style="color:#065F46;">✅ All {total_burst} photos captured!</strong></div>',
                        unsafe_allow_html=True
                    )
                    st.progress(1.0)
                    if st.button("🔄 Take 4 More Photos", key=f"reset_burst_{idx}", use_container_width=True):
                        st.session_state.burst_counts[burst_key] = 0
                        st.session_state.burst_frames[burst_hash_key] = None
                        if f"cam_{idx}" in st.session_state:
                            del st.session_state[f"cam_{idx}"]
                        st.rerun()

    # ➕ Add dynamic class button
    if st.button("➕ Add a class", use_container_width=True):
        st.session_state.local_classes.append(f"Class {len(st.session_state.local_classes) + 1}")
        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# COLUMN 2: TRAINING CARD
# ══════════════════════════════════════════════════════════════════════════════
with col_training:
    st.subheader("⚙️ Training")
    st.caption("Train a Support Vector Machine model on top of MobileNetV3 features.")
    
    with st.container(border=True):
        # Calculate readiness
        n_classes = len(st.session_state.local_classes)
        # Only count classes that have 5 or more images uploaded in backend
        sufficient_classes = [c for c in st.session_state.local_classes if st.session_state.counts.get(c, 0) >= 5]
        can_train = n_classes >= 2 and len(sufficient_classes) == n_classes
        
        if can_train:
            st.markdown(
                '<div style="background-color:rgba(16, 185, 129, 0.12); border-left: 5px solid #10B981; '
                'padding: 12px; border-radius: 6px; color: #065F46; font-size: 14px; font-weight: 500; margin-bottom:15px;">'
                '🚀 Ready to Train!<br/>All classes have at least 5 images.</div>', 
                unsafe_allow_html=True
            )
        else:
            st.markdown(
                '<div style="background-color:rgba(245, 158, 11, 0.12); border-left: 5px solid #F59E0B; '
                'padding: 12px; border-radius: 6px; color: #78350F; font-size: 14px; font-weight: 500; margin-bottom:15px;">'
                '⚠️ Prerequisites Missing:<br/>Ensure you have at least 2 classes and every class has 5+ images.</div>', 
                unsafe_allow_html=True
            )
            # List details
            for c in st.session_state.local_classes:
                cnt = st.session_state.counts.get(c, 0)
                if cnt < 5:
                    st.caption(f"❌ **{c}**: {cnt}/5 images")
                else:
                    st.caption(f"✅ **{c}**: {cnt} images")
                    
        st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)
        
        # Train Button
        if st.button("Train Model", type="primary", disabled=not can_train, use_container_width=True):
            with st.spinner("Extracting features and training SVM... (this may take up to 60s)"):
                data, status = call_api("POST", "/train", timeout=300)
            if status == 200:
                st.session_state.trained = True
                st.session_state.train_result = data
                st.toast("Model trained successfully!", icon="🚀")
                st.rerun()
            elif data:
                st.error(data.get("detail", "Training failed."))
        
        # Display model stats if trained
        if st.session_state.train_result:
            tr = st.session_state.train_result
            st.divider()
            st.markdown("##### 📊 Last Training Session:")
            # Show the number of images the user actually uploaded (tracked in session state)
            uploaded_total = int(sum(st.session_state.counts.values())) if st.session_state.counts else 0
            st.metric(label="Total Uploaded Images", value=uploaded_total)
            # Backend `total_samples` may include augmented variants; show it only as a detail
            backend_total = tr.get("total_samples", None)
            if backend_total is not None and backend_total != uploaded_total:
                st.caption(f"(Backend used {backend_total} samples including augmentations)")
            if "cv_accuracy" in tr:
                st.metric(label="Cross-Val Accuracy", value=tr["cv_accuracy"])
            else:
                st.caption("No cross-val generated (requires ≥ 5 images per class).")
                
        # Advanced Hyperparameters Expandable Card
        st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)
        with st.expander("🛠️ Advanced Settings", expanded=False):
            st.markdown(
                """
                **Feature Extractor:**
                - Backbone: MobileNetV3-Large (ImageNet)
                - Feature Dim: 960 (L2-Normalized)
                - Parameters: Frozen (Transfer Learning)
                
                **Classifier Head:**
                - Model: Support Vector Machine (SVM)
                - Kernel: Radial Basis Function (RBF)
                - Regularization C: 10.0
                - Scaling: Platt Scaling (enables prob. estimation)
                - Confidence Gate: 60%
                """
            )


# ══════════════════════════════════════════════════════════════════════════════
# COLUMN 3: PREVIEW & TEST CARD
# ══════════════════════════════════════════════════════════════════════════════
with col_preview:
    st.subheader("🔮 Preview")
    st.caption("Test the real-world performance of your newly trained model.")
    
    with st.container(border=True):
        if not st.session_state.trained:
            # Untrained Placeholder Graphic
            st.markdown(
                """
                <div style="text-align: center; padding: 40px 10px; color: #64748B;">
                    <div style="font-size: 50px; margin-bottom:10px;">🔒</div>
                    <h5 style="color: #64748B; font-weight:600;">Model Untrained</h5>
                    <p style="font-size: 13px; opacity:0.8;">Once you train a model on the left, you can test it live in this panel.</p>
                </div>
                """, 
                unsafe_allow_html=True
            )
        else:
            test_mode = st.radio(
                "Select Test Input Mode",
                ["Upload file", "Webcam"],
                horizontal=True,
                key="test_mode_radio",
                label_visibility="collapsed"
            )
            
            test_bytes = None
            if test_mode == "Upload file":
                test_file = st.file_uploader(
                    "Choose test image",
                    type=["jpg", "jpeg", "png", "bmp", "webp"],
                    key="test_uploader",
                    label_visibility="collapsed"
                )
                if test_file:
                    test_bytes = test_file.getvalue()
            else:
                test_cam = st.camera_input("Capture test image", key="test_cam", label_visibility="collapsed")
                if test_cam:
                    test_bytes = test_cam.getvalue()
            
            # Predict Logic
            if test_bytes:
                st.markdown("<div style='height:15px;'></div>", unsafe_allow_html=True)
                test_hash = hash(test_bytes)
                
                # Dynamic call caching
                if st.session_state.last_test_hash != test_hash:
                    with st.spinner("Classifying test image..."):
                        data, status = call_api(
                            "POST", "/predict",
                            files=[("file", ("test.jpg", test_bytes, "image/jpeg"))],
                            timeout=30,
                        )
                    if status == 200:
                        st.session_state.last_test_hash = test_hash
                        st.session_state.last_prediction = data
                    else:
                        st.session_state.last_prediction = None
                        if data:
                            st.error(data.get("detail", "Prediction failed."))
                
                # Show results & progress bars
                if st.session_state.last_prediction:
                    data = st.session_state.last_prediction
                    conf  = data["confidence"]
                    pred  = data["predicted_class"]
                    probs = data["all_probabilities"]
                    
                    # Image preview
                    st.image(Image.open(io.BytesIO(test_bytes)), use_container_width=True)
                    st.divider()
                    
                    if data["uncertain"]:
                        st.markdown(
                            f'<div style="background-color:rgba(245, 158, 11, 0.1); border:1px solid #F59E0B; padding:12px; border-radius:8px; margin-bottom:20px;">'
                            f'<strong style="color:#78350F;">⚠️ Prediction: Uncertain ({conf}%)</strong><br/>'
                            f'<span style="font-size:12px; color:#78350F; opacity:0.9;">{data["message"]}</span></div>',
                            unsafe_allow_html=True
                        )
                    else:
                        st.markdown(
                            f'<div style="background-color:rgba(59, 130, 246, 0.1); border:1px solid #3B82F6; padding:12px; border-radius:8px; margin-bottom:20px;">'
                            f'<strong style="color:#1E3A8A;">🏆 Prediction: {pred} ({conf}%)</strong><br/>'
                            f'<span style="font-size:12px; color:#1E3A8A; opacity:0.9;">{data["message"]}</span></div>',
                            unsafe_allow_html=True
                        )
                    
                    st.markdown("##### Output Confidence per Class:")
                    for cls, pct in probs.items():
                        is_winner = (cls == pred and not data["uncertain"])
                        # Render a custom colored highlight for the winning bar label
                        label_style = "class=\'winning-bar-text\'" if is_winner else ""
                        st.markdown(f"<span {label_style}>{cls} — {pct}%</span>", unsafe_allow_html=True)
                        st.progress(int(pct))


# ══════════════════════════════════════════════════════════════════════════════
# FOOTER
# ══════════════════════════════════════════════════════════════════════════════
st.divider()
st.caption(
    "Powered by MobileNetV3 Feature Extraction (960-dim) + Radial Support Vector Classifier (RBF SVM). "
    "Platt probabilities scaling is bounded by a 60% confidence gate. Designed to work just like Google Teachable Machine."
)
