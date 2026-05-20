"""
main.py  —  FastAPI application: routes only, no business logic
════════════════════════════════════════════════════════════════
WHY THIS FILE EXISTS:
  This file's ONLY job is to define HTTP endpoints (routes) and connect them
  to the right utility functions. It does NOT:
    • Touch the file system directly
    • Run any machine learning code directly
    • Know anything about PyTorch or scikit-learn

  All real work is delegated to:
    → app.utils.data_utils  (file system operations)
    → app.utils.ml_utils    (machine learning)

  This pattern is called "thin controller / fat service" and makes the code
  much easier to read, test, and maintain.

API ENDPOINTS SUMMARY:
  GET  /              → health check
  GET  /classes       → list classes and image counts
  POST /upload-sample → save images to dataset/<class>/
  POST /train         → train the SVM classifier
  POST /predict       → classify one image
  DELETE /reset       → wipe dataset and model
"""

import logging
from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.utils.data_utils import (
    save_images,
    get_class_info,
    validate_dataset,
    reset_dataset,
)
from app.utils.ml_utils import train_model, predict_image

# ── Logging setup ─────────────────────────────────────────────────────────────
# Shows INFO-level logs in the terminal when you run uvicorn.
# You'll see messages like "Saved: abc123.jpg → Cat/"
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s | %(name)s | %(message)s"
)

# ── App Instance ──────────────────────────────────────────────────────────────
app = FastAPI(
    title="Teachable Machine API",
    description="Train a custom image classifier via HTTP — no ML knowledge needed.",
    version="2.0",
)

# ── CORS Middleware ───────────────────────────────────────────────────────────
# Allows the Streamlit frontend (running on port 8501) to call this API
# (running on port 8000). Without this, browsers block cross-origin requests.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # in production, replace "*" with your frontend URL
    allow_methods=["*"],
    allow_headers=["*"],
)


# ══════════════════════════════════════════════════════════════════════════════
# ROUTE 1: Health Check
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/")
def health_check():
    """
    Simple ping endpoint.
    The Streamlit sidebar calls this to show "Backend connected ✅" or "❌".
    """
    return {"status": "ok", "message": "Teachable Machine API is running."}


# ══════════════════════════════════════════════════════════════════════════════
# ROUTE 2: List Classes
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/classes")
def list_classes():
    """
    Return all current class names and their image counts.

    Example response:
        {
          "classes": ["Cat", "Dog"],
          "counts":  {"Cat": 12, "Dog": 8},
          "total":   20
        }

    Called by:
        • Streamlit sidebar to show the dataset overview
        • After every upload to refresh the count display
    """
    return get_class_info()


# ══════════════════════════════════════════════════════════════════════════════
# ROUTE 3: Upload Training Images
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/upload-sample")
async def upload_sample(
    class_name: str             = Form(...),
    files:      list[UploadFile] = File(...),
):
    """
    Save one or more images into dataset/<class_name>/.

    Parameters (sent as multipart/form-data):
        class_name : text field — the category label (e.g., "Cat")
        files      : one or more image files

    HOW MULTIPART/FORM-DATA WORKS:
        The browser/Streamlit bundles the class_name text and the image files
        together in one HTTP request body. FastAPI's Form() and File() decorators
        automatically parse them out for us.

    Example response:
        {
          "class_name": "Cat",
          "saved": 5,
          "skipped": 0,
          "total": 12,
          "message": "Saved 5 image(s). 'Cat' now has 12 total."
        }
    """
    if not class_name or not class_name.strip():
        raise HTTPException(status_code=422, detail="class_name cannot be empty.")

    # Read all file bytes upfront (UploadFile is async, data_utils expects bytes)
    images_bytes = []
    for f in files:
        if not f.content_type.startswith("image/"):
            continue   # silently skip non-image files (e.g., PDFs accidentally uploaded)
        raw = await f.read()
        images_bytes.append(raw)

    if not images_bytes:
        raise HTTPException(
            status_code=422,
            detail="No valid image files found in the upload."
        )

    try:
        result = save_images(class_name, images_bytes)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    result["message"] = (
        f"Saved {result['saved']} image(s). "
        f"'{result['class_name']}' now has {result['total']} total."
    )
    return result


# ══════════════════════════════════════════════════════════════════════════════
# ROUTE 4: Train the Model
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/train")
def train():
    """
    Extract features for all dataset images, train an SVM, save model.pkl.

    This is the most compute-intensive endpoint — expect 15–60 seconds
    depending on how many images you have and whether a GPU is available.

    Calls validate_dataset() first to give clear error messages
    instead of cryptic ML exceptions.

    Example response:
        {
          "status": "trained",
          "classes": ["Cat", "Dog"],
          "samples_per_class": {"Cat": 12, "Dog": 8},
          "total_samples": 20,
          "cv_accuracy": "91.67%"
        }
    """
    # Guard: check prerequisites before starting expensive training
    is_valid, error_message = validate_dataset()
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_message)

    try:
        result = train_model()
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"status": "trained", **result}


# ══════════════════════════════════════════════════════════════════════════════
# ROUTE 5: Predict
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/predict")
async def predict(file: UploadFile = File(...)):
    """
    Classify a single image using the saved model.

    Parameter (sent as multipart/form-data):
        file : one image file

    Example response (confident):
        {
          "predicted_class": "Cat",
          "confidence": 91.3,
          "uncertain": false,
          "all_probabilities": {"Cat": 91.3, "Dog": 8.7},
          "message": "Predicted 'Cat' with 91.3% confidence."
        }

    Example response (uncertain):
        {
          "predicted_class": "uncertain",
          "confidence": 54.2,
          "uncertain": true,
          "all_probabilities": {"Cat": 54.2, "Dog": 45.8},
          "message": "Low confidence (54.2%). Add more diverse training images."
        }
    """
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=422, detail="Uploaded file must be an image.")

    image_bytes = await file.read()

    try:
        result = predict_image(image_bytes)
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return result


# ══════════════════════════════════════════════════════════════════════════════
# ROUTE 6: Reset
# ══════════════════════════════════════════════════════════════════════════════

@app.delete("/reset")
def reset():
    """
    Delete all dataset images and the saved model. Start fresh.

    Use this when you want to train a completely new set of classes.

    Example response:
        {"status": "reset", "message": "Dataset and model cleared."}
    """
    reset_dataset()
    return {"status": "reset", "message": "Dataset and model cleared."}
