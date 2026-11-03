import {
  FileChartColumnIncreasing,
  Hospital,
  Network,
  ShieldCheck,
  LayoutDashboard,
  LogOut,
  Menu,
  ScanLine,
  Users,
  X,
} from "lucide-react";
import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { Brand } from "../components/Brand";
import { Button } from "../components/ui/Button";
import { useAuth } from "../hooks/useAuth";

const commonNavigation = [
  { icon: LayoutDashboard, label: "Dashboard", to: "/app" },
  { icon: ScanLine, label: "MRI analysis", to: "/app/mri-analysis" },
  {
    icon: FileChartColumnIncreasing,
    label: "Result workspace",
    to: "/app/results",
  },
];

export function AppShell() {
  const [isOpen, setIsOpen] = useState(false);
  const { actor, logout } = useAuth();
  const navigate = useNavigate();
  const isAdmin = actor?.role === "hospital_admin";
  const navigation = [
    ...commonNavigation,
    ...(isAdmin
      ? [
          { icon: Users, label: "Doctors", to: "/app/doctors" },
          { icon: Hospital, label: "Hospital", to: "/app/hospital" },
          { icon: Network, label: "Global model", to: "/app/federation" },
          { icon: ShieldCheck, label: "Blockchain trust", to: "/app/blockchain" },
        ]
      : []),
  ];

  const handleLogout = async () => {
    await logout();
    navigate("/");
  };

  return (
    <div className="min-h-screen bg-canvas text-ink lg:grid lg:grid-cols-[17rem_minmax(0,1fr)]">
      <aside
        className={`fixed inset-y-0 left-0 z-30 flex w-72 flex-col border-r border-border bg-sidebar p-5 transition-transform lg:sticky lg:translate-x-0 ${isOpen ? "translate-x-0" : "-translate-x-full"}`}
      >
        <div className="flex items-center justify-between">
          <Brand />
          <button
            aria-label="Close navigation"
            className="rounded-md p-2 text-muted lg:hidden"
            onClick={() => setIsOpen(false)}
            type="button"
          >
            <X aria-hidden className="h-5 w-5" />
          </button>
        </div>
        <nav aria-label="Primary navigation" className="mt-10 grid gap-1">
          {navigation.map(({ icon: Icon, label, to }) => (
            <NavLink
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition ${isActive ? "bg-primary/20 text-white ring-1 ring-primary/40" : "text-muted hover:bg-slate-700/60 hover:text-ink"}`
              }
              key={label}
              onClick={() => setIsOpen(false)}
              to={to}
            >
              <Icon aria-hidden className="h-5 w-5" />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto rounded-xl border border-border bg-slate-900/30 p-4">
          <p className="text-xs font-semibold uppercase tracking-wider text-secondary">
            Active context
          </p>
          <p className="mt-2 text-sm font-semibold text-ink">
            {actor?.hospital_name}
          </p>
          <p className="mt-1 text-xs capitalize text-muted">
            {actor?.role.replaceAll("_", " ")}
          </p>
          <Button
            className="mt-4 w-full"
            onClick={() => void handleLogout()}
            variant="ghost"
          >
            <LogOut aria-hidden className="h-4 w-4" />
            Log out
          </Button>
        </div>
      </aside>
      {isOpen ? (
        <button
          aria-label="Close navigation overlay"
          className="fixed inset-0 z-20 bg-slate-950/60 lg:hidden"
          onClick={() => setIsOpen(false)}
          type="button"
        />
      ) : null}
      <main className="min-w-0">
        <header className="sticky top-0 z-10 flex min-h-16 items-center justify-between border-b border-border bg-canvas/95 px-4 backdrop-blur sm:px-7">
          <button
            aria-label="Open navigation"
            className="rounded-md p-2 text-muted lg:hidden"
            onClick={() => setIsOpen(true)}
            type="button"
          >
            <Menu aria-hidden className="h-5 w-5" />
          </button>
          <div className="ml-auto text-right">
            <p className="text-sm font-medium text-ink">{actor?.full_name}</p>
            <p className="text-xs text-muted">{actor?.email}</p>
          </div>
        </header>
        <div className="mx-auto max-w-7xl p-4 sm:p-7">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
