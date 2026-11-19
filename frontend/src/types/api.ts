export interface HealthResponse {
  status: string;
  app_name: string;
  version: string;
  environment: string;
  timestamp: string;
}

export interface FreshnessResponse {
  batch_id?: string;
  published_at?: string;
  latest_transaction_date?: string;
  last_refresh_at: string;
  status: string;
  marts_status: Record<string, any>;
}

export interface FilterOptionsResponse {
  branches: string[];
  min_date: string | null;
  max_date: string | null;
  categories: string[];
  payment_methods: string[];
}

export interface SummaryKPI {
  total_net_sales: number;
  total_gross_sales: number;
  total_discount: number;
  total_bills: number;
  total_qty_sold: number;
  total_item_rows: number;
  average_order_value: number;
  zero_price_item_count: number;
  last_updated_at?: string | null;
  previous_period_net_sales?: number | null;
  sales_growth_pct?: number | null;
  bills_growth_pct?: number | null;
}

export interface DailySalesItem {
  sales_date: string;
  branch: string;
  total_bills: number;
  total_item_rows: number;
  total_qty_sold: number;
  gross_sales: number;
  total_discount: number;
  net_sales: number;
  average_order_value: number;
  zero_price_item_count: number;
}

export interface HourlySalesItem {
  sales_hour: number;
  total_bills: number;
  total_item_rows: number;
  total_qty_sold: number;
  gross_sales: number;
  net_sales: number;
  average_order_value: number;
}

export interface TopMenuItem {
  rank: number;
  menu_key: string;
  menu_name: string;
  menu_category?: string | null;
  menu_category_detail?: string | null;
  qty_sold: number;
  total_bills: number;
  gross_sales: number;
  net_sales: number;
  zero_price_qty: number;
  is_master_matched: boolean;
  master_match_status: string;
}

export interface CategoryPerformanceItem {
  menu_category: string;
  qty_sold: number;
  total_bills: number;
  total_item_rows: number;
  gross_sales: number;
  net_sales: number;
  sales_contribution_pct: number;
}

export interface PaymentSummaryItem {
  payment_method: string;
  total_bills: number;
  net_sales: number;
  payment_contribution_pct: number;
}

export interface GlobalFilterState {
  startDate: string;
  endDate: string;
  branch: string;
}


// -----------------------------------------------------------------------------
// ML Demand Forecasting Types (F-13 Compliance)
// -----------------------------------------------------------------------------
export interface MLSummaryKPI {
  predicted_total_items_tomorrow: number;
  menus_forecasted_count: number;
  active_model_name: string;
  active_model_version: string;
  model_status: string;
  forecast_target_date: string | null;
  last_forecast_created_at: string | null;
  top_demanded_menu: string | null;
}

export interface MLProductForecastItem {
  forecast_run_id: string;
  forecast_date: string;
  branch: string;
  menu_key: string;
  menu_name: string;
  menu_category: string;
  predicted_qty: number;
  model_version: string;
  model_name: string;
  status: string;
  prediction_created_at: string;
}

export interface MLSevenDayItem {
  forecast_run_id: string;
  forecast_date: string;
  branch: string;
  predicted_total_qty: number;
  horizon_step: number;
  model_version: string;
  model_name: string;
  forecast_status: string;
  prediction_created_at: string;
}

export interface MLHourlyForecastItem {
  forecast_run_id: string;
  forecast_date: string;
  forecast_hour: number;
  branch: string;
  predicted_qty: number;
  model_version: string;
  status: string;
  prediction_created_at: string;
}

export interface MLProductionRecommendationItem {
  forecast_run_id: string;
  menu_key: string;
  menu_name: string;
  menu_category: string;
  branch: string;
  forecast_date: string;
  forecast_qty: number;
  suggested_prepare_qty: number;
  recommendation_reason: string;
  model_version: string;
  policy_version: string;
  recommendation_status: string;
  disclaimer: string;
  prediction_created_at: string;
}

export interface MLModelMetricsResponse {
  active_model: string;
  active_version: string;
  active_run_id: string;
  status: string;
  last_promoted_at: string | null;
  promotion_reason: string | null;
  latest_metrics: {
    mae: number;
    rmse: number;
    wape: number;
    sample_count?: number;
  };
  all_models_evaluated?: Record<string, any>;
}

export interface MLModelStatusResponse {
  status: string;
  has_active_model: boolean;
  model_name: string | null;
  model_version: string | null;
  evaluation_status: string | null;
  data_readiness_status: string;
  message: string;
}

export interface AlertEvent {
  alert_id: string;
  rule_id: string;
  rule_name: string;
  status: "FIRING" | "RESOLVED";
  severity: "INFO" | "WARNING" | "CRITICAL";
  owner: string;
  threshold?: any;
  current_value?: any;
  message: string;
  runbook?: string;
  triggered_at: string;
  resolved_at?: string | null;
  resolution_message?: string | null;
  details?: Record<string, any>;
}

export interface SystemHealthMetrics {
  status: string;
  role_caller: string;
  platform: {
    system: string;
    release: string;
    python: string;
  };
  process_metrics: {
    pid: number;
    memory_used_mb: number | null;
    cpu_percent: number | null;
  };
  system_metrics: {
    total_ram_gb: number | null;
    available_ram_gb: number | null;
    ram_percent: number | null;
  };
}
