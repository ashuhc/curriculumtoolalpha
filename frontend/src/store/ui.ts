// Theme, assistant visibility and toast notifications.
import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface Toast { id: number; title: string; body?: string; tone: "info" | "success" | "error" }

interface UIState {
  theme: "dark" | "light";
  toggleTheme: () => void;
  chatOpen: boolean;
  setChatOpen: (v: boolean) => void;
  navOpen: boolean;
  setNavOpen: (v: boolean) => void;
  toasts: Toast[];
  toast: (t: Omit<Toast, "id" | "tone"> & { tone?: Toast["tone"] }) => void;
  dismiss: (id: number) => void;
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
        set({ toasts: [...get().toasts.slice(-3), { tone: "info", ...t, id }] });
        setTimeout(() => get().dismiss(id), 4500);
      },
      dismiss: (id) => set({ toasts: get().toasts.filter((t) => t.id !== id) }),
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
