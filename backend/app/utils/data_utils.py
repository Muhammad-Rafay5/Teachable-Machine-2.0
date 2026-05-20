"""
data_utils.py  —  File system operations (no ML here)
══════════════════════════════════════════════════════
WHY THIS FILE EXISTS:
  Keeps all "disk I/O" logic in one place, completely separate from ML code.
  Every function here is simple, testable, and has ONE job.

WHAT IT DOES:
  • save_images()      → saves uploaded images into dataset/<class_name>/
  • get_class_info()   → reads dataset folder, counts images per class
  • validate_dataset() → checks training prerequisites, returns readable errors
  • sanitize_name()    → makes class names safe to use as folder names

WHAT IT DOES NOT DO:
  • No machine learning
  • No FastAPI routing
  • No HTTP requests
"""

import uuid
import io
import logging
from pathlib import Path
from PIL import Image

from app.config import settings

log = logging.getLogger(__name__)


# ── Name Sanitizer ─────────────────────────────────────────────────────────────

def sanitize_class_name(name: str) -> str:
    """
    Convert a user-typed class name into a safe folder name.

    Example:
        "My Cat!!"  →  "My Cat"
        "dog/puppy" →  "dogpuppy"
        "   "       →  raises ValueError

    Only allows: letters, digits, spaces, hyphens, underscores.
    """
    safe = "".join(c for c in name.strip() if c.isalnum() or c in " -_")
    safe = safe.strip()
    if not safe:
        raise ValueError(f"Class name '{name}' is invalid or empty after sanitization.")
    return safe


# ── Image Saver ────────────────────────────────────────────────────────────────

def save_images(class_name: str, image_bytes_list: list[bytes]) -> dict:
    """
    Save a list of raw image bytes into dataset/<class_name>/.

    Parameters:
        class_name       : the category label (will be sanitized)
        image_bytes_list : list of raw bytes from uploaded files

    Returns a dict with:
        class_name   : sanitized folder name used
        saved        : how many were saved successfully
        skipped      : how many were rejected (corrupt, wrong format)
        total        : total images now in this class folder

    HOW UUID FILENAMES WORK:
        uuid.uuid4().hex generates a random 32-character hex string like:
        "3f2504e04f8911d39a0c0305e82c3301"
        This guarantees no two files ever overwrite each other, even when
        multiple users upload at the same time.
    """
    safe_name  = sanitize_class_name(class_name)
    class_dir  = settings.DATASET_DIR / safe_name
    class_dir.mkdir(parents=True, exist_ok=True)   # create folder if missing

    saved   = 0
    skipped = 0

    for raw_bytes in image_bytes_list:
        # Step 1: Verify it's actually a valid image before saving
        try:
            img = Image.open(io.BytesIO(raw_bytes))
            img.verify()   # raises if the file is corrupt or not an image
        except Exception as e:
            log.warning(f"Skipping corrupt/invalid image: {e}")
            skipped += 1
            continue

        # Step 2: Save with a random UUID filename (.jpg extension always)
        filename  = f"{uuid.uuid4().hex}.jpg"
        save_path = class_dir / filename

        # Re-open (verify() moves the file pointer, can't reuse the same object)
        # Convert to RGB so we never accidentally save RGBA or grayscale
        img = Image.open(io.BytesIO(raw_bytes)).convert("RGB")
        img.save(save_path, format="JPEG", quality=95)

        saved += 1
        log.info(f"Saved: {save_path.name} → {safe_name}/")

    # Count total images now in this class folder
    total = len([
        p for p in class_dir.iterdir()
        if p.suffix.lower() in settings.ALLOWED_EXTENSIONS
    ])

    return {
        "class_name": safe_name,
        "saved":      saved,
        "skipped":    skipped,
        "total":      total,
    }


# ── Dataset Inspector ──────────────────────────────────────────────────────────

def get_class_info() -> dict:
    """
    Scan the dataset folder and return info about all classes.

    Returns:
        {
          "classes": ["Cat", "Dog"],          # sorted alphabetically
          "counts":  {"Cat": 12, "Dog": 8},   # image count per class
          "total":   20                         # grand total
        }

    This is called by GET /classes and is also used internally by validate_dataset().
    """
    dataset_dir = settings.DATASET_DIR

    if not dataset_dir.exists():
        return {"classes": [], "counts": {}, "total": 0}

    counts = {}
    for folder in sorted(dataset_dir.iterdir()):
        if not folder.is_dir():
            continue
        # Only count files with allowed image extensions
        n_images = len([
            p for p in folder.iterdir()
            if p.suffix.lower() in settings.ALLOWED_EXTENSIONS
        ])
        if n_images > 0:   # ignore empty folders
            counts[folder.name] = n_images

    return {
        "classes": list(counts.keys()),
        "counts":  counts,
        "total":   sum(counts.values()),
    }


# ── Training Prerequisites Validator ──────────────────────────────────────────

def validate_dataset() -> tuple[bool, str]:
    """
    Check if the dataset is ready for training.

    Returns:
        (True,  "")          → all good, proceed with training
        (False, "message")   → not ready, message explains why

    WHY CHECK BEFORE TRAINING:
        If we skip these checks and just call clf.fit(), scikit-learn raises
        cryptic internal errors. Catching them here gives the user a
        clear, actionable message instead of a stack trace.

    Checks performed:
        1. Dataset folder must exist
        2. At least MIN_CLASSES (2) class folders must exist
        3. Every class must have at least MIN_IMAGES_PER_CLASS (5) images
    """
    info = get_class_info()

    # Check 1: Do we have enough classes?
    n_classes = len(info["classes"])
    if n_classes < settings.MIN_CLASSES:
        return False, (
            f"Need at least {settings.MIN_CLASSES} classes to train. "
            f"You have {n_classes}. Add images for more classes."
        )

    # Check 2: Does every class have enough images?
    under_threshold = {
        cls: cnt
        for cls, cnt in info["counts"].items()
        if cnt < settings.MIN_IMAGES_PER_CLASS
    }
    if under_threshold:
        details = ", ".join(
            f"'{cls}' has {cnt}" for cls, cnt in under_threshold.items()
        )
        return False, (
            f"Each class needs at least {settings.MIN_IMAGES_PER_CLASS} images. "
            f"These are below the limit: {details}."
        )

    return True, ""


# ── Dataset Cleaner ────────────────────────────────────────────────────────────

def reset_dataset() -> None:
    """
    Delete all images and class folders, then recreate the empty dataset dir.
    Also deletes the saved model if it exists.
    Used by DELETE /reset.
    """
    import shutil

    if settings.DATASET_DIR.exists():
        shutil.rmtree(settings.DATASET_DIR)
    settings.DATASET_DIR.mkdir(parents=True, exist_ok=True)

    if settings.MODEL_PATH.exists():
        settings.MODEL_PATH.unlink()

    log.info("Dataset and model have been reset.")
