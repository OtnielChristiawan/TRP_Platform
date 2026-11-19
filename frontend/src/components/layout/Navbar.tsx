import React from "react";
import { Menu, Coffee } from "lucide-react";
import type { FreshnessResponse } from "../../types/api";
import { FreshnessIndicator } from "../common/FreshnessIndicator";
import { RoleSelector } from "../common/RoleSelector";

interface NavbarProps {
  onToggleSidebar: () => void;
  freshness?: FreshnessResponse;
  isLoadingFreshness?: boolean;
  onRefresh?: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({
  onToggleSidebar,
  freshness,
  isLoadingFreshness,
  onRefresh,
}) => {
  return (
    <header className="h-16 bg-white border-b border-[#ede8df] sticky top-0 z-30 flex items-center justify-between px-4 sm:px-6">
      <div className="flex items-center gap-3">
        <button
          onClick={onToggleSidebar}
          className="lg:hidden p-2 text-[#7c7267] hover:text-[#1e1b18] hover:bg-[#f5efe6] rounded-lg transition-colors cursor-pointer"
        >
          <Menu className="w-5 h-5" />
        </button>
        <div className="hidden sm:flex items-center gap-2">
          <div className="p-1.5 bg-[#f5efe6] text-[#7c3f15] rounded-lg">
            <Coffee className="w-4 h-4" />
          </div>
          <span className="text-xs font-semibold text-[#6b6256]">
            Sales Analytics Dashboard
          </span>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <RoleSelector />
        <FreshnessIndicator
          freshness={freshness}
          isLoading={isLoadingFreshness}
          onRefresh={onRefresh}
        />
      </div>
    </header>
  );
};
