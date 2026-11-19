import React from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Layout } from "./components/layout/Layout";
import { Overview } from "./pages/Overview";
import { SalesAnalytics } from "./pages/SalesAnalytics";
import { ProductAnalytics } from "./pages/ProductAnalytics";
import { PaymentAnalytics } from "./pages/PaymentAnalytics";
import { DemandForecasting } from "./pages/DemandForecasting";
import { SystemAlerts } from "./pages/SystemAlerts";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
      staleTime: 30 * 1000, // 30s cache
    },
  },
});

export const App: React.FC = () => {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Layout />}>
            <Route index element={<Overview />} />
            <Route path="sales" element={<SalesAnalytics />} />
            <Route path="products" element={<ProductAnalytics />} />
            <Route path="payments" element={<PaymentAnalytics />} />
            <Route path="forecast" element={<DemandForecasting />} />
            <Route path="alerts" element={<SystemAlerts />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
};

export default App;
