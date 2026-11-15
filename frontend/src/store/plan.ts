// Planning settings shared by every view (persisted), reference metadata, and a
// data-version counter bumped by live "data changed" events.
import { create } from "zustand";
import { persist } from "zustand/middleware";
import { api, type Meta, type PlanSettings } from "../api";

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
      update: (patch) => set({ settings: { ...get().settings, ...patch } }),
      reset: () => set({ settings: { ...DEFAULT_SETTINGS, target_term: get().settings.target_term } }),
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
    { name: "econ-plan-settings", partialize: (s) => ({ settings: { ...DEFAULT_SETTINGS, ...s.settings } }) },
  ),
);

export const settingsKey = (s: PlanSettings) => JSON.stringify(s);
