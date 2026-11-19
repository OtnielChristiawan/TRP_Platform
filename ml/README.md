# Bakery Data Platform V4 — Machine Learning Demand Forecasting & Production Planner

**Document Version:** 1.0.0  
**Compliance Standard:** TBP Advanced Data Platform Engineering (F-11, F-12, F-13)  
**Target Business:** Toko Roti Pagi (TRP)

---

## 1. System Architecture

```text
┌──────────────────────────────────────┐
│              MINIO GOLD              │
│       gold_ml_demand_features        │
│    gold_sales_daily & gold_hourly    │
└──────────────────┬───────────────────┘
                   │
                   ▼
┌──────────────────────────────────────┐
│          ML Data Extraction          │
│       DuckDB Engine (Extractor)      │
└──────────────────┬───────────────────┘
                   │
                   ▼
┌──────────────────────────────────────┐
│         Feature Engineering          │
│  Lags, Rolling Avg, Calendar Lags    │
│  (Zero Target Leakage Verification)  │
└──────────────────┬───────────────────┘
                   │
                   ▼
┌──────────────────────────────────────┐
│     Versioned ML Training Dataset    │
│      dset_20261018_20261019_95       │
└──────────────────┬───────────────────┘
                   │
                   ▼
┌──────────────────────────────────────┐
│  Multi-Model Chronological Training  │
│  ├─ Model 1: Naive Lag Baseline      │
│  ├─ Model 2: Ridge Regression (L2)   │
│  └─ Model 3: Random Forest (Depth<=4)│
└──────────────────┬───────────────────┘
                   │
                   ▼
┌──────────────────────────────────────┐
│   Evaluation & Promotion Gate        │
│   Metric: MAE, RMSE, WAPE            │
│   Policy: Must outperform Baseline   │
└──────────────────┬───────────────────┘
                   │
                   ▼
┌──────────────────────────────────────┐
│     Model Registry & Artifacts       │
│  state/ml/model_registry.json        │
└──────────────────┬───────────────────┘
                   │
                   ▼
┌──────────────────────────────────────┐
│       Scheduled Batch Inference      │
│   1. ml_forecast_product_daily (H+1) │
│   2. ml_forecast_next_7_days (Multi) │
│   3. ml_forecast_hourly (9..19 WIB)  │
│   4. ml_production_recommendations   │
└──────────────────┬───────────────────┘
                   │
                   ▼
┌──────────────────────────────────────┐
│            FastAPI Backend           │
│         /api/v1/ml/* Endpoints       │
└──────────────────┬───────────────────┘
                   │
                   ▼
┌──────────────────────────────────────┐
│       React Analytics Dashboard      │
│     Page 5: Demand Forecasting       │
└──────────────────────────────────────┘
```

---

## 2. Model Evaluation & Benchmark Comparison (Holdout Test Set)

All candidate models were strictly trained on Day 1 (`2026-10-18`) and tested on the identical holdout test set on Day 2 (`2026-10-19`) comprising 47 product observations.

| Model Candidate | Algorithm & Hyperparameters | MAE (pcs) | RMSE (pcs) | WAPE (%) | Promotion Decision |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **Model 1: Baseline Naive** | Lag-1 with Historical Menu Mean Fallback | **6.70** | 12.29 | **53.9%** | **PROMOTED (Active)** |
| **Model 2: Ridge Regression** | $\alpha=1.0$, OneHotEncoder + StandardScaler | 7.12 | **10.65** | 57.3% | Candidate (Rejected) |
| **Model 3: Random Forest** | $n=50, \text{depth}=4, \text{leaf}=2$ | 7.37 | 10.62 | 59.3% | Candidate (Rejected) |

**Promotion Rationale:**  
Under the platform governance policy, candidate ML models are only promoted if their MAE strictly outperforms the naive baseline on the holdout test set. Because the Naive Baseline achieved the lowest MAE ($6.70 < 7.12$), the Baseline was promoted to active production with status `provisional` due to the 2-day historical time horizon.

---

## 3. The Four Core Business Outputs

### A. Next-Day Product Demand (`ml_forecast_product_daily`)
- **Grain:** `(forecast_date, branch, menu_key)`
- **Target:** Day $T+1$ (`2026-10-20`)
- **Columns:** `forecast_run_id`, `forecast_date`, `branch`, `menu_key`, `menu_name`, `menu_category`, `predicted_qty`, `model_version`, `status`, `prediction_created_at`.
- **Constraint:** Strictly nonnegative clipping ($\max(0, \hat{y})$).

### B. Seven-Day Demand Forecast (`ml_forecast_next_7_days`)
- **Grain:** `(forecast_date, branch)` for $H \in [1..7]$
- **Projection:** Projections for H+1 through H+7 with empirical weekend uplifts. Zero data leakage from future actuals.

### C. Hourly Demand Forecast (`ml_forecast_hourly`)
- **Grain:** `(forecast_date, forecast_hour, branch)`
- **Constraint:** Bounded to operational bakery hours $[09, 19]$ WIB. Non-operational hours are zero.

### D. Production Preparation Recommendation (`ml_production_recommendations`)
- **Grain:** `(forecast_date, branch, menu_key)`
- **Logic:** Decision support batch baking suggestions:
  $$\text{Suggested Qty} = \lceil \text{Forecast Qty} + Z \times \sigma_{\text{demand}} \rceil$$
- **Operational Disclaimer:**
  *Rekomendasi bersifat decision support awal dan belum memperhitungkan sisa stok fisik di etalase, ketersediaan bahan baku di gudang, kapasitas tray oven, dan umur kadaluarsa produk.*

---

## 4. FastAPI Endpoints (`/api/v1/ml/*`)

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/v1/ml/summary` | Executive KPI overview for next-day forecast |
| `GET` | `/api/v1/ml/forecast/products` | Per-menu demand forecasts (supports `branch`, `limit`, `menu_key`) |
| `GET` | `/api/v1/ml/forecast/weekly` | 7-day multi-step demand trend projections |
| `GET` | `/api/v1/ml/forecast/hourly` | Operational hourly forecast distribution |
| `GET` | `/api/v1/ml/recommendations` | Production batch preparation suggestions with safety buffer |
| `GET` | `/api/v1/ml/model/metrics` | Model evaluation metrics (MAE, RMSE, WAPE) & comparison |
| `GET` | `/api/v1/ml/model/status` | Model health, governance, and readiness status |

---

## 5. Execution Runbook & PowerShell Commands

### Run ML Training Manually
```powershell
& ".venv\Scripts\python.exe" -m ml.training.train_runner
```

### Run Batch Inference Manually
```powershell
& ".venv\Scripts\python.exe" -m ml.inference.batch_inference
```

### Run Unified Scheduler (Weekly Training & Daily Inference)
```powershell
# Single run for both training and inference
& ".venv\Scripts\python.exe" -m ml.scheduler --mode both

# Run continuous background scheduler (Sunday 02:00 WIB train, Daily 03:00 WIB infer)
& ".venv\Scripts\python.exe" -m ml.scheduler --loop
```

### Run Full Test Suite
```powershell
& ".venv\Scripts\pytest.exe" tests/ backend/tests/ -v
```

---

## 6. Academic Compliance Evidence (TBP)

### F-11: Dataset ML, Eksperimen, dan Versioning
- **Data Source:** Extracted directly from committed MinIO Gold Parquet (`gold_ml_demand_features`, `gold_sales_daily`, `gold_sales_hourly`).
- **Versioning:** Datasets versioned deterministically (`dset_20261018_20261019_95`) with SHA256 content hashes.
- **Leakage Prevention:** Features strictly precede target date ($T-1$ lag, rolling historical average). No future actuals.
- **Experiment Tracking:** Multi-model comparison logged in `state/ml/experiments/` storing hyperparameters, train/test windows, and metrics (MAE, RMSE, WAPE).
- **Model Registry:** Model versioning and promotion state maintained in `state/ml/model_registry.json`.

### F-12: Integrasi Inference ML
- **Inference Mode:** Scheduled batch inference engine (`ml/inference/batch_inference.py`) writing versioned immutable Parquet predictions to `state/ml/predictions/` and `s3://bakery-gold/ml/predictions/`.
- **Provenance Metadata:** Every prediction row includes `forecast_run_id`, `model_version`, `model_name`, `status`, and `prediction_created_at`.
- **Safety & Error Handling:** Validated with unit tests for insufficient data, nonnegative bounds, and fallback heuristics.

### F-13: Dashboard ML Integration
- **Frontend Integration:** Added Page 5 **Demand Forecasting** (`/forecast`) with 6 complete sections:
  1. Section A: Executive Forecast KPIs
  2. Section B: Seven-Day Demand Trend Line Chart
  3. Section C: Product Demand Forecast Table (with search and category filter)
  4. Section D: Hourly Demand Forecast Bar Chart (operating hours 9..19)
  5. Section E: Production Preparation Table with buffer rationale and operational disclaimer
  6. Section F: Model Performance & Governance Audit Comparison Table
- **Dynamic API Fetch:** Reads live from FastAPI backend with TanStack Query.
