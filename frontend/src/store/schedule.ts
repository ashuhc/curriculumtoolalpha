// Shared term-schedule cache used by Overview, Term Schedule and Conflicts & Audits. Live
// events patch locks/comment counts in place and trigger silent refetches.
import { create } from "zustand";
import { api, type Lock, type PlanSettings, type ScheduleResponse } from "../api";
import { settingsKey } from "./plan";

interface ScheduleState {
  key: string | null;
  data: ScheduleResponse | null;
  loading: boolean;
  error: string | null;
  fetch: (settings: PlanSettings, opts?: { silent?: boolean }) => Promise<void>;
  applyLock: (term: string, sectionId: string, lock: Lock | null) => void;
  bumpComments: (term: string, sectionId: string, delta: number) => void;
}

let seq = 0;

export const useSchedule = create<ScheduleState>()((set, get) => ({
  key: null,
  data: null,
  loading: false,
  error: null,
  fetch: async (settings, opts = {}) => {
    if (!settings.target_term) return;
    const key = settingsKey(settings);
    const id = ++seq;
    if (!opts.silent) set({ loading: true, key });
    try {
      const data = await api.schedule(settings);
      if (id === seq) set({ data, error: null, key });
    } catch (e) {
      if (id === seq) set({ error: (e as Error).message });
    } finally {
      if (id === seq) set({ loading: false });
    }
  },
  applyLock: (term, sectionId, lock) => {
    const d = get().data;
    if (!d || d.term !== term) return;
    const locks = d.locks.filter((l) => l.section_id !== sectionId);
    set({ data: { ...d, locks: lock ? [...locks, lock] : locks } });
  },
  bumpComments: (term, sectionId, delta) => {
    const d = get().data;
    if (!d || d.term !== term) return;
    const n = Math.max(0, (d.comment_counts[sectionId] ?? 0) + delta);
    set({ data: { ...d, comment_counts: { ...d.comment_counts, [sectionId]: n } } });
  },
}));
