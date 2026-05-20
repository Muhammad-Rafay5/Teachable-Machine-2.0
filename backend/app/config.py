"""
config.py  —  Single source of truth for all settings
══════════════════════════════════════════════════════
WHY THIS FILE EXISTS:
  Instead of scattering "224", "../dataset", "0.60" across multiple files,
  every configurable value lives here. Change one line here → whole app updates.

HOW TO USE:
  from app.config import settings
  settings.DATASET_DIR   →  Path object pointing to the dataset folder
  settings.IMAGE_SIZE    →  (224, 224) — the size MobileNetV3 expects
"""

from pathlib import Path


class Settings:
    # ── Directory Paths ────────────────────────────────────────────────────────
    # Path(__file__) is this file: backend/app/config.py
    # .parent       → backend/app/
    # .parent.parent → backend/
    BASE_DIR: Path = Path(__file__).parent.parent

    DATASET_DIR: Path = BASE_DIR / "dataset"   # where class image folders live
    MODEL_DIR:   Path = BASE_DIR / "models"    # where model.pkl is saved
    MODEL_PATH:  Path = MODEL_DIR / "model.pkl"

    # ── Image Preprocessing ────────────────────────────────────────────────────
    # MobileNetV3 was trained on 224×224 images → NEVER change this
    IMAGE_SIZE: tuple = (224, 224)

    # ImageNet statistics — used to normalize pixel values
    # These exact numbers match what MobileNetV3 was trained with
    IMAGENET_MEAN: list = [0.485, 0.456, 0.406]
    IMAGENET_STD:  list = [0.229, 0.224, 0.225]

    # ── Training Guards ────────────────────────────────────────────────────────
    MIN_CLASSES:           int   = 2    # must have at least 2 different classes
    MIN_IMAGES_PER_CLASS:  int   = 5    # minimum images to train reliably

    # ── Confidence Threshold ───────────────────────────────────────────────────
    # Predictions below this % are returned as "uncertain"
    # This PREVENTS the model from confidently predicting the wrong class
    CONFIDENCE_THRESHOLD: float = 0.60   # 60%

    # ── SVM Hyperparameters ────────────────────────────────────────────────────
    # C=10   → moderate regularization (good for transfer learning features)
    # gamma  → 'scale' means 1 / (n_features × X.var()) — auto-calibrated
    SVM_C:     float = 10.0
    SVM_GAMMA: str   = "scale"

    # ── Allowed Image Extensions ───────────────────────────────────────────────
    ALLOWED_EXTENSIONS: set = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


# Single shared instance — import this everywhere
settings = Settings()
