"""
ml_utils.py  —  All machine learning logic (no routing, no file I/O)
════════════════════════════════════════════════════════════════════════
WHY THIS FILE EXISTS:
  Keeps every ML decision in one place so you can understand, tweak,
  or swap the model without touching any other file.

THE ML PIPELINE (read this first):
  ┌─────────────────────────────────────────────────────────────┐
  │  Your image (any size, any format)                          │
  │        ↓                                                    │
  │  [Resize → CenterCrop → Normalize]   ← TRANSFORM           │
  │        ↓                                                    │
  │  MobileNetV3-Large (960 features)    ← EXTRACTOR (frozen)  │
  │        ↓                                                    │
  │  L2 Normalize features                                      │
  │        ↓                                                    │
  │  SVM with RBF kernel                 ← the only thing      │
  │        ↓                               that TRAINS         │
  │  Probability per class (Platt scaling)                      │
  │        ↓                                                    │
  │  Confidence gate (< 60% → "uncertain")                     │
  └─────────────────────────────────────────────────────────────┘

WHAT THIS FILE CONTAINS:
  build_extractor()    → loads MobileNetV3 once at startup
  extract_features()   → runs one image through the frozen backbone
  train_model()        → extracts features for all images, trains SVM, saves model
  predict_image()      → loads saved model, runs prediction on one image
"""

import io
import pickle
import logging
import numpy as np
from pathlib import Path

import torch
import torchvision.transforms as transforms
from torchvision import models
from PIL import Image

from sklearn.svm import SVC
from sklearn.preprocessing import LabelEncoder, normalize
from sklearn.model_selection import StratifiedKFold, cross_val_score

from app.config import settings

log = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — FEATURE EXTRACTOR
# The backbone model is loaded ONCE when the server starts.
# Loading it per-request would add ~2 seconds to every call.
# ══════════════════════════════════════════════════════════════════════════════

def build_extractor() -> torch.nn.Module:
    """
    Load MobileNetV3-Large pretrained on ImageNet, strip the classifier head.

    WHY MobileNetV3:
      - Fast inference (designed for mobile/embedded devices)
      - Strong 960-dim features good enough for small custom datasets
      - Available in torchvision with pretrained ImageNet weights

    WHY STRIP THE HEAD:
      MobileNetV3's original classifier maps 960 features → 1000 ImageNet classes.
      We don't want those 1000 classes — we want YOUR custom classes.
      So we keep everything up to the classifier and add our own SVM on top.

    Structure after stripping:
      Input image (224×224×3)
           ↓
      backbone.features   (convolutional blocks, learns edges/textures/shapes)
           ↓
      backbone.avgpool    (collapses spatial dimensions → one vector per image)
           ↓
      Flatten             (shape: (batch, 960))
    """
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    log.info(f"Using device: {device}")

    # Load with pretrained ImageNet weights
    backbone = models.mobilenet_v3_large(
        weights=models.MobileNet_V3_Large_Weights.DEFAULT
    )

    # Build extractor: features → pool → flatten → 960-dim vector
    extractor = torch.nn.Sequential(
        backbone.features,
        backbone.avgpool,
        torch.nn.Flatten(),
    )

    # eval() disables dropout and batchnorm training mode.
    # CRITICAL: without this, the same image gives different features every call.
    extractor.eval()
    extractor.to(device)

    # Freeze all parameters — we never update these weights.
    # This also saves GPU memory and speeds up inference.
    for param in extractor.parameters():
        param.requires_grad = False

    log.info("MobileNetV3 feature extractor ready.")
    return extractor, device


# ── Global extractor instance (created once at import time) ──────────────────
# Any file that does `from app.utils.ml_utils import EXTRACTOR` gets this
# same already-loaded model — no redundant loading.
EXTRACTOR, DEVICE = build_extractor()


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — IMAGE PREPROCESSING
# This transform pipeline MUST be identical for training AND prediction.
# If they ever differ, the model produces garbage predictions.
# Stored as a module-level constant so there's only one definition.
# ══════════════════════════════════════════════════════════════════════════════

TRANSFORM = transforms.Compose([
    # Step 1: Resize so the SHORT edge = 256px (keeps aspect ratio)
    transforms.Resize(256),

    # Step 2: Crop the center 224×224 region
    # WHY CENTERCROP NOT JUST RESIZE TO 224:
    #   Resizing to exactly 224 distorts non-square images (squashes/stretches).
    #   CenterCrop after Resize(256) gives a clean undistorted 224×224 patch.
    transforms.CenterCrop(224),

    # Step 3: Convert PIL Image to PyTorch tensor
    # PIL stores pixels as uint8 [0, 255]
    # ToTensor() converts to float32 [0.0, 1.0] AND rearranges shape:
    #   (H, W, C) PIL  →  (C, H, W) PyTorch   (channels first)
    transforms.ToTensor(),

    # Step 4: Normalize with ImageNet statistics
    # WHY THESE EXACT NUMBERS:
    #   MobileNetV3 was trained on images normalized this way.
    #   Using different values shifts the feature distribution → wrong features.
    #   Formula: output = (input - mean) / std   applied per channel
    transforms.Normalize(
        mean=settings.IMAGENET_MEAN,   # [0.485, 0.456, 0.406]
        std=settings.IMAGENET_STD,     # [0.229, 0.224, 0.225]
    ),
])


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — FEATURE EXTRACTION (one image → one 960-dim vector)
# ══════════════════════════════════════════════════════════════════════════════

def extract_features(img: Image.Image) -> np.ndarray:
    """
    Run a single PIL image through the frozen MobileNetV3 backbone.

    Parameters:
        img : a PIL Image object (any size, will be resized automatically)

    Returns:
        numpy array of shape (960,) — L2-normalized feature vector

    WHY L2 NORMALIZATION:
        Raw MobileNetV3 features can have very different magnitudes across
        dimensions. L2 normalization projects every feature vector onto the
        unit sphere, so the SVM's RBF kernel measures angles (similarity)
        rather than being dominated by high-magnitude dimensions.

        Think of it like: instead of comparing "how loud" features are,
        we compare "which direction" they point in 960-dim space.
    """
    # Apply preprocessing: PIL Image → normalized tensor of shape (3, 224, 224)
    tensor = TRANSFORM(img).unsqueeze(0).to(DEVICE)
    #   unsqueeze(0) adds a batch dimension: (3, 224, 224) → (1, 3, 224, 224)
    #   the model always expects (batch_size, channels, height, width)

    # Run through the frozen backbone (no gradient tracking needed)
    with torch.no_grad():
        features = EXTRACTOR(tensor)   # shape: (1, 960)

    # Move back to CPU and convert to numpy
    features_np = features.cpu().numpy()   # shape: (1, 960)

    # L2 normalize: each row divided by its Euclidean length
    features_normalized = normalize(features_np, norm="l2")   # shape: (1, 960)

    return features_normalized[0]   # return shape: (960,)


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4 — TRAINING
# ══════════════════════════════════════════════════════════════════════════════

def train_model() -> dict:
    """
    Full training pipeline: scan dataset → extract features → train SVM → save model.

    Returns a dict with training results:
        classes          : list of class names
        samples_per_class: dict of {class: n_images}
        total_samples    : total images used
        cv_accuracy      : cross-validation accuracy (optional, if enough data)

    STEP BY STEP:
        1. Scan dataset/ for class folders
        2. For each image in each folder: extract its 960-dim feature vector
        3. Label each feature vector with its class name
        4. Train an SVM classifier on (features, labels)
        5. Optionally cross-validate to estimate real-world accuracy
        6. Save (SVM + LabelEncoder) to model.pkl
    """
    dataset_dir = settings.DATASET_DIR

    # ── Step 1: Collect all image paths with their class labels ──────────────
    X_raw = []   # will become list of (960,) numpy arrays
    y_raw = []   # will become list of class name strings
    samples_per_class = {}

    class_folders = sorted([
        d for d in dataset_dir.iterdir() if d.is_dir()
    ])

    log.info(f"Found {len(class_folders)} class folders.")

    for class_dir in class_folders:
        image_paths = [
            p for p in class_dir.iterdir()
            if p.suffix.lower() in settings.ALLOWED_EXTENSIONS
        ]
        samples_per_class[class_dir.name] = len(image_paths)
        log.info(f"  Class '{class_dir.name}': {len(image_paths)} images")

        # ── Step 2: Extract features for every image ──────────────────────
        for img_path in image_paths:
            try:
                img = Image.open(img_path).convert("RGB")
                feat = extract_features(img)   # shape: (960,)
                X_raw.append(feat)
                y_raw.append(class_dir.name)
            except Exception as e:
                log.warning(f"  Skipping {img_path.name}: {e}")

    if len(X_raw) == 0:
        raise RuntimeError("No valid images found in the dataset. Add images first.")

    # Convert lists to numpy arrays for scikit-learn
    X = np.array(X_raw)   # shape: (N_total_images, 960)
    y = np.array(y_raw)   # shape: (N_total_images,) — string labels

    # ── Step 3: Encode string labels to integers ──────────────────────────────
    # SVM expects numeric labels: "Cat" → 0, "Dog" → 1
    # LabelEncoder remembers this mapping so we can reverse it at prediction time
    le = LabelEncoder()
    y_encoded = le.fit_transform(y)
    # le.classes_ is now ["Cat", "Dog"] (sorted alphabetically)

    # ── Step 4: Train the SVM ─────────────────────────────────────────────────
    # WHY SVM WITH RBF KERNEL:
    #   - RBF (Radial Basis Function) creates non-linear decision boundaries.
    #     This matters because image features rarely separate linearly.
    #   - "Max margin" principle: SVM finds the boundary with the LARGEST gap
    #     between classes. This makes it more robust on small datasets than
    #     methods that just minimize average error.
    #   - probability=True: uses Platt scaling to convert SVM scores to
    #     proper probabilities (e.g., 87% Cat, 13% Dog). Without this,
    #     SVM only gives you a yes/no decision.
    #   - class_weight='balanced': if Cat has 20 images and Dog has 8,
    #     this automatically upweights Dog samples so the model doesn't
    #     just predict Cat for everything.

    clf = SVC(
        kernel="rbf",              # non-linear boundary
        C=settings.SVM_C,         # 10.0 — regularization strength
        gamma=settings.SVM_GAMMA, # "scale" — auto-calibrated to data
        probability=True,          # enables predict_proba()
        class_weight="balanced",   # handles unequal class sizes
        random_state=42,           # reproducible results
    )

    # ── Step 5: Cross-Validation (optional quality estimate) ──────────────────
    # Cross-validation splits data into N folds, trains on N-1, tests on 1,
    # repeats N times. Gives an honest estimate of real-world accuracy
    # without needing a separate test set.
    #
    # We only do this if there's enough data (≥5 images per class minimum).
    cv_accuracy = None
    min_count = min(samples_per_class.values())

    if min_count >= 5 and len(X) >= len(le.classes_) * 5:
        n_splits = min(5, min_count)   # can't have more folds than samples
        cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
        # StratifiedKFold preserves class ratio in each fold (important for imbalanced data)

        scores = cross_val_score(clf, X, y_encoded, cv=cv, scoring="accuracy")
        cv_accuracy = float(scores.mean())
        log.info(f"Cross-val accuracy: {cv_accuracy:.2%} ± {scores.std():.2%}")

    # Now train on the FULL dataset (cross-val was just for the accuracy estimate)
    clf.fit(X, y_encoded)

    # ── Step 6: Save model to disk ─────────────────────────────────────────────
    # We save both the SVM (clf) and the LabelEncoder (le) together.
    # The LabelEncoder is needed at prediction time to convert 0/1 back to "Cat"/"Dog".
    settings.MODEL_DIR.mkdir(parents=True, exist_ok=True)
    model_bundle = {
        "clf":     clf,                    # trained SVM
        "le":      le,                     # label encoder
        "classes": list(le.classes_),      # ["Cat", "Dog", ...] for reference
    }
    with open(settings.MODEL_PATH, "wb") as f:
        pickle.dump(model_bundle, f)

    log.info(f"Model saved → {settings.MODEL_PATH}")

    result = {
        "classes":           list(le.classes_),
        "samples_per_class": samples_per_class,
        "total_samples":     len(X),
    }
    if cv_accuracy is not None:
        result["cv_accuracy"] = f"{cv_accuracy:.2%}"

    return result


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 5 — PREDICTION
# ══════════════════════════════════════════════════════════════════════════════

def predict_image(image_bytes: bytes) -> dict:
    """
    Classify a single image using the saved model.

    Parameters:
        image_bytes : raw bytes of the image file

    Returns a dict:
        predicted_class  : winning class name (or "uncertain")
        confidence       : confidence % (0–100)
        uncertain        : True if below CONFIDENCE_THRESHOLD
        all_probabilities: {class_name: probability_%} for all classes
        message          : human-readable summary

    CONFIDENCE GATE EXPLAINED:
        SVM with Platt scaling gives a probability for each class.
        If the highest probability is below 60%, the model is unsure —
        it might be looking at something it wasn't trained on, or the
        image is ambiguous. Instead of guessing wrong, we return "uncertain".

        Example outputs:
            Cat: 91%, Dog: 9%  → confident, return "Cat"
            Cat: 55%, Dog: 45% → uncertain, return "uncertain" + show both bars
    """
    # ── Load the saved model bundle ───────────────────────────────────────────
    if not settings.MODEL_PATH.exists():
        raise FileNotFoundError(
            "No trained model found. Go to Step 2 and click Train first."
        )

    with open(settings.MODEL_PATH, "rb") as f:
        bundle = pickle.load(f)

    clf: SVC          = bundle["clf"]
    le:  LabelEncoder = bundle["le"]

    # ── Preprocess the image ──────────────────────────────────────────────────
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception:
        raise ValueError("Could not read the uploaded image. Try a different file.")

    # ── Extract features ──────────────────────────────────────────────────────
    features = extract_features(img)           # shape: (960,)
    features_2d = features.reshape(1, -1)      # shape: (1, 960) — SVM expects 2D

    # ── Get class probabilities ───────────────────────────────────────────────
    # probs shape: (1, n_classes) — one probability per class
    probs = clf.predict_proba(features_2d)[0]  # shape: (n_classes,)

    # Index of the class with the highest probability
    best_idx    = int(np.argmax(probs))
    confidence  = float(probs[best_idx])
    pred_class  = le.inverse_transform([best_idx])[0]   # e.g., 0 → "Cat"

    # ── Build full probability map (sorted high → low) ────────────────────────
    all_probs = {
        le.inverse_transform([i])[0]: round(float(p) * 100, 1)
        for i, p in sorted(enumerate(probs), key=lambda x: -x[1])
    }

    # ── Confidence gate ───────────────────────────────────────────────────────
    uncertain = confidence < settings.CONFIDENCE_THRESHOLD

    if uncertain:
        message = (
            f"Low confidence ({confidence:.1%}). The image may not closely "
            f"match any of the trained classes. Try adding more diverse training images."
        )
    else:
        message = f"Predicted '{pred_class}' with {confidence:.1%} confidence."

    return {
        "predicted_class":  pred_class if not uncertain else "uncertain",
        "confidence":       round(confidence * 100, 1),
        "uncertain":        uncertain,
        "threshold_pct":    settings.CONFIDENCE_THRESHOLD * 100,
        "all_probabilities": all_probs,
        "message":          message,
    }
