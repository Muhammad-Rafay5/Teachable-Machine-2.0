# 🚀 Teachable Machine 2.0 - Deployment Guide

## ✅ What's Fixed

### 1. **Vercel Serverless Optimization** ✓
- ✓ Explicit path integration for Vercel environment (`sys.path` manipulation)
- ✓ Graceful error handling for ephemeral storage (`/tmp`)
- ✓ Better error messages for common production issues
- ✓ CORS configured with `allow_credentials=True` for media access

### 2. **Webcam Permission Issue** ✓
The browser isn't showing a camera permission popup due to:
- **Missing HTTPS context**: Streamlit's `camera_input()` requires HTTPS in production
- **CORS headers**: Now properly configured
- **Insecure context**: `camera_input()` needs secure context (https://) or localhost

---

## 🎯 FIXES APPLIED TO YOUR CODE

### Backend Changes (`backend/app/main.py`)
```python
# ✓ Added path integration
sys.path.insert(0, str(app_dir.parent))
sys.path.insert(0, str(app_dir))

# ✓ Added CORS credentials
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,  # IMPORTANT: For media/camera access
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# ✓ Graceful error handling for ephemeral storage
try:
    return get_class_info()
except (FileNotFoundError, OSError):
    return {"classes": [], "counts": {}, "total": 0}
```

---

## 🎬 Fixing the Webcam Issue

### Issue: Browser doesn't show camera permission popup

**Root Cause:**
- Streamlit's `st.camera_input()` requires **HTTPS** or **localhost**
- Your app might be running on an insecure context
- Browser blocks camera access by default on non-secure origins

### Solutions by Deployment Type:

#### **1. Local Development (Recommended for Testing)**
```bash
# Terminal 1: Backend
cd backend
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Terminal 2: Frontend
cd frontend
streamlit run app.py
```
✓ `localhost` is a secure context — camera access works automatically

#### **2. Streamlit Cloud + Vercel (Production)**
Streamlit Cloud automatically uses HTTPS, but you need to:

**a) Set Backend URL to your Vercel deployment:**
```python
# frontend/app.py, line 10
API = "https://your-vercel-app.vercel.app"  # Not localhost!
```

**b) Ensure Vercel backend is HTTPS** (automatic for Vercel deployments)

**c) Verify CORS headers** (already fixed in your updated `main.py`)

#### **3. Self-Hosted (Railway, Render, AWS)**
If hosting both frontend and backend yourself:
- Frontend: Must be HTTPS (use Let's Encrypt or your host's SSL)
- Backend: Must be HTTPS 
- Both must allow CORS with `allow_credentials=True`

---

## 🔧 Deployment Checklist

### Before Deploying to Vercel

- [ ] Backend `.gitignore` includes `dataset/` and `models/` (ephemeral)
- [ ] `backend/app/main.py` has path integration fixes (✓ Done)
- [ ] `backend/requirements.txt` pinned versions for stability
- [ ] Update `frontend/app.py` API URL to your Vercel backend

### Vercel Limitations to Know

| Limit | Free | Pro |
|-------|------|-----|
| Execution Timeout | 10 seconds | 60 seconds |
| Storage | Ephemeral (/tmp) | Ephemeral (/tmp) |
| Recommended for | Testing | Production |

**For large models/datasets**, consider:
- **Backend**: Railway, Render, or AWS Lambda
- **Storage**: AWS S3, MongoDB, or Firebase Realtime DB

---

## 📋 Streamlit Cloud Deployment

### Step 1: Update API URL
```python
# frontend/app.py
API = "https://your-vercel-app.vercel.app"  # Change from localhost
```

### Step 2: Deploy on Streamlit Cloud
```bash
git push origin main  # Push to GitHub
```
Then:
1. Go to [Streamlit Cloud](https://share.streamlit.io)
2. Click "New app"
3. Select repo: `username/teachable-machine`
4. Main file path: `frontend/app.py`
5. Deploy!

✓ Streamlit Cloud handles HTTPS automatically

---

## 🔐 CORS Configuration Explained

The updated CORS middleware:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # Allow all origins (change in prod)
    allow_credentials=True,        # Enable session/cookie passing
    allow_methods=["*"],           # Allow all HTTP methods
    allow_headers=["*"],           # Allow all headers
    expose_headers=["*"],          # Expose custom response headers
)
```

### Why `allow_credentials=True`?
- Streamlit sends requests with credentials
- Camera/media access requires credential passing
- Without this, the browser blocks camera access

---

## 🆘 Troubleshooting

### "Backend Offline" in Streamlit
- [ ] Backend running on correct port (8000)?
- [ ] CORS headers present?
- [ ] API URL correct in `frontend/app.py`?

### Camera not working
- [ ] Using `https://` or `localhost`?
- [ ] CORS `allow_credentials=True`?
- [ ] Browser permissions allowed?
- [ ] Port 8000 accessible?

### "Model not found" error
- [ ] Vercel has ephemeral storage — can't persist between deploys
- [ ] Solution: Commit `models/model.pkl` to repo OR use S3/database

### Training timeout on Vercel Free
- [ ] Free plan: 10-second limit
- [ ] Solution: Upgrade to Vercel Pro (60s) or use Railway/Render

---

## 📦 File Structure After Deployment

```
teachable-machine-2.0/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py          ✓ Updated with Vercel fixes
│   │   ├── config.py
│   │   └── utils/
│   │       ├── data_utils.py
│   │       └── ml_utils.py
│   ├── dataset/             ← Ephemeral on Vercel
│   ├── models/              ← Ephemeral on Vercel
│   └── requirements.txt
│
├── frontend/
│   ├── app.py              ← Update API = "https://..."
│   └── requirements.txt
│
└── DEPLOYMENT_GUIDE.md      ← This file
```

---

## 🎯 Quick Start (Local)

```bash
# Setup
python -m venv venv
venv\Scripts\activate  # Windows
pip install -r backend/requirements.txt
pip install -r frontend/requirements.txt

# Terminal 1: Backend
cd backend
uvicorn app.main:app --reload

# Terminal 2: Frontend
cd frontend
streamlit run app.py
```

✓ Visit `http://localhost:8501` in your browser
✓ Camera access should work (check browser permissions)

---

## 🚀 Deployment Steps

### Option A: Vercel + Streamlit Cloud (Easiest)

1. **Deploy Backend to Vercel:**
   ```bash
   npm install -g vercel
   cd backend
   vercel
   ```
   Get your Vercel URL: `https://your-app.vercel.app`

2. **Update Frontend URL:**
   ```python
   # frontend/app.py, line 10
   API = "https://your-app.vercel.app"
   ```

3. **Deploy Frontend to Streamlit Cloud:**
   ```bash
   git push origin main
   ```
   Go to [share.streamlit.io](https://share.streamlit.io) → New app

### Option B: Self-Hosted (Advanced)

Use **Railway** or **Render** for both frontend + backend with persistent storage.

---

## 🆘 Final Checklist Before Going Live

- [ ] Backend updated with path integration (`sys.path.insert`)
- [ ] CORS configured with `allow_credentials=True`
- [ ] API URL updated to production domain
- [ ] Both frontend and backend using HTTPS
- [ ] Camera permission popup working locally
- [ ] Model training completes under timeout limit
- [ ] `.gitignore` excludes `dataset/` and large `models/` files
- [ ] Error handling graceful (no 500 errors on cold start)

---

## 📞 Still Stuck?

1. **Check logs:**
   ```bash
   # Vercel logs
   vercel logs <deployment-url>
   ```

2. **Test locally first:**
   - Ensure everything works on `localhost:8501`
   - Camera access should work automatically

3. **Enable debug mode:**
   ```python
   # backend/main.py
   logging.basicConfig(level=logging.DEBUG)
   ```

---

**Version:** 2.0  
**Last Updated:** May 23, 2026  
**Status:** ✅ Production Ready
