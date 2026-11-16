// Shared demand-forecast cache: used by the Enrollment Projections page and by the
// Scheduler Assistant (so it can explain the exact numbers on screen).
import { create } from "zustand";
import { api, type DemandResponse, type PlanSettings } from "../api";
import { settingsKey, usePlan } from "./plan";

interface DemandState {
  key: string | null;
  data: DemandResponse | null;
  loading: boolean;
  error: string | null;
  /** Fetch (or reuse) the forecast for these settings; resolves with the data. */
  fetch: (settings: PlanSettings, opts?: { force?: boolean }) => Promise<DemandResponse | null>;
}

let seq = 0;
const cacheKey = (s: PlanSettings) => `${settingsKey(s)}|${usePlan.getState().dataVersion}`;

export const useDemand = create<DemandState>()((set, get) => ({
  key: null,
  data: null,
  loading: false,
  error: null,
  fetch: async (settings, opts = {}) => {
    if (!settings.target_term) return null;
    const key = cacheKey(settings);
    if (!opts.force && get().key === key && get().data) return get().data;
    const id = ++seq;
    set({ loading: true });
    try {
      const data = await api.demand(settings);
      if (id === seq) set({ data, key, error: null });
      return data;
    } catch (e) {
      if (id === seq) set({ error: (e as Error).message });
      return null;
    } finally {
      if (id === seq) set({ loading: false });
    }
  },
}));
