// Design-system primitives: restrained, border-led, enterprise-dashboard styling.
import { AlertCircle, AlertTriangle, CheckCircle2, GraduationCap, Info, Loader2, X, type LucideIcon } from "lucide-react";
import { Link } from "react-router-dom";
import { useEffect, useId, type ButtonHTMLAttributes, type ReactNode } from "react";

export function cx(...c: (string | false | null | undefined)[]) {
  return c.filter(Boolean).join(" ");
}

/**
 * Elevated card surface, theme-aware. Light: white on the slate-50 canvas with a
 * soft border and xs shadow. Dark: translucent zinc with a white/10 hairline and
 * a faint top highlight for depth.
 */
export const CARD = "rounded-lg border border-slate-200/80 bg-white shadow-xs dark:border-white/10 dark:bg-zinc-900/70 dark:shadow-[inset_0_1px_0_rgb(255_255_255/0.04),0_1px_2px_rgb(0_0_0/0.4)]";
/** Hover micro-interaction for clickable cards: lift slightly, border warms toward Northeastern Red. */
export const CARD_INTERACTIVE = "transition duration-150 hover:-translate-y-px hover:border-nu/40 hover:shadow-md dark:hover:border-nu/50 dark:hover:shadow-[0_10px_28px_-14px_rgb(208_28_40/0.55)] motion-reduce:transform-none";

/** Tinted icon badges (static class strings so Tailwind keeps them). */
export const ICON_TONE = {
  primary: "bg-red-50 text-[#D01C28] dark:bg-red-500/10 dark:text-red-400",
  warning: "bg-amber-50 text-amber-600 dark:bg-amber-500/10 dark:text-amber-400",
  success: "bg-emerald-50 text-emerald-600 dark:bg-emerald-500/10 dark:text-emerald-400",
  neutral: "bg-slate-100 text-slate-500 dark:bg-white/5 dark:text-zinc-400",
} as const;
export type IconTone = keyof typeof ICON_TONE;

export function IconBadge({ icon: Icon, tone = "primary", size = 30 }: { icon: LucideIcon; tone?: IconTone; size?: number }) {
  return (
    <span className={cx("inline-flex shrink-0 items-center justify-center rounded-md", ICON_TONE[tone])} style={{ width: size, height: size }}>
      <Icon className="h-4 w-4" strokeWidth={1.9} />
    </span>
  );
}

// ------------------------------------------------------------------ layout ---
export function PageHeader({ title, description, actions, meta, eyebrow }: { title: string; description?: ReactNode; actions?: ReactNode; meta?: ReactNode; eyebrow?: string }) {
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-4 border-b border-line pb-5">
      <div className="min-w-0 flex-1 basis-80">
        {eyebrow && (
          <div className="mb-1.5 flex items-center gap-1.5 text-[11px] font-semibold tracking-wide text-nu-text">
            <span className="h-1.5 w-1.5 rounded-full bg-nu" />{eyebrow}
          </div>
        )}
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        {description && <p className="mt-1 text-[13px] leading-relaxed text-muted text-pretty">{description}</p>}
        {meta && <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted">{meta}</div>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Panel({ title, description, actions, children, className, bodyClass, flush }: {
  title?: ReactNode; description?: ReactNode; actions?: ReactNode; children?: ReactNode; className?: string; bodyClass?: string; flush?: boolean;
}) {
  return (
    <section className={cx(CARD, className)}>
      {(title || actions) && (
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-4 py-3">
          <div className="min-w-0 flex-1 basis-64">
            {title && <h2 className="text-[13px] font-semibold">{title}</h2>}
            {description && <p className="mt-0.5 text-xs leading-relaxed text-muted">{description}</p>}
          </div>
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={cx(!flush && "p-4", bodyClass)}>{children}</div>
    </section>
  );
}

export function StatGrid({ children, cols = 4 }: { children: ReactNode; cols?: 3 | 4 | 5 | 6 }) {
  const c = { 3: "md:grid-cols-3", 4: "md:grid-cols-4", 5: "md:grid-cols-5", 6: "md:grid-cols-3 xl:grid-cols-6" }[cols];
  return <div className={cx("grid grid-cols-2 gap-3", c)}>{children}</div>;
}

export function Stat({ label, value, sub, tone, icon, iconTone = "primary", onClick, active, to }: {
  label: string; value: ReactNode; sub?: ReactNode; tone?: "danger" | "warning" | "success";
  icon?: LucideIcon; iconTone?: IconTone; onClick?: () => void; active?: boolean; to?: string;
}) {
  const color = tone === "danger" ? "text-nu-text" : tone === "warning" ? "text-amber-600 dark:text-amber-400" : tone === "success" ? "text-emerald-600 dark:text-emerald-400" : "";
  const interactive = !!(onClick || to);
  const body = (
    <>
      <div className="flex items-start justify-between gap-2">
        <div className="text-xs font-medium text-muted">{label}</div>
        {icon && <IconBadge icon={icon} tone={iconTone} size={28} />}
      </div>
      <div className={cx("mt-1 text-2xl font-semibold tabular-nums tracking-tight", color)}>{value}</div>
      {sub && <div className="mt-0.5 truncate text-xs text-faint">{sub}</div>}
    </>
  );
  const cls = cx(CARD, "block px-4 py-3.5", interactive && CARD_INTERACTIVE, interactive && "cursor-pointer",
    active && "ring-1 ring-nu/40 dark:ring-nu/50");
  if (to) return <Link to={to} className={cls}>{body}</Link>;
  return <div onClick={onClick} className={cls}>{body}</div>;
}

// ---------------------------------------------------------------- controls ---
type Variant = "primary" | "secondary" | "ghost" | "danger";
export function Button({ variant = "secondary", size = "md", icon, loading, className, children, ...rest }:
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: "sm" | "md"; icon?: ReactNode; loading?: boolean }) {
  const v: Record<Variant, string> = {
    primary: "bg-nu text-white hover:bg-nu-hover border-transparent",
    secondary: "bg-surface border-line-strong hover:bg-hover",
    ghost: "border-transparent text-muted hover:bg-hover hover:text-fg",
    danger: "bg-surface border-line-strong text-nu-text hover:bg-nu-soft",
  };
  return (
    <button
      className={cx("inline-flex select-none items-center justify-center gap-1.5 whitespace-nowrap rounded-md border font-medium transition-colors disabled:pointer-events-none disabled:opacity-50",
        size === "sm" ? "h-7 px-2.5 text-xs" : "h-8 px-3 text-[13px]", v[variant], className)}
      disabled={loading || rest.disabled} {...rest}>
      {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : icon}
      {children}
    </button>
  );
}

/** Small info icon that reveals supplementary detail on hover or keyboard focus. */
export function InfoTip({ label, children }: { label: string; children: ReactNode }) {
  const id = useId();
  return (
    <span className="group relative inline-flex align-middle">
      <button type="button" aria-label={label} aria-describedby={id}
        className="inline-flex h-4 w-4 items-center justify-center rounded-full text-faint outline-none transition-colors hover:text-fg focus-visible:text-fg focus-visible:ring-2 focus-visible:ring-fg/20">
        <Info className="h-3.5 w-3.5" />
      </button>
      <span role="tooltip" id={id}
        className="pointer-events-none invisible absolute left-1/2 top-full z-30 mt-1.5 w-72 max-w-[80vw] -translate-x-1/2 rounded-md border border-line bg-surface px-3 py-2 text-xs font-normal leading-relaxed text-muted opacity-0 shadow-md transition-opacity group-focus-within:visible group-focus-within:opacity-100 group-hover:visible group-hover:opacity-100">
        {children}
      </span>
    </span>
  );
}

export function IconButton({ label, className, children, ...rest }: ButtonHTMLAttributes<HTMLButtonElement> & { label: string }) {
  return (
    <button aria-label={label} title={label}
      className={cx("inline-flex h-8 w-8 items-center justify-center rounded-md text-muted transition-colors hover:bg-hover hover:text-fg", className)} {...rest}>
      {children}
    </button>
  );
}

const TONES = {
  neutral: "bg-subtle text-muted border-line",
  red: "bg-nu-soft text-nu-text border-transparent",
  amber: "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-transparent",
  green: "bg-emerald-500/10 text-emerald-600 border-transparent",
  blue: "bg-sky-500/10 text-sky-600 border-transparent",
};
export type Tone = keyof typeof TONES;
export function Badge({ children, tone = "neutral", className }: { children: ReactNode; tone?: Tone; className?: string }) {
  return <span className={cx("inline-flex items-center gap-1 whitespace-nowrap rounded border px-1.5 py-px text-[11px] font-medium", TONES[tone], className)}>{children}</span>;
}

export const inputBase = "h-8 rounded-md border border-line-strong bg-surface px-2.5 text-[13px] outline-none transition-colors placeholder:text-faint focus:border-fg/40 focus:ring-2 focus:ring-fg/5 disabled:opacity-50";
export const inputCls = inputBase + " w-full";
export const textareaCls = "w-full rounded-md border border-line-strong bg-surface px-2.5 py-2 text-[13px] outline-none placeholder:text-faint focus:border-fg/40 focus:ring-2 focus:ring-fg/5";

export function Field({ label, hint, children, className }: { label: ReactNode; hint?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <label className={cx("block", className)}>
      <span className="mb-1.5 block text-xs font-medium text-fg">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-faint">{hint}</span>}
    </label>
  );
}

export function Switch({ checked, onChange, label, disabled }: { checked: boolean; onChange: (v: boolean) => void; label?: ReactNode; disabled?: boolean }) {
  return (
    <label className={cx("relative inline-flex cursor-pointer select-none items-center gap-2 text-[13px]", disabled && "pointer-events-none opacity-50")}>
      <span className={cx("relative h-[18px] w-8 shrink-0 rounded-full transition-colors", checked ? "bg-nu" : "bg-line-strong")}>
        <span className={cx("absolute top-[2px] h-[14px] w-[14px] rounded-full bg-white transition-all", checked ? "left-[16px]" : "left-[2px]")} />
      </span>
      <input type="checkbox" className="sr-only" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      {label}
    </label>
  );
}

export function Tabs<T extends string>({ tabs, value, onChange, className }: { tabs: { id: T; label: ReactNode; count?: number }[]; value: T; onChange: (t: T) => void; className?: string }) {
  return (
    <div className={cx("flex gap-4 border-b border-line", className)}>
      {tabs.map((t) => (
        <button key={t.id} onClick={() => onChange(t.id)}
          className={cx("-mb-px flex items-center gap-1.5 border-b-2 py-2 text-[13px] font-medium transition-colors",
            value === t.id ? "border-nu text-fg" : "border-transparent text-muted hover:text-fg")}>
          {t.label}
          {t.count !== undefined && <span className="rounded bg-subtle px-1.5 text-[11px] tabular-nums text-muted">{t.count}</span>}
        </button>
      ))}
    </div>
  );
}

export function Segmented<T extends string>({ options, value, onChange }: { options: { id: T; label: ReactNode }[]; value: T; onChange: (v: T) => void }) {
  return (
    <div className="inline-flex rounded-md border border-line-strong p-0.5">
      {options.map((o) => (
        <button key={o.id} onClick={() => onChange(o.id)}
          className={cx("flex h-6 items-center gap-1.5 rounded px-2.5 text-xs font-medium transition-colors",
            value === o.id ? "bg-subtle text-fg" : "text-muted hover:text-fg")}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

// ------------------------------------------------------------------ tables ---
/** Height for primary data tables: fills the viewport below the header, scrolling internally. */
export const DATA_MAX_H = "max-h-[max(18rem,calc(100dvh-11rem))]";

export function Table({ children, maxH = DATA_MAX_H, className }: { children: ReactNode; maxH?: string; className?: string }) {
  return (
    <div className={cx("overflow-auto", maxH, className)}>
      <table className="w-full border-collapse text-[13px] [&_td]:border-b [&_td]:border-line [&_td]:px-3 [&_td]:py-2 [&_td]:align-middle [&_th]:sticky [&_th]:top-0 [&_th]:z-10 [&_th]:border-b [&_th]:border-line [&_th]:bg-subtle [&_th]:px-3 [&_th]:py-2 [&_th]:text-left [&_th]:text-[11px] [&_th]:font-medium [&_th]:whitespace-nowrap [&_th]:text-muted [&_tbody_tr:last-child_td]:border-b-0">
        {children}
      </table>
    </div>
  );
}

// ---------------------------------------------------------------- feedback ---
export function Spinner({ label = "Loading…" }: { label?: string }) {
  return <div className="flex items-center gap-2 py-10 text-[13px] text-muted"><Loader2 className="h-4 w-4 animate-spin" /> {label}</div>;
}

export function Alert({ tone = "info", title, children, action }: { tone?: "info" | "warning" | "error" | "success"; title?: ReactNode; children?: ReactNode; action?: ReactNode }) {
  const map = {
    info: { icon: Info, cls: "border-line bg-subtle", ic: "text-muted" },
    warning: { icon: AlertTriangle, cls: "border-amber-500/30 bg-amber-500/5", ic: "text-amber-500" },
    error: { icon: AlertCircle, cls: "border-nu/30 bg-nu-soft", ic: "text-nu-text" },
    success: { icon: CheckCircle2, cls: "border-emerald-500/30 bg-emerald-500/5", ic: "text-emerald-500" },
  }[tone];
  const Icon = map.icon;
  return (
    <div className={cx("flex items-start gap-2.5 rounded-md border px-3 py-2.5 text-[13px]", map.cls)}>
      <Icon className={cx("mt-px h-4 w-4 shrink-0", map.ic)} />
      <div className="min-w-0 flex-1">
        {title && <div className="font-medium">{title}</div>}
        {children && <div className={cx(!!title && "mt-0.5", "text-muted")}>{children}</div>}
      </div>
      {action}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: string; onRetry?: () => void }) {
  return <Alert tone="error" title="Something Went Wrong" action={onRetry && <Button size="sm" onClick={onRetry}>Retry</Button>}>{error}</Alert>;
}

export function Empty({ icon, title, children }: { icon?: ReactNode; title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-12 text-center">
      {icon && <div className="mb-3 text-faint">{icon}</div>}
      <div className="text-[13px] font-medium">{title}</div>
      {children && <div className="mt-1 max-w-sm text-xs text-muted">{children}</div>}
    </div>
  );
}

export function Avatar({ name, size = 24, ring }: { name: string; size?: number; ring?: boolean }) {
  const parts = name.replace(",", "").split(/\s+/).filter(Boolean);
  const text = ((parts[0]?.[0] ?? "") + (parts[1]?.[0] ?? "")).toUpperCase();
  let h = 0;
  for (const ch of name) h = (h * 31 + ch.charCodeAt(0)) % 360;
  return (
    <span title={name} className={cx("inline-flex shrink-0 items-center justify-center rounded-full font-semibold text-white", ring && "ring-2 ring-surface")}
      style={{ width: size, height: size, fontSize: size * 0.4, background: `hsl(${h} 35% 42%)` }}>{text}</span>
  );
}

// ---------------------------------------------------------------- overlays ---
export function Drawer({ open, onClose, title, subtitle, children, footer, width = "w-[520px]" }: {
  open: boolean; onClose: () => void; title: ReactNode; subtitle?: ReactNode; children: ReactNode; footer?: ReactNode; width?: string;
}) {
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    if (open) document.addEventListener("keydown", k);
    return () => document.removeEventListener("keydown", k);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50">
      <div className="absolute inset-0 bg-black/30" onClick={onClose} />
      <aside className={cx("animate-slide-in absolute inset-y-0 right-0 flex max-w-full flex-col border-l border-slate-200 bg-white shadow-xl dark:border-white/10 dark:bg-zinc-900", width)}>
        <header className="flex items-start justify-between gap-3 border-b border-line px-5 py-4">
          <div className="min-w-0">
            <div className="text-[15px] font-semibold">{title}</div>
            {subtitle && <div className="mt-0.5 text-xs text-muted">{subtitle}</div>}
          </div>
          <IconButton label="Close" onClick={onClose}><X className="h-4 w-4" /></IconButton>
        </header>
        <div className="flex-1 overflow-y-auto">{children}</div>
        {footer && <footer className="border-t border-line px-5 py-3">{footer}</footer>}
      </aside>
    </div>
  );
}

export function Modal({ open, onClose, title, children, footer }: { open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; footer?: ReactNode }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="animate-fade-up relative w-full max-w-md rounded-lg border border-slate-200 bg-white shadow-xl dark:border-white/10 dark:bg-zinc-900">
        <header className="flex items-center justify-between border-b border-line px-5 py-3">
          <div className="text-[15px] font-semibold">{title}</div>
          <IconButton label="Close" onClick={onClose}><X className="h-4 w-4" /></IconButton>
        </header>
        <div className="px-5 py-4">{children}</div>
        {footer && <footer className="flex justify-end gap-2 border-t border-line px-5 py-3">{footer}</footer>}
      </div>
    </div>
  );
}

/** Themed confirmation dialog (replaces window.confirm). Escape or the backdrop cancels. */
export function ConfirmDialog({ open, title, children, confirmLabel, tone = "primary", busy, onConfirm, onCancel }: {
  open: boolean; title: string; children: ReactNode; confirmLabel: string; tone?: "primary" | "danger";
  busy?: boolean; onConfirm: () => void; onCancel: () => void;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape" && !busy) onCancel(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, busy, onCancel]);
  return (
    <Modal open={open} onClose={() => !busy && onCancel()} title={title}
      footer={<>
        <Button variant="ghost" onClick={onCancel} disabled={busy}>Cancel</Button>
        <Button variant={tone === "danger" ? "danger" : "primary"} loading={busy} onClick={onConfirm} autoFocus>{confirmLabel}</Button>
      </>}>
      <div className="space-y-3 text-[13px] leading-relaxed text-muted">{children}</div>
    </Modal>
  );
}

// ------------------------------------------------------------ domain bits ---
export const SEVERITY_TONE = { Critical: "red", Warning: "amber", Info: "neutral" } as const;

/**
 * Category styling as complete, static Tailwind class strings. (Never build
 * class names like `bg-${color}-500`: Tailwind only ships classes it can
 * find written out in full in the source.)
 */
export interface CategoryStyle { dot: string; bar: string; chip: string }
export const CATEGORY_STYLE: Record<string, CategoryStyle> = {
  "Core · Econ at NU": { dot: "bg-orange-600", bar: "bg-orange-600", chip: "bg-orange-600/15 text-orange-700 ring-orange-600/30 dark:text-orange-300" },
  "Core · Principles": { dot: "bg-amber-500", bar: "bg-amber-500", chip: "bg-amber-500/15 text-amber-700 ring-amber-500/30 dark:text-amber-300" },
  "Core · Follow-up": { dot: "bg-violet-500", bar: "bg-violet-500", chip: "bg-violet-500/15 text-violet-700 ring-violet-500/30 dark:text-violet-300" },
  "Core · Capstone": { dot: "bg-blue-500", bar: "bg-blue-500", chip: "bg-blue-500/15 text-blue-700 ring-blue-500/30 dark:text-blue-300" },
  Recitation: { dot: "bg-emerald-500", bar: "bg-emerald-500", chip: "bg-emerald-500/15 text-emerald-700 ring-emerald-500/30 dark:text-emerald-300" },
  Elective: { dot: "bg-cyan-500", bar: "bg-cyan-500", chip: "bg-cyan-500/15 text-cyan-700 ring-cyan-500/30 dark:text-cyan-300" },
};
const FALLBACK_STYLE: CategoryStyle = { dot: "bg-zinc-400", bar: "bg-zinc-400", chip: "bg-zinc-500/15 text-zinc-600 ring-zinc-500/30 dark:text-zinc-300" };
export const CATEGORIES = Object.keys(CATEGORY_STYLE);
export const categoryStyle = (category: string) => CATEGORY_STYLE[category] ?? FALLBACK_STYLE;

export function CategoryDot({ category }: { category: string }) {
  return <span className={cx("inline-block h-2 w-2 shrink-0 rounded-sm", categoryStyle(category).dot)} />;
}

/** Northeastern brand mark: graduation cap on a Northeastern Red tile (same artwork as /favicon.svg). */
export function BrandMark({ size = 28 }: { size?: number }) {
  return (
    <span className="inline-flex shrink-0 items-center justify-center rounded-[22%] bg-nu text-white" style={{ width: size, height: size }} aria-hidden>
      <GraduationCap style={{ width: size * 0.64, height: size * 0.64 }} strokeWidth={2.1} />
    </span>
  );
}
