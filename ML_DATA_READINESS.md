# Bakery Data Platform V4: Machine Learning Data Readiness Audit

**Document Version:** 1.0.0  
**Audit Date:** 2026-11-19  
**Auditor:** Senior ML Engineer & Data Architect  
**Subject:** Feasibility and Readiness Assessment for Demand Forecasting & Production Planning (TBP Compliance: F-11, F-12, F-13)

---

## 1. Executive Summary

This audit assesses the historical transaction data available in the **MinIO Gold Data Lake** (`s3://bakery-gold/`) to establish the statistical feasibility, risks, and boundary conditions for Machine Learning demand forecasting at **Toko Roti Pagi (TRP)**.

**Verdict: PROVISIONAL ML READINESS (FEASIBLE WITH BOUNDED POLICIES)**
- **Data Status:** The pipeline is functioning end-to-end (Bronze -> Silver -> Gold). The committed Gold layer currently captures **2 calendar days** (`2026-10-18` Sunday to `2026-10-19` Monday).
- **Feasibility:** Basic tabular models (Baseline Naive, Ridge Regression, and Random Forest) can be trained across pooled menu observations, but long-term seasonal forecasting (e.g. 7-day cyclical demand or yearly trends) is mathematically constrained by sample horizon.
- **Policy Enforcement:** All inference outputs generated on this dataset must be flagged with `status: provisional` or `insufficient_data` for low-observation items, with explicit nonnegative bounds and transparent error handling. Model promotion strictly requires outperforming the naive baseline.

---

## 2. Gold Dataset Inventory & Verification

The following analytical Gold data marts were audited directly from MinIO Parquet files:

| Dataset Name | MinIO Object Path | Grain | Record Count |
| :--- | :--- | :--- | :--- |
| `gold_sales_daily` | `s3://bakery-gold/gold_sales_daily/` | `(sales_date, branch)` | 2 rows |
| `gold_sales_hourly` | `s3://bakery-gold/gold_sales_hourly/` | `(sales_date, sales_hour, branch)` | 20 rows |
| `gold_menu_performance_daily` | `s3://bakery-gold/gold_menu_performance_daily/` | `(sales_date, branch, menu_key)` | 95 rows |
| `gold_category_performance_daily`| `s3://bakery-gold/gold_category_performance_daily/`| `(sales_date, branch, menu_category)` | 6 rows |
| `gold_payment_daily` | `s3://bakery-gold/gold_payment_daily/` | `(sales_date, branch, payment_method)` | 4 rows |
| `gold_ml_demand_features` | `s3://bakery-gold/gold_ml_demand_features/` | `(sales_date, branch, menu_key)` | 95 rows |

---

## 3. Data Profile & Temporal Analysis

### 3.1 Date Range & Volume
- **Earliest Sales Date:** `2026-10-18` (Sunday)
- **Latest Sales Date:** `2026-10-19` (Monday)
- **Calendar Days Covered:** 2 days
- **Total Bills (Transactions):** 285 valid bills
- **Total Item Rows:** 1,083 line items
- **Total Quantity Sold:** 1,194 units
- **Total Net Sales:** Rp 21,807,200
- **Zero-Price Items:** 150 items (predominantly packaging bags, paper boxes, or zero-cost complimentary condiments).

### 3.2 Operational Hours Profile
Transactions occur exclusively between **09:00 and 19:00 WIB** (11 operating hours). No sales exist before 09:00 or after 19:59.
- **Lunch Peak (10:00 - 12:59):** Accounts for 121 bills and 576 units sold (48.2% of daily volume).
- **Afternoon Snack Peak (15:00 - 16:59):** Accounts for 60 bills and 258 units sold (21.6% of daily volume).
- **Opening (09:00 - 09:59) & Closing (18:00 - 19:59):** Lower volume ramp-up and wind-down.
- **Rule for Hourly Model:** Predictions are restricted to operational window $[09, 19]$. Non-operational hours are deterministically assigned 0 qty without model hallucination.

### 3.3 Menu & Category Distribution
- **Total Unique Menu SKUs:** 52 items
- **Items Observed on Both Days:** 43 items (82.7%)
- **Items Observed on Only 1 Day:** 9 items (17.3%)
- **Category Breakdown:**
  1. **PASTRY:** 33 menus, 932 units sold (78.0% qty), Rp 14,411,200 (66.08% revenue).
  2. **BEVERAGE:** 15 menus, 233 units sold (19.5% qty), Rp 6,470,000 (29.67% revenue).
  3. **DESSERT:** 4 menus, 29 units sold (2.4% qty), Rp 926,000 (4.25% revenue).

---

## 4. Machine Learning Feasibility & Risk Assessment

### 4.1 Identified Risks & Mitigations

| Risk | Impact | Mitigation Strategy |
| :--- | :--- | :--- |
| **Short Calendar Horizon (2 days)** | Weekly seasonality ($Lag_7$, Day-of-Week cycle) cannot be fully populated. | 1. Use pooled global tabular model across all menus.<br>2. Fill unobserved lags with valid default values.<br>3. Mark model outputs as `provisional`. |
| **Sparse / Intermittent Demand** | Infrequently ordered items have high variance and zero sales. | Separate high-velocity items from low-velocity items. Use Nonnegative Clipping ($\hat{y} \ge 0$). |
| **Target Data Leakage** | Future sales leaking into lag or rolling features. | Window functions strictly precede target date (`rowsBetween(-7, -1)` or `lag(1)`). Train/test split is strictly chronological. |
| **Overfitting on Complex Models** | Deep learning / deep trees memorizing noise. | Limit Random Forest `max_depth <= 4`, `min_samples_leaf >= 2`. Compare strictly with Baseline Naive. |
| **Divergence between SKU and Total** | Sum of menu forecasts $\ne$ total daily forecast. | Acknowledge reconciliation delta in status metadata. |

---

## 5. Decision & Operational Policies

1. **Model Governance Policy:** A model is eligible for production inference ONLY if its evaluation metric on the holdout test set achieves a **lower MAE / WAPE than the Naive Baseline**. Otherwise, fallback to the Naive Baseline.
2. **Production Recommendation Policy:** Recommended prepare quantity uses:
   $$\text{Suggested Qty} = \lceil \text{Predicted Qty} + Z \times \sigma_{\text{demand}} \rceil$$
   with an explicit operational disclaimer that current data lacks raw material inventory, shelf-life spoilage rates, and kitchen capacity constraints.
3. **Data Completeness Gate:** If minimum observations for a menu $< 1$, forecast status is set to `insufficient_data` and recommendation is marked `unavailable`.
