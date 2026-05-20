# Teachable Machine Clone
### FastAPI + Streamlit | MobileNetV3 + SVM | No Docker Required

---

## Project Structure & What Each File Does

```
teachable-machine-clone/
├── backend/
│   ├── app/
│   │   ├── __init__.py       Makes app/ a Python package (never edit)
│   │   ├── main.py           HTTP routes ONLY — thin layer, no ML
│   │   ├── config.py         ALL settings in one place (paths, sizes, thresholds)
│   │   └── utils/
│   │       ├── __init__.py   Makes utils/ a Python package (never edit)
│   │       ├── data_utils.py File system ops: save images, scan folders, validate
│   │       └── ml_utils.py   ALL ML: feature extraction, training, prediction
│   ├── dataset/              Auto-created — one subfolder per class
│   ├── models/               model.pkl saved here after training
│   └── requirements.txt
├── frontend/
│   ├── app.py                Streamlit UI — HTTP calls only, zero ML
│   └── requirements.txt
└── README.md
```

---

## Setup & Running (No Docker)

### Backend
```bash
cd teachable-machine-clone/backend

python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate

pip install -r requirements.txt

# MUST run from inside backend/ so relative paths resolve
uvicorn app.main:app --reload --port 8000
```

Visit http://localhost:8000/docs for interactive API docs.

### Frontend (new terminal)
```bash
cd teachable-machine-clone/frontend
pip install -r requirements.txt
streamlit run app.py
```

Opens at http://localhost:8501

---

## Workflow

| Step | You do | What happens |
|------|--------|-------------|
| 1 | Type "Cat", upload images | POST /upload-sample saves to dataset/Cat/ with UUID filenames |
| 2 | Type "Dog", upload images | Same for dataset/Dog/ |
| 3 | Click Train Model | POST /train extracts MobileNetV3 features, trains SVM, saves model.pkl |
| 4 | Upload a test image | POST /predict returns class + confidence % |

---

## File Explanations

### config.py
Single source of truth. IMAGE_SIZE, paths, thresholds all here.
Change CONFIDENCE_THRESHOLD here and it updates across the whole app.

### data_utils.py (no ML)
- sanitize_class_name() — safe folder names
- save_images()         — UUID filenames, validates images before saving
- get_class_info()      — scans dataset/, counts per class
- validate_dataset()    — returns (True,"") or (False, "clear error message")
- reset_dataset()       — wipes everything

### ml_utils.py (all ML)
- build_extractor()    — loads MobileNetV3 ONCE at startup (frozen)
- TRANSFORM            — module-level constant, identical for train+predict
- extract_features()   — PIL Image -> 960-dim L2-normalized numpy vector
- train_model()        — feature extraction loop + SVM training + save pkl
- predict_image()      — load pkl + extract features + SVM proba + confidence gate

### main.py (routes only)
Five endpoints, each 5-10 lines. All real work delegated to utils:
  GET  /            health check
  GET  /classes     list classes + counts
  POST /upload-sample  save images
  POST /train          train model
  POST /predict        classify image
  DELETE /reset        wipe everything

### frontend/app.py (UI only)
- call_api() helper wraps all requests with error handling
- refresh_classes() syncs session_state from backend
- Step 3 (predict) hidden until session_state.trained = True
- Sends files as multipart/form-data (same as browser file inputs)

---

## ML Architecture

```
Your image (any size)
      |
  Resize(256) -> CenterCrop(224) -> ToTensor() -> Normalize(ImageNet stats)
      |
  MobileNetV3-Large (FROZEN — never updates)
      |
  960-dimensional feature vector
      |
  L2 Normalize
      |
  SVM with RBF kernel (this is what trains on your images)
      |
  Probability per class (Platt scaling)
      |
  Confidence gate: < 60% -> return "uncertain"
```

Why SVM over LogisticRegression:
- RBF kernel handles non-linear class boundaries
- Maximum-margin principle: robust on small datasets (10-50 images/class)
- probability=True enables well-calibrated confidence scores

Why confidence gate:
- Without it the model always picks something, even at 52%
- With it: uncertain means "add more training images" not "wrong answer"

---

## Common Errors

| Error | Fix |
|-------|-----|
| Backend offline in sidebar | cd backend && uvicorn app.main:app --reload |
| ModuleNotFoundError: app | You must run uvicorn from inside the backend/ folder |
| Need at least 2 classes | Upload images for a second class |
| Only has N images | Add more images to that class (need >= 5) |
| uncertain prediction | Add more diverse training images |
| CV accuracy < 75% | Classes too visually similar or too few images |

---

## Tips for High Accuracy

- 20+ images per class beats 5 every time
- Vary backgrounds, lighting, angles — model should learn the object not the setting
- Add a "None" or "Other" class to catch images that dont match anything
- CV accuracy below 80%: classes may be too visually similar
