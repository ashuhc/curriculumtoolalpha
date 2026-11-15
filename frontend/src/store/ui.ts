// Theme, assistant visibility and toast notifications.
import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface Toast { id: number; title: string; body?: string; tone: "info" | "success" | "error"; leaving?: boolean }

/** How long each toast stays up (success confirmations are brief; errors linger so they can be read). */
const DURATION = { success: 3000, info: 4500, error: 6000 } as const;
const FADE_MS = 220;

interface UIState {
  theme: "dark" | "light";
  toggleTheme: () => void;
  chatOpen: boolean;
  setChatOpen: (v: boolean) => void;
  navOpen: boolean;
  setNavOpen: (v: boolean) => void;
  toasts: Toast[];
  toast: (t: Omit<Toast, "id" | "tone" | "leaving"> & { tone?: Toast["tone"] }) => void;
  /** Green confirmation toast, optionally flashing the element(s) registered under `flashKey`. */
  success: (title: string, body?: string, flashKey?: string | string[]) => void;
  dismiss: (id: number) => void;
  /** Keys of elements currently showing the green "just updated" highlight. */
  flashed: Record<string, number>;
  flash: (key: string | string[]) => void;
}

let nextId = 1;

export const useUI = create<UIState>()(
  persist(
    (set, get) => ({
      theme: document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark",
      toggleTheme: () => set({ theme: get().theme === "dark" ? "light" : "dark" }),
      chatOpen: false,
      setChatOpen: (chatOpen) => set({ chatOpen }),
      navOpen: false,
      setNavOpen: (navOpen) => set({ navOpen }),
      toasts: [],
      toast: (t) => {
        const id = nextId++;
        const tone = t.tone ?? "info";
        // Collapse an identical toast that is already showing (e.g. repeated toggles)
        const rest = get().toasts.filter((x) => !(x.title === t.title && x.body === t.body));
        set({ toasts: [...rest.slice(-3), { ...t, tone, id }] });
        setTimeout(() => get().dismiss(id), DURATION[tone]);
      },
      success: (title, body, flashKey) => {
        get().toast({ title, body, tone: "success" });
        if (flashKey) get().flash(flashKey);
      },
      dismiss: (id) => {
        // Fade out, then remove
        set({ toasts: get().toasts.map((t) => (t.id === id ? { ...t, leaving: true } : t)) });
        setTimeout(() => set({ toasts: get().toasts.filter((t) => t.id !== id) }), FADE_MS);
      },
      flashed: {},
      flash: (key) => {
        const keys = Array.isArray(key) ? key : [key];
        const stamp = Date.now();
        set({ flashed: { ...get().flashed, ...Object.fromEntries(keys.map((k) => [k, stamp])) } });
        setTimeout(() => {
          const next = { ...get().flashed };
          keys.forEach((k) => { if (next[k] === stamp) delete next[k]; });
          set({ flashed: next });
        }, 1600);
      },
    }),
    { name: "econ-ui", partialize: (s) => ({ theme: s.theme }) },
  ),
);

// Keep <html data-theme> in sync with the store (including the persisted value at startup)
function applyTheme(theme: "dark" | "light") {
  if (theme === "light") document.documentElement.setAttribute("data-theme", "light");
  else document.documentElement.removeAttribute("data-theme");
}
applyTheme(useUI.getState().theme);
useUI.subscribe((s) => applyTheme(s.theme));

/** Class name for the green "just updated" highlight on an element registered under `key`. */
export function useFlash() {
  const flashed = useUI((s) => s.flashed);
  return (key: string) => (flashed[key] ? "flash-success" : "");
}
