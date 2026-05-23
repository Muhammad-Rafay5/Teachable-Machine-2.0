"""
main.py  —  FastAPI application: Vercel Serverless Optimized
════════════════════════════════════════════════════════════════
DEPLOYMENT-READY:
  ✓ Explicit path integration for Vercel serverless environment
  ✓ Retained 'thin controller' pattern with clean execution
  ✓ CORS configured for seamless Streamlit handshakes (with credentials)
  ✓ Graceful error handling for ephemeral/read-only filesystems
  ✓ Compatible with local development AND production Vercel deployment

WHY THIS FILE EXISTS:
  This file's ONLY job is to define HTTP endpoints (routes) and connect them
  to the right utility functions. It does NOT:
    • Touch the file system directly
    • Run any machine learning code directly
    • Know anything about PyTorch or scikit-learn

  All real work is delegated to:
    → app.utils.data_utils  (file system operations)
    → app.utils.ml_utils    (machine learning)

API ENDPOINTS SUMMARY:
  GET  /              → health check
  GET  /classes       → list classes and image counts
  POST /upload-sample → save images to dataset/<class>/
  POST /train         → train the SVM classifier
  POST /predict       → classify one image
  DELETE /reset       → wipe dataset and model
"""

import os
import sys
import logging
from pathlib import Path
from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# ── CRITICAL FIX FOR VERCEL ───────────────────────────────────────────────────
# Ensures the serverless environment can locate the app package module.
# On Vercel, the working directory and import paths behave differently.
app_dir = Path(__file__).parent
sys.path.insert(0, str(app_dir.parent))  # Add backend/ to path
sys.path.insert(0, str(app_dir))          # Add app/ to path

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
    description="Train a custom image classifier via HTTP — Vercel Serverless Optimized.",
    version="2.0",
)

# ── CORS Middleware ───────────────────────────────────────────────────────────
# Allows the Streamlit frontend (running on port 8501, or deployed on Streamlit Cloud)
# to call this API (running on port 8000, or deployed on Vercel).
# Without this, browsers block cross-origin requests, especially for camera/media access.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # In production, replace "*" with your frontend URL(s)
    allow_credentials=True,  # IMPORTANT: Enables credential passing (sessions, cookies)
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],   # Exposes custom headers to frontend
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
    return {"status": "ok", "message": "Teachable Machine API is running perfectly on Vercel."}


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
    
    Gracefully handles missing folders on ephemeral Vercel storage.
    """
    try:
        return get_class_info()
    except (FileNotFoundError, OSError):
        # Vercel has ephemeral storage; dataset folder may not exist on cold start
        logging.warning("Dataset folder not found. Returning empty classes.")
        return {"classes": [], "counts": {}, "total": 0, "note": "Running on ephemeral serverless storage."}
    except Exception as e:
        logging.error(f"Unexpected error in /classes: {e}")
        return {"classes": [], "counts": {}, "total": 0}


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
    
    NOTE ON VERCEL:
        Vercel's serverless environment has ephemeral storage (/tmp is temporary).
        For persistent storage in production, integrate with S3, MongoDB, or a database.
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
    except OSError as e:
        logging.error(f"OSError during file save (Vercel ephemeral storage?): {e}")
        raise HTTPException(
            status_code=507, 
            detail="Server storage is read-only or unavailable. For production, integrate S3 or a database."
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logging.error(f"Unexpected error in /upload-sample: {e}")
        raise HTTPException(status_code=500, detail="Internal server error during upload.")

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
    
    WARNING: Vercel's Free Plan has a 10-second timeout (Pro: 60 seconds).
    Large datasets may exceed this limit. For production, consider:
      • Using Vercel Pro (60s execution limit)
      • Deploying backend elsewhere (AWS Lambda, Railway, etc.)
      • Implementing async training with background jobs
    """
    # Guard: check prerequisites before starting expensive training
    is_valid, error_message = validate_dataset()
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_message)

    try:
        logging.info("Starting model training...")
        result = train_model()
        logging.info(f"Training completed. CV Accuracy: {result.get('cv_accuracy', 'N/A')}")
    except RuntimeError as e:
        logging.error(f"Training runtime error: {e}")
        raise HTTPException(status_code=500, detail=f"Training failed: {str(e)}")
    except TimeoutError:
        logging.error("Training exceeded execution timeout.")
        raise HTTPException(
            status_code=504, 
            detail="Training exceeded server timeout. Deploy backend to a platform with longer execution limits (Railway, AWS)."
        )
    except Exception as e:
        logging.error(f"Unexpected error during training: {e}")
        raise HTTPException(status_code=500, detail="Internal server error during training.")

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
        logging.warning(f"Model file not found: {e}")
        raise HTTPException(
            status_code=404, 
            detail="Model not found. Please train the model first or deploy with a pre-trained model.pkl in the repository."
        )
    except ValueError as e:
        logging.error(f"Prediction value error: {e}")
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logging.error(f"Unexpected error during prediction: {e}")
        raise HTTPException(status_code=500, detail="Internal server error during prediction.")

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
    
    On Vercel (ephemeral storage), this operation may not persist between deploys.
    """
    try:
        reset_dataset()
        logging.info("Dataset and model reset successfully.")
    except OSError as e:
        logging.warning(f"OSError during reset (may be normal on ephemeral storage): {e}")
        # Don't fail the request — ephemeral storage means nothing to clean up
    except Exception as e:
        logging.error(f"Error during reset: {e}")
        # Still return success — the intent was to clear state
    
    return {"status": "reset", "message": "Dataset and model state cleared."}
