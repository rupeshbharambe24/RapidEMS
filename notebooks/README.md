# 🚑 AI Emergency Response System — Training Notebooks

Five self-contained Jupyter notebooks that train every ML/DL model needed for the
**AI-Enabled Smart Emergency Response & Ambulance Coordination System**.

Each notebook generates its own synthetic data, runs full EDA with visualisations,
benchmarks 4–6 candidate models, picks the best, and saves it to disk. **No external
dataset required.**

---

## 📓 The notebooks

| # | File | Model | Type | Target |
|---|------|-------|------|--------|
| 1 | `01_severity_classifier.ipynb`     | Emergency Severity Classifier  | 5-class classification | Accuracy ≥ 0.95, Macro F1 ≥ 0.93 |
| 2 | `02_eta_predictor.ipynb`           | Ambulance ETA Predictor        | Regression             | R² ≥ 0.95, MAE ≤ 30s |
| 3 | `03_hospital_recommender.ipynb`    | Hospital Recommender           | Regression + Ranking   | R² ≥ 0.95, Top-1 acc ≥ 0.92 |
| 4 | `04_traffic_predictor.ipynb`       | Traffic Congestion Predictor   | Regression             | R² ≥ 0.95, MAE ≤ 0.05 |
| 5 | `05_hotspot_forecaster_lstm.ipynb` | LSTM Hotspot Forecaster        | Time-series            | R² ≥ 0.92, MAE ≤ 0.4 incidents/hr |

**Notebooks 1–4 take ~2–5 min each on CPU. Notebook 5 (LSTM) takes ~10–20 min on CPU, ~3–5 min on GPU.**

---

## 🚀 How to run

### 1. Set up the environment

```bash
python -m venv venv
source venv/bin/activate              # Windows: venv\Scripts\activate

pip install jupyter numpy pandas scikit-learn xgboost lightgbm catboost \
            imbalanced-learn shap matplotlib seaborn joblib statsmodels \
            tensorflow scipy
```

### 2. Launch Jupyter

```bash
jupyter notebook
# or
jupyter lab
```

### 3. Run any notebook end-to-end

Open one of the `.ipynb` files and choose **`Kernel → Restart & Run All`**.

You can run them in any order — each is fully self-contained.

### 4. Find your trained models

Each notebook creates two folders next to itself:

```
models/      ← .pkl / .keras model files (drop these into your FastAPI backend's ai/models/)
reports/     ← .json metric reports
```

---

## 🏗️ What's inside each notebook

Every notebook follows the same disciplined structure:

1. **Title + performance targets** — what success looks like
2. **Setup & imports**
3. **Synthetic data generation** — rule-based simulation with realistic noise
4. **Exploratory Data Analysis** — 5–7 visualisations including:
   - Target distributions
   - Feature distributions by class/group
   - Correlation heatmaps
   - Time-of-day / seasonality patterns where relevant
5. **Preprocessing** — split, scale, balance (SMOTE for imbalanced classes)
6. **Model bake-off** — 4–6 candidates compared on the same test set:
   - Linear baseline (sanity check)
   - Random Forest
   - **XGBoost** (tuned)
   - **LightGBM** (tuned)
   - **CatBoost** (tuned)
   - Voting / averaging ensemble
7. **Leaderboard** — sortable table + bar-chart visual
8. **Deep-dive on the winner** — confusion matrix / predicted-vs-actual / residuals / per-class metrics / ROC
9. **Feature importance + SHAP** — explainability
10. **Smoke-test predictions** — runs the model on 2–3 hand-built scenarios
11. **Persist artefacts** — saves model + scaler + feature columns + JSON report
12. **Summary table** — target vs achieved metrics

---

## 🎯 Why the 95 %+ accuracy claim is realistic

The data is **synthetic and rule-driven** — labels are generated from clear physical
or clinical rules with controlled noise (5 % label noise on classification, 6–8 %
log-normal noise on regressions, irreducible Poisson noise on the time-series).

Because the underlying signal is strong, well-tuned gradient boosting hits the
targets on the first run. Notebook 5 (LSTM) is the one exception — the Poisson
noise floor caps R² at ≈ 0.93, so the target there is 0.92 (≈ at the floor).

**Caveat for production:** these accuracies will *not* transfer to real EMS data
without retraining. Treat the synthetic results as proof that the architecture
and training pipeline work — then swap in real CSVs (same column names) and retrain.

---

## 🧰 Best-of-class model choices, by notebook

| Notebook | Winning architecture (typical) | Why |
|----------|-------------------------------|-----|
| 1. Severity   | XGBoost/LightGBM voting ensemble + **isotonic calibration** | Multi-class with imbalance; ensemble for variance, calibration so confidence % is reliable for the dispatcher UI |
| 2. ETA        | Average of XGBoost + LightGBM + CatBoost | Heavy-tailed regression; averaging boosters reduces variance |
| 3. Hospital   | XGBoost regression, evaluated as ranker | Non-linear interactions between specialty/beds/distance |
| 4. Traffic    | LightGBM + cyclical sin/cos features | Native categorical handling, periodicity-friendly |
| 5. Hotspot    | Stacked LSTM with dropout + Huber loss | Time-series with daily/weekly seasonality and Poisson noise |

---

## 📦 What gets saved (after you run all 5)

```
models/
├── severity_classifier.pkl
├── severity_scaler.pkl
├── severity_feature_cols.pkl
├── eta_xgb.pkl
├── eta_lgbm.pkl
├── eta_catboost.pkl
├── eta_scaler.pkl
├── eta_feature_cols.pkl
├── hospital_recommender.pkl
├── hospital_scaler.pkl
├── hospital_feature_cols.pkl
├── traffic_predictor.pkl
├── traffic_scaler.pkl
├── traffic_feature_cols.pkl
├── hotspot_lstm.keras
└── hotspot_count_scaler.pkl

reports/
├── severity_classifier_report.json
├── eta_predictor_report.json
├── hospital_recommender_report.json
├── traffic_predictor_report.json
└── hotspot_forecaster_report.json
```

Drop `models/` into the FastAPI backend's `ai/models/` directory and wire up the
inference layer per Section 7 of the system spec. The backend just needs:

```python
import joblib, tensorflow as tf
sev_model = joblib.load("ai/models/severity_classifier.pkl")
sev_scaler = joblib.load("ai/models/severity_scaler.pkl")
hotspot_model = tf.keras.models.load_model("ai/models/hotspot_lstm.keras")
# ... etc
```

---

## 🐛 Troubleshooting

| Symptom | Fix |
|---------|-----|
| `ModuleNotFoundError: catboost` | `pip install catboost` |
| `tensorflow` import fails on Apple Silicon | `pip install tensorflow-macos tensorflow-metal` |
| LSTM training is too slow | Reduce `N_DAYS = 730` to `N_DAYS = 365` in cell 2 of notebook 5 |
| OOM when running SMOTE in notebook 1 | Drop `N_SAMPLES` from 50 000 to 25 000 in cell 2 |
| SHAP plot doesn't render | The notebooks already wrap SHAP in `try/except`; results are still saved |

---

Built for the **AI-Enabled Smart Emergency Response & Ambulance Coordination System** hackathon project.
