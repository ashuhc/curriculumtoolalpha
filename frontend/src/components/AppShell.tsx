// Application chrome: sidebar navigation, top bar (term, presence, theme, account) and toasts.
import {
  AlertCircle, AlertTriangle, BarChart3, CheckCircle2, Info, CalendarRange, ClipboardList, LayoutDashboard, LogIn, LogOut, Menu, Moon, Settings2, Sun, X,
} from "lucide-react";
import { useEffect, type ReactNode } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { useAuth, useIsAdmin } from "../store/auth";
import { useCollab } from "../store/collab";
import { usePlan } from "../store/plan";
import { useUI } from "../store/ui";
import { TermSelect } from "./SettingsPanel";
import { Avatar, BrandMark, IconButton, cx } from "./ui";

const NAV = [
  { group: "Planning", items: [
    { to: "/", label: "Overview", icon: LayoutDashboard },
    { to: "/demand", label: "Enrollment Projections", icon: BarChart3 },
    { to: "/schedule", label: "Term Schedule", icon: CalendarRange },
    { to: "/conflicts", label: "Conflicts & Audits", icon: AlertTriangle },
  ] },
  { group: "Faculty", items: [{ to: "/preferences", label: "Teaching Preferences", icon: ClipboardList }] },
  { group: "Administration", admin: true, items: [{ to: "/admin", label: "Administration", icon: Settings2 }] },
];

function Brand() {
  return (
    <div className="flex items-center gap-2.5 px-3 py-4">
      <BrandMark size={28} />
      <div className="leading-tight">
        <div className="text-[13px] font-semibold">Economics Scheduler</div>
        <div className="text-[11px] text-muted">Northeastern University</div>
      </div>
    </div>
  );
}

function Sidebar() {
  const isAdmin = useIsAdmin();
  const user = useAuth((s) => s.user);
  const signOut = useAuth((s) => s.signOut);
  const setNavOpen = useUI((s) => s.setNavOpen);
  const navigate = useNavigate();
  return (
    <div className="flex h-full flex-col">
      <Brand />
      <nav className="flex-1 space-y-5 overflow-y-auto px-2 py-2">
        {NAV.filter((g) => !g.admin || isAdmin).map((g) => (
          <div key={g.group}>
            <div className="px-2 pb-1 text-[11px] font-medium uppercase tracking-wider text-faint">{g.group}</div>
            {g.items.map((n) => (
              <NavLink key={n.to} to={n.to} end={n.to === "/"} onClick={() => setNavOpen(false)}
                className={({ isActive }) => cx("group relative flex h-8 items-center gap-2.5 rounded-md px-2 text-[13px] transition-colors",
                  isActive ? "bg-red-50 font-medium text-fg dark:bg-red-500/10 before:absolute before:inset-y-1.5 before:-left-2 before:w-[3px] before:rounded-full before:bg-nu"
                    : "text-muted hover:bg-hover hover:text-fg")}>
                <n.icon className="h-4 w-4 shrink-0 group-aria-[current=page]:text-[#D01C28] dark:group-aria-[current=page]:text-red-400" strokeWidth={1.75} />{n.label}
              </NavLink>
            ))}
          </div>
        ))}
      </nav>
      <div className="border-t border-line p-2">
        {user ? (
          <div className="flex items-center gap-2.5 rounded-md px-2 py-2">
            <Avatar name={user.name} size={28} />
            <div className="min-w-0 flex-1 leading-tight">
              <div className="truncate text-[13px] font-medium">{user.name}</div>
              <div className="truncate text-[11px] text-muted">{user.role === "admin" ? "Scheduler" : "Faculty"} · {user.email}</div>
            </div>
            <IconButton label="Sign Out" onClick={() => { signOut(); navigate("/"); useUI.getState().success("Signed out"); }}><LogOut className="h-4 w-4" /></IconButton>
          </div>
        ) : (
          <NavLink to="/login" className="flex h-9 items-center gap-2 rounded-md px-2 text-[13px] text-muted hover:bg-hover hover:text-fg">
            <LogIn className="h-4 w-4" /> Sign In
          </NavLink>
        )}
      </div>
    </div>
  );
}

function Presence() {
  const presence = useCollab((s) => s.presence);
  const status = useCollab((s) => s.status);
  const me = useAuth((s) => s.user);
  const others = presence.filter((p) => p.id !== me?.id && p.role !== "guest");
  const label = { online: "Live", connecting: "Connecting", offline: "Offline" }[status];
  return (
    <div className="flex items-center gap-3">
      {others.length > 0 && (
        <div className="hidden -space-x-1.5 sm:flex">
          {others.slice(0, 4).map((p) => (
            <span key={p.id} title={`${p.name}${p.page ? ` · ${p.page}` : ""}${p.section_id ? ` · ${p.section_id}` : ""}`}>
              <Avatar name={p.name} size={24} ring />
            </span>
          ))}
          {others.length > 4 && <span className="flex h-6 w-6 items-center justify-center rounded-full bg-subtle text-[10px] ring-2 ring-surface">+{others.length - 4}</span>}
        </div>
      )}
      <span className="flex items-center gap-1.5 text-xs text-muted" title="Real-Time Collaboration Connection">
        <span className={cx("h-1.5 w-1.5 rounded-full", status === "online" ? "bg-emerald-500" : status === "connecting" ? "bg-amber-500" : "bg-faint")} />
        {label}
      </span>
    </div>
  );
}

const TOAST_STYLE = {
  success: { box: "border-emerald-200 bg-emerald-50/95 text-emerald-800 dark:border-emerald-800/60 dark:bg-emerald-950/80 dark:text-emerald-300",
             body: "text-emerald-700/80 dark:text-emerald-300/70", icon: CheckCircle2 },
  error: { box: "border-nu/30 bg-surface text-fg", body: "text-muted", icon: AlertCircle },
  info: { box: "border-line bg-surface text-fg", body: "text-muted", icon: Info },
} as const;

function Toaster() {
  const toasts = useUI((s) => s.toasts);
  const dismiss = useUI((s) => s.dismiss);
  return (
    <div aria-live="polite" className="pointer-events-none fixed bottom-4 left-1/2 z-[60] flex w-[380px] max-w-[92vw] -translate-x-1/2 flex-col gap-2">
      {toasts.map((t) => {
        const st = TOAST_STYLE[t.tone];
        const Icon = st.icon;
        return (
          <div key={t.id} role={t.tone === "error" ? "alert" : "status"}
            className={cx("pointer-events-auto flex items-start gap-2.5 rounded-md border px-3 py-2.5 shadow-lg backdrop-blur",
              st.box, t.leaving ? "animate-toast-out" : "animate-fade-up")}>
            <Icon className={cx("mt-px h-4 w-4 shrink-0", t.tone === "error" ? "text-nu-text" : t.tone === "info" ? "text-sky-500" : "")} />
            <div className="min-w-0 flex-1">
              <div className="text-[13px] font-medium">{t.title}</div>
              {t.body && <div className={cx("truncate text-xs", st.body)}>{t.body}</div>}
            </div>
            <button onClick={() => dismiss(t.id)} aria-label="Dismiss" className="opacity-60 hover:opacity-100"><X className="h-3.5 w-3.5" /></button>
          </div>
        );
      })}
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const { theme, toggleTheme, navOpen, setNavOpen } = useUI();
  const term = usePlan((s) => s.settings.target_term);
  const sendPresence = useCollab((s) => s.sendPresence);
  const location = useLocation();
  const pageName = NAV.flatMap((g) => g.items).find((n) => n.to === location.pathname)?.label ?? "Sign In";

  useEffect(() => { sendPresence({ page: pageName, term, section_id: null }); }, [pageName, term, sendPresence]);

  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 border-r border-line bg-surface lg:block"><Sidebar /></aside>
      {navOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div className="absolute inset-0 bg-black/30" onClick={() => setNavOpen(false)} />
          <aside className="animate-fade-up absolute inset-y-0 left-0 w-64 border-r border-line bg-surface"><Sidebar /></aside>
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-40 flex h-12 items-center gap-3 border-b border-line bg-surface/90 px-4 backdrop-blur md:px-6">
          <IconButton label="Open Navigation" className="lg:hidden" onClick={() => setNavOpen(true)}><Menu className="h-4 w-4" /></IconButton>
          <div className="flex items-center gap-2 text-xs text-muted">
            <span className="hidden sm:inline">Term</span>
            <div className="w-40"><TermSelect compact /></div>
          </div>
          <div className="ml-auto flex items-center gap-2">
            <Presence />
            <div className="mx-1 h-4 w-px bg-line" />
            <button aria-label={theme === "dark" ? "Switch to Light Theme" : "Switch to Dark Theme"}
              title={theme === "dark" ? "Switch to Light Theme" : "Switch to Dark Theme"} onClick={toggleTheme}
              className="inline-flex h-8 w-8 items-center justify-center rounded-md text-[#D01C28] transition-colors hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-500/10">
              {theme === "dark" ? <Moon className="h-4 w-4" /> : <Sun className="h-4 w-4" />}
            </button>
          </div>
        </header>
        <main className="mx-auto w-full max-w-[1440px] flex-1 px-4 py-6 md:px-8">{children}</main>
        <footer className="border-t border-line px-8 py-4 text-xs text-faint">
          Northeastern University · Department of Economics · Undergraduate Curriculum Planning
        </footer>
      </div>
      <Toaster />
    </div>
  );
}
