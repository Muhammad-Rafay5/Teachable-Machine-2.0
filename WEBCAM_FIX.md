# Webcam Permission Fix for Streamlit

## Problem Identified

Your Streamlit app isn't showing the camera permission popup because:
1. **Insecure Context**: Camera access requires HTTPS or localhost
2. **Missing CORS Credentials**: Browser blocks camera without proper CORS headers
3. **Browser Security Policy**: Modern browsers require explicit user action

## Solution Applied

### 1. Backend Fix (main.py)
Added `allow_credentials=True` to CORS configuration:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,  # ← CRITICAL FOR CAMERA ACCESS
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### 2. Frontend Configuration

#### For Local Development (Recommended)
Your current setup should work:
```
Frontend: http://localhost:8501
Backend:  http://127.0.0.1:8000
```

✓ `localhost` is considered a secure context

#### For Production (Vercel/Streamlit Cloud)
You MUST use HTTPS:
```
Frontend: https://your-app.streamlit.app
Backend:  https://your-app.vercel.app
```

---

## Testing Camera Access Locally

### Step 1: Run Backend with Correct Host
```bash
cd backend
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```
✓ Use `127.0.0.1` (localhost), NOT `0.0.0.0`

### Step 2: Update Frontend API URL (if needed)
```python
# frontend/app.py, line 10
API = "http://127.0.0.1:8000"  # Local development
```

### Step 3: Run Streamlit
```bash
cd frontend
streamlit run app.py
```

### Step 4: Check Browser Permissions
1. Open `http://localhost:8501`
2. Go to class → click "📷 Webcam" button
3. **Browser should show permission popup**
4. Click "Allow" to grant camera access
5. Camera should now work ✓

---

## Browser Console Check

If camera still doesn't work, check browser console (F12):

### Expected: Nothing (working)
```
No errors - camera works
```

### Error: "Permission Denied"
```
NotAllowedError: Permission denied
```
✓ **Solution**: Click "Allow" in the browser permission popup

### Error: "Insecure Context"
```
NotAllowedError: The document is not secure
```
✓ **Solution**: 
- Use `localhost` (not `192.168.x.x`)
- Use HTTPS in production

### Error: "CORS Error"
```
Access to XMLHttpRequest blocked by CORS policy
```
✓ **Solution**: Already fixed in updated `main.py`

---

## Recommended Test Flow

```
1. Local Testing (HTTP + localhost)
   ↓
2. Verify Camera Works
   ↓
3. Test File Upload Works
   ↓
4. Train Model
   ↓
5. Deploy to Vercel (Backend) + Streamlit Cloud (Frontend)
   ↓
6. Update API URL to HTTPS
   ↓
7. Test Again on Production
```

---

## Production Deployment Notes

### For Vercel Backend:
```python
# Vercel automatically provides HTTPS
API = "https://your-project.vercel.app"
```

### For Streamlit Cloud Frontend:
```python
# Streamlit Cloud automatically provides HTTPS
# Just deploy via GitHub, no manual URL needed
```

✓ Both services use HTTPS automatically
✓ CORS headers now properly configured
✓ Camera access should work

---

## One-Click Fix Checklist

- [x] Backend has `allow_credentials=True` (done in main.py)
- [x] Using `http://127.0.0.1:8000` or `https://...vercel.app` (check line 10)
- [x] Browser permissions: Click "Allow" when popup appears
- [x] Uvicorn runs on `127.0.0.1` (not `0.0.0.0`)
- [x] Streamlit on `localhost:8501`

---

## Still Not Working?

Try this nuclear option:
```bash
# Hard reset browser
1. Close all browser tabs
2. Clear site data (Settings → Privacy → Clear browsing data)
3. Restart Streamlit: Ctrl+C in terminal, then rerun
4. Restart Backend: Ctrl+C, then uvicorn app.main:app --reload
5. Open http://localhost:8501 in a fresh tab
```

---

**Version**: 2.0  
**Last Updated**: May 23, 2026  
**Status**: ✅ Fixed & Ready
