import React from "react";
import { NavLink } from "react-router-dom";
import {
  LayoutDashboard,
  TrendingUp,
  UtensilsCrossed,
  CreditCard,
  Wheat,
  X,
  BrainCircuit,
  BellRing,
} from "lucide-react";

interface SidebarProps {
  onClose: () => void;
  isOpen: boolean;
}

const NAV_ITEMS = [
  { path: "/", label: "Overview", icon: LayoutDashboard },
  { path: "/sales", label: "Sales Analytics", icon: TrendingUp },
  { path: "/products", label: "Product Analytics", icon: UtensilsCrossed },
  { path: "/payments", label: "Payment Analytics", icon: CreditCard },
  { path: "/forecast", label: "Demand Forecasting", icon: BrainCircuit },
  { path: "/alerts", label: "System & Alerts", icon: BellRing },
];

export const Sidebar: React.FC<SidebarProps> = ({ isOpen, onClose }) => {
  return (
    <>
      {/* Mobile Backdrop */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-black/40 z-40 lg:hidden backdrop-blur-xs transition-opacity"
          onClick={onClose}
        />
      )}

      {/* Sidebar Container */}
      <aside
        className={`fixed top-0 bottom-0 left-0 z-50 w-64 bg-white border-r border-[#ede8df] flex flex-col transition-transform duration-200 ease-in-out lg:translate-x-0 ${
          isOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        {/* Brand Header */}
        <div className="h-16 flex items-center justify-between px-6 border-b border-[#ede8df]">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-[#7c3f15] text-[#fbf8f5] flex items-center justify-center shadow-xs">
              <Wheat className="w-5 h-5" />
            </div>
            <div>
              <h1 className="text-sm font-bold tracking-tight text-[#1e1b18] leading-tight">
                Toko Roti Pagi
              </h1>
              <p className="text-[10px] text-[#8c8275] font-semibold uppercase tracking-wider">
                Bakery Data Platform
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="lg:hidden p-1.5 text-stone-500 hover:text-stone-800 rounded-md"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Navigation Items */}
        <nav className="flex-1 px-3 py-6 space-y-1.5 overflow-y-auto">
          <div className="px-3 pb-2 text-[10px] font-bold uppercase tracking-wider text-[#a09789]">
            Analytics Menus
          </div>
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.path}
                to={item.path}
                onClick={onClose}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-xs font-semibold transition-all ${
                    isActive
                      ? "bg-[#f5efe6] text-[#7c3f15] shadow-2xs font-bold"
                      : "text-[#6b6256] hover:bg-[#faf7f2] hover:text-[#1e1b18]"
                  }`
                }
              >
                <Icon className="w-4 h-4 shrink-0" />
                <span>{item.label}</span>
              </NavLink>
            );
          })}
        </nav>

        {/* Footer Info */}
        <div className="p-4 border-t border-[#ede8df] bg-[#faf7f2]/60">
          <div className="bg-white rounded-lg p-3 border border-[#ede8df] text-xs">
            <p className="font-semibold text-[#1e1b18]">TRP Data Mart V4</p>
            <p className="text-[11px] text-[#7c7267] mt-0.5">
              Near-Realtime Gold Parquet powered by Spark & DuckDB.
            </p>
          </div>
        </div>
      </aside>
    </>
  );
};
