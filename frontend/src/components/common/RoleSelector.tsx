import React, { useEffect, useState } from "react";
import { Shield, ShieldCheck, ShieldAlert } from "lucide-react";
import { getActiveRole, setActiveRole, type UserRole } from "../../services/api";

export const RoleSelector: React.FC = () => {
  const [role, setRole] = useState<UserRole>(getActiveRole());

  useEffect(() => {
    const handleRoleChanged = () => setRole(getActiveRole());
    window.addEventListener("bakery_role_changed", handleRoleChanged);
    return () => window.removeEventListener("bakery_role_changed", handleRoleChanged);
  }, []);

  const handleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const newRole = e.target.value as UserRole;
    setActiveRole(newRole);
    setRole(newRole);
  };

  const getRoleBadge = (r: UserRole) => {
    switch (r) {
      case "admin":
        return {
          bg: "bg-red-50 text-red-700 border-red-200",
          icon: ShieldAlert,
          label: "Admin (Dosen)",
        };
      case "operator":
        return {
          bg: "bg-amber-50 text-amber-700 border-amber-200",
          icon: ShieldCheck,
          label: "Operator (Data Eng)",
        };
      default:
        return {
          bg: "bg-neutral-50 text-neutral-600 border-neutral-200",
          icon: Shield,
          label: "Viewer (Store Mgr)",
        };
    }
  };

  const badge = getRoleBadge(role);
  const Icon = badge.icon;

  return (
    <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg border text-xs font-medium transition-all shadow-2xs bg-white">
      <div className={`p-1 rounded ${badge.bg}`}>
        <Icon className="w-3.5 h-3.5" />
      </div>
      <div className="flex flex-col">
        <span className="text-[9px] uppercase tracking-wider text-neutral-400 font-semibold leading-none">
          Role
        </span>
        <select
          value={role}
          onChange={handleChange}
          className="text-xs font-semibold text-neutral-800 bg-transparent cursor-pointer focus:outline-hidden py-0.5"
          title="Ganti peran pengguna untuk menguji keamanan RBAC F-16"
        >
          <option value="viewer">Viewer (Read-Only)</option>
          <option value="operator">Operator (Data Eng)</option>
          <option value="admin">Admin (Full Control)</option>
        </select>
      </div>
    </div>
  );
};
