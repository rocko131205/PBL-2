import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { BookOpenCheck, ChevronDown, History, LayoutDashboard, LogOut, Menu, ShieldAlert, ShieldCheck, Upload, Workflow, X } from "lucide-react";
import clsx from "clsx";
import { Wordmark } from "@/components/Brand";
import { useAuth } from "@/lib/auth";

const NAV = [
  { to: "/upload", label: "Upload", Icon: Upload },
  { to: "/analysis", label: "Analysis", Icon: LayoutDashboard },
  { to: "/workflow", label: "Agent workflow", Icon: Workflow },
  { to: "/basel", label: "Basel III", Icon: BookOpenCheck },
  { to: "/history", label: "File history", Icon: History },
];
const ACCOUNT = [{ to: "/security", label: "Security", Icon: ShieldCheck }];

function initials(name: string) {
  return name.trim().split(/\s+/).slice(0, 2).map((w) => w[0]?.toUpperCase() ?? "").join("") || "?";
}

function NavItem({ to, label, Icon, onClick }: { to: string; label: string; Icon: typeof Upload; onClick: () => void }) {
  return (
    <NavLink
      to={to} onClick={onClick}
      className={({ isActive }) =>
        clsx("flex items-center gap-3 rounded-xl px-3.5 py-2.5 text-sm font-medium transition",
          isActive ? "accent-gradient text-white shadow-[0_8px_24px_-10px_#3b82f6]" : "text-ink-2 hover:bg-white/[0.06] hover:text-ink")}
    >
      <Icon className="size-[18px]" aria-hidden /> {label}
    </NavLink>
  );
}

export function AppLayout() {
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const close = () => setOpen(false);
  const account = user?.is_admin ? [...ACCOUNT, { to: "/admin/security", label: "Security dashboard", Icon: ShieldAlert }] : ACCOUNT;
  const first = user?.full_name.split(" ")[0] ?? "";

  return (
    <div className="min-h-screen gap-4 p-3 lg:grid lg:grid-cols-[16.5rem_minmax(0,1fr)] lg:p-4">
      {/* Sidebar: floats as a rounded glass panel on desktop, a drawer on small screens */}
      <aside
        className={clsx(
          "glass fixed inset-y-3 left-3 z-40 flex w-64 flex-col rounded-3xl p-4 transition-transform lg:sticky lg:top-4 lg:h-[calc(100vh-2rem)] lg:w-auto lg:translate-x-0",
          open ? "translate-x-0" : "-translate-x-[110%]",
        )}
      >
        <div className="flex items-center justify-between px-1.5 pb-7 pt-1.5">
          <Wordmark />
          <button className="rounded p-1 text-ink-3 lg:hidden" onClick={close} aria-label="Close menu"><X className="size-5" /></button>
        </div>
        <nav aria-label="Main" className="space-y-1">
          {NAV.map((n) => <NavItem key={n.to} {...n} onClick={close} />)}
        </nav>
        <div className="mt-auto space-y-1 border-t border-line pt-4">
          {account.map((n) => <NavItem key={n.to} {...n} onClick={close} />)}
        </div>
      </aside>
      {open && <div className="fixed inset-0 z-30 bg-black/60 lg:hidden" onClick={close} aria-hidden />}

      <div className="flex min-w-0 flex-col">
        <header className="flex items-center gap-3 px-1 py-3 sm:px-3">
          <button className="rounded-lg p-2 text-ink-2 hover:bg-white/[0.06] lg:hidden" onClick={() => setOpen(true)} aria-label="Open menu"><Menu className="size-5" /></button>
          <div>
            <div className="text-xl font-semibold tracking-tight sm:text-2xl">Welcome, <span className="accent-text">{first}</span></div>
            <div className="text-xs text-ink-3 sm:text-sm">Here's your financial analysis workspace</div>
          </div>
          <div className="ml-auto"><UserMenu name={user?.full_name ?? ""} email={user?.email ?? ""} onSignOut={logout} /></div>
        </header>
        <main className="flex-1 px-1 pb-8 pt-2 sm:px-3"><Outlet /></main>
      </div>
    </div>
  );
}

function UserMenu({ name, email, onSignOut }: { name: string; email: string; onSignOut: () => void }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", close); };
  }, []);
  return (
    <div ref={ref} className="relative">
      <button onClick={() => setOpen((o) => !o)} aria-haspopup="menu" aria-expanded={open}
        className="glass flex items-center gap-2.5 rounded-full p-1.5 pr-3 hover:bg-white/10">
        <span className="accent-gradient grid size-9 place-items-center rounded-full text-xs font-semibold text-white">{initials(name)}</span>
        <span className="hidden text-left leading-tight sm:block">
          <span className="block text-sm font-medium">{name}</span>
          <span className="block text-[11px] text-ink-3">{email}</span>
        </span>
        <ChevronDown className="size-4 text-ink-3" aria-hidden />
      </button>
      {open && (
        <div role="menu" className="glass absolute right-0 z-50 mt-2 w-52 rounded-2xl bg-surface-solid p-1.5">
          <button role="menuitem" onClick={onSignOut} className="flex w-full items-center gap-2 rounded-xl px-3 py-2.5 text-sm text-ink-2 hover:bg-white/[0.06] hover:text-ink">
            <LogOut className="size-4" aria-hidden /> Sign out
          </button>
        </div>
      )}
    </div>
  );
}
