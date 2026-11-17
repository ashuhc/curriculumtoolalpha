// Planning settings shared by every view (persisted), reference metadata, and a
// data-version counter bumped by live "data changed" events.
import { create } from "zustand";
import { persist } from "zustand/middleware";
import { api, type Meta, type PlanSettings } from "../api";
import { useUI } from "./ui";

const LABELS: Record<keyof PlanSettings, (v: never) => string> = {
  target_term: (v: string) => `Now planning ${v}`,
  growth_multiplier: (v: number) => `Enrollment growth set to ${v.toFixed(2)}×`,
  history_window: (v: number) => `History window set to ${v} term${v === 1 ? "" : "s"}`,
  apply_trend: (v: boolean) => `Historical trend ${v ? "on" : "off"}`,
  large_lecture_cap: (v: number) => `Large lecture cap set to ${v}`,
  small_section_cap: (v: number) => `Small section cap set to ${v}`,
  virtual_cap: (v: number) => `Remote section cap set to ${v}`,
  recitation_cap: (v: number) => `Recitation cap set to ${v}`,
  min_elective_demand: (v: number) => `Minimum elective enrollment set to ${v}`,
  history_fallback: (v: boolean) => `Teaching-history matching ${v ? "on" : "off"}`,
  force_fill_core: (v: boolean) => `Force-fill unstaffed core ${v ? "on" : "off"}`,
  recitation_leader_load: (v: number) => `Recitations per leader set to ${v}`,
};

let pendingSince: PlanSettings | null = null;
let confirmTimer: ReturnType<typeof setTimeout> | undefined;

/** Confirm settings changes once the user stops adjusting (no toast per slider tick). */
function confirmSettings(before: PlanSettings, getAfter: () => PlanSettings, reset = false) {
  pendingSince = pendingSince ?? before;
  clearTimeout(confirmTimer);
  confirmTimer = setTimeout(() => {
    const from = pendingSince!;
    pendingSince = null;
    const after = getAfter();
    const changed = (Object.keys(LABELS) as (keyof PlanSettings)[]).filter((k) => from[k] !== after[k]);
    if (!changed.length) return;
    const ui = useUI.getState();
    const lines = changed.map((k) => (LABELS[k] as (v: unknown) => string)(after[k]));
    const termOnly = changed.length === 1 && changed[0] === "target_term";
    ui.success(reset ? "Planning settings reset to defaults" : termOnly ? lines[0] : "Planning settings saved",
      reset || termOnly ? (termOnly ? "Forecast, schedule and conflicts updated" : undefined) : lines.join(" · "), "settings");
  }, 700);
}

export const DEFAULT_SETTINGS: PlanSettings = {
  target_term: "", growth_multiplier: 1.0, history_window: 3, apply_trend: true, large_lecture_cap: 200,
  small_section_cap: 45, virtual_cap: 25, recitation_cap: 30, min_elective_demand: 15, history_fallback: true,
  force_fill_core: false, recitation_leader_load: 5,
};

interface PlanState {
  settings: PlanSettings;
  update: (patch: Partial<PlanSettings>) => void;
  reset: () => void;
  meta: Meta | null;
  metaError: string | null;
  loadMeta: () => Promise<void>;
  dataVersion: number;
  bumpData: () => void;
}

export const usePlan = create<PlanState>()(
  persist(
    (set, get) => ({
      settings: DEFAULT_SETTINGS,
      update: (patch) => {
        const before = get().settings;
        set({ settings: { ...before, ...patch } });
        confirmSettings(before, () => get().settings);
      },
      reset: () => {
        const before = get().settings;
        set({ settings: { ...DEFAULT_SETTINGS, target_term: before.target_term } });
        confirmSettings(before, () => get().settings, true);
      },
      meta: null,
      metaError: null,
      loadMeta: async () => {
        try {
          const meta = await api.meta();
          const all = [...meta.terms.upcoming, ...meta.terms.historical];
          const s = get().settings;
          set({ meta, metaError: null, settings: all.includes(s.target_term) ? s : { ...s, target_term: meta.terms.default } });
        } catch (e) {
          set({ metaError: (e as Error).message });
        }
      },
      dataVersion: 0,
      bumpData: () => set({ dataVersion: get().dataVersion + 1 }),
    }),
    {
      name: "econ-plan-settings",
      partialize: (s) => ({ settings: { ...DEFAULT_SETTINGS, ...s.settings } }),
      // Saved settings from an older version may lack newer fields: fill them from the defaults
      merge: (persisted, current) => ({
        ...current,
        settings: { ...DEFAULT_SETTINGS, ...((persisted as { settings?: Partial<PlanSettings> } | undefined)?.settings ?? {}) },
      }),
    },
  ),
);

export const settingsKey = (s: PlanSettings) => JSON.stringify(s);
