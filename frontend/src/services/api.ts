import type {
  AlertEvent,
  CategoryPerformanceItem,
  DailySalesItem,
  FilterOptionsResponse,
  FreshnessResponse,
  GlobalFilterState,
  HourlySalesItem,
  PaymentSummaryItem,
  SummaryKPI,
  SystemHealthMetrics,
  TopMenuItem,
} from "../types/api";

const API_BASE = "/api/v1";

export type UserRole = "viewer" | "operator" | "admin";

const ROLE_KEYS: Record<UserRole, string> = {
  viewer: "trp-viewer-key-2026",
  operator: "trp-operator-key-2026",
  admin: "trp-admin-key-2026",
};

export function getActiveRole(): UserRole {
  return (localStorage.getItem("bakery_user_role") as UserRole) || "operator";
}

export function setActiveRole(role: UserRole) {
  localStorage.setItem("bakery_user_role", role);
  window.dispatchEvent(new Event("bakery_role_changed"));
}

export function getActiveApiKey(): string {
  const role = getActiveRole();
  return ROLE_KEYS[role] || ROLE_KEYS.viewer;
}

function buildQueryString(params: Record<string, string | number | undefined>): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      query.append(key, String(value));
    }
  }
  const str = query.toString();
  return str ? `?${str}` : "";
}

async function request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const headers = {
    "X-API-Key": getActiveApiKey(),
    "Content-Type": "application/json",
    ...(options.headers || {}),
  };

  const res = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers,
  });

  if (!res.ok) {
    const errorBody = await res.json().catch(() => ({}));
    throw new Error(errorBody.detail || `Request failed with status ${res.status}`);
  }
  return res.json();
}

export const api = {
  getFreshness(): Promise<FreshnessResponse> {
    return request<FreshnessResponse>("/data/freshness");
  },

  getFilters(): Promise<FilterOptionsResponse> {
    return request<FilterOptionsResponse>("/filters");
  },

  getSummary(filters: GlobalFilterState): Promise<SummaryKPI> {
    const qs = buildQueryString({
      start_date: filters.startDate,
      end_date: filters.endDate,
      branch: filters.branch,
    });
    return request<SummaryKPI>(`/dashboard/summary${qs}`);
  },

  getDailySales(filters: GlobalFilterState): Promise<DailySalesItem[]> {
    const qs = buildQueryString({
      start_date: filters.startDate,
      end_date: filters.endDate,
      branch: filters.branch,
    });
    return request<DailySalesItem[]>(`/sales/daily${qs}`);
  },

  getHourlySales(filters: GlobalFilterState): Promise<HourlySalesItem[]> {
    const qs = buildQueryString({
      start_date: filters.startDate,
      end_date: filters.endDate,
      branch: filters.branch,
    });
    return request<HourlySalesItem[]>(`/sales/hourly${qs}`);
  },

  getTopMenus(
    filters: GlobalFilterState,
    limit: number = 10,
    sortBy: "quantity" | "sales" = "quantity",
    category?: string
  ): Promise<TopMenuItem[]> {
    const qs = buildQueryString({
      start_date: filters.startDate,
      end_date: filters.endDate,
      branch: filters.branch,
      limit,
      sort_by: sortBy,
      category,
    });
    return request<TopMenuItem[]>(`/menus/top${qs}`);
  },

  getCategoryPerformance(filters: GlobalFilterState): Promise<CategoryPerformanceItem[]> {
    const qs = buildQueryString({
      start_date: filters.startDate,
      end_date: filters.endDate,
      branch: filters.branch,
    });
    return request<CategoryPerformanceItem[]>(`/categories/performance${qs}`);
  },

  getPaymentSummary(filters: GlobalFilterState): Promise<PaymentSummaryItem[]> {
    const qs = buildQueryString({
      start_date: filters.startDate,
      end_date: filters.endDate,
      branch: filters.branch,
    });
    return request<PaymentSummaryItem[]>(`/payments/summary${qs}`);
  },

  // ---------------------------------------------------------------------------
  // ML Demand Forecasting Endpoints
  // ---------------------------------------------------------------------------
  getMLSummary(branch?: string) {
    const qs = buildQueryString({ branch });
    return request<import("../types/api").MLSummaryKPI>(`/ml/summary${qs}`);
  },

  getMLProductForecasts(branch?: string, limit: number = 100) {
    const qs = buildQueryString({ branch, limit });
    return request<import("../types/api").MLProductForecastItem[]>(`/ml/forecast/products${qs}`);
  },

  getMLWeeklyForecast(branch?: string) {
    const qs = buildQueryString({ branch });
    return request<import("../types/api").MLSevenDayItem[]>(`/ml/forecast/weekly${qs}`);
  },

  getMLHourlyForecast(branch?: string) {
    const qs = buildQueryString({ branch });
    return request<import("../types/api").MLHourlyForecastItem[]>(`/ml/forecast/hourly${qs}`);
  },

  getMLRecommendations(branch?: string, limit: number = 100) {
    const qs = buildQueryString({ branch, limit });
    return request<import("../types/api").MLProductionRecommendationItem[]>(`/ml/recommendations${qs}`);
  },

  getMLModelMetrics() {
    return request<import("../types/api").MLModelMetricsResponse>("/ml/model/metrics");
  },

  getMLModelStatus() {
    return request<import("../types/api").MLModelStatusResponse>("/ml/model/status");
  },

  // ---------------------------------------------------------------------------
  // F-15 Alerting & System Operations
  // ---------------------------------------------------------------------------
  getActiveAlerts(): Promise<AlertEvent[]> {
    return request<AlertEvent[]>("/operations/alerts/active");
  },

  getAlertHistory(limit: number = 50): Promise<AlertEvent[]> {
    return request<AlertEvent[]>(`/operations/alerts/history?limit=${limit}`);
  },

  triggerTestAlert(rule_id: string, message?: string, current_value: any = 1): Promise<AlertEvent> {
    return request<AlertEvent>("/operations/alerts/trigger-test", {
      method: "POST",
      body: JSON.stringify({ rule_id, message, current_value }),
    });
  },

  resolveAlert(rule_id: string): Promise<AlertEvent> {
    return request<AlertEvent>(`/operations/alerts/resolve/${rule_id}`, {
      method: "POST",
      body: JSON.stringify({}),
    });
  },

  getSystemHealth(): Promise<SystemHealthMetrics> {
    return request<SystemHealthMetrics>("/operations/system/health");
  },

  refreshDuckDBCache(): Promise<{ status: string; message: string }> {
    return request("/operations/cache/refresh", {
      method: "POST",
      body: JSON.stringify({}),
    });
  },

  triggerGoldSync(): Promise<{ status: string; message: string }> {
    return request("/operations/pipeline/trigger-gold", {
      method: "POST",
      body: JSON.stringify({}),
    });
  },

  getSecurityAuditLog(limit: number = 50): Promise<any[]> {
    return request<any[]>(`/admin/security/audit-log?limit=${limit}`);
  },

  getDataQualityReport(): Promise<any> {
    return request<any>("/operations/governance/quality-report");
  },

  getDataLineage(): Promise<any> {
    return request<any>("/operations/governance/lineage");
  },
};
