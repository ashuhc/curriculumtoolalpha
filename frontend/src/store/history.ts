// Undo / Redo for Term Schedule edits (added, edited, cap-raised, deleted and reverted sections).
// Each entry stores before/after snapshots of the affected section IDs; undoing restores the
// "before" snapshot on the server, guarded by the "after" snapshot so a section another scheduler
// changed in the meantime is never overwritten (the server answers 409 and the entry is dropped).
// Kept per browser tab (sessionStorage), so a page refresh doesn't lose it.
import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
import { ApiError, api, type SectionState } from "../api";
import { useDemand } from "./demand";
import { usePlan } from "./plan";
import { useSchedule } from "./schedule";
import { useUI } from "./ui";

export interface HistoryEntry { id: number; label: string; detail: string; before: SectionState[]; after: SectionState[] }
interface Stack { undo: HistoryEntry[]; redo: HistoryEntry[] }
interface HistoryState {
  stacks: Record<string, Stack>;
  busy: boolean;
  /** Add a finished action (snapshots already known, e.g. from the delete endpoint). Clears Redo. */
  push: (term: string, e: Omit<HistoryEntry, "id">) => void;
  /** Snapshot `ids`, run `mutate`, snapshot again and push the change (also when `mutate` fails part-way). */
  record: <T>(label: string, term: string, ids: string[], mutate: () => Promise<T>, detail?: string) => Promise<T>;
  undo: (term: string) => Promise<void>;
  redo: (term: string) => Promise<void>;
}

const LIMIT = 50;
const EMPTY: Stack = { undo: [], redo: [] };
let nextId = Date.now();

export const isMac = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent);
export const UNDO_KEYS = isMac ? "⌘Z" : "Ctrl+Z";
export const REDO_KEYS = isMac ? "⇧⌘Z" : "Ctrl+Y";

const same = (a: SectionState[], b: SectionState[]) => JSON.stringify(a) === JSON.stringify(b);

async function refresh() {
  await useSchedule.getState().fetch(usePlan.getState().settings, { silent: true });
  useDemand.getState().refresh();
}

export const useHistory = create<HistoryState>()(persist((set, get) => {
  const stack = (term: string) => get().stacks[term] ?? EMPTY;
  const put = (term: string, s: Stack) => set({ stacks: { ...get().stacks, [term]: s } });

  // Shared by Undo and Redo: restore `to`, expecting the section still looks like `from`
  async function step(term: string, dir: "undo" | "redo") {
    const st = stack(term);
    const entry = st[dir][st[dir].length - 1];
    if (!entry || get().busy) return;
    const [to, from] = dir === "undo" ? [entry.before, entry.after] : [entry.after, entry.before];
    const verb = dir === "undo" ? "Undo" : "Redo";
    set({ busy: true });
    try {
      await api.restoreSectionState(term, to.map((state, i) => ({ state, expect: from[i] })));
      const rest = st[dir].slice(0, -1);
      const other = dir === "undo" ? "redo" : "undo";
      put(term, { [dir]: rest, [other]: [...st[other], entry] } as unknown as Stack);
      await refresh();
      useUI.getState().success(`${verb}: ${entry.label}`, entry.detail, to.map((s) => `section:${s.section_id}`));
    } catch (e) {
      const stale = e instanceof ApiError && e.status === 409;
      if (stale) put(term, { ...st, [dir]: st[dir].slice(0, -1) });       // can never apply again
      useUI.getState().toast({ title: `Can't ${verb} ${entry.label}`, tone: "error",
        body: stale ? `${(e as Error).message} This step was removed from the history.` : (e as Error).message });
      if (stale) await refresh();
    } finally { set({ busy: false }); }
  }

  return {
    stacks: {},
    busy: false,
    push: (term, e) => {
      if (same(e.before, e.after)) return;
      const st = stack(term);
      put(term, { undo: [...st.undo, { ...e, id: nextId++ }].slice(-LIMIT), redo: [] });
    },
    record: async (label, term, ids, mutate, detail) => {
      const uniq = [...new Set(ids)];
      let before: SectionState[] | null = null;
      try { before = await api.sectionState(term, uniq); } catch { /* history is best-effort; never block the edit */ }
      const snap = async () => {
        if (!before) return;
        try { get().push(term, { label, detail: detail ?? uniq.join(", "), before, after: await api.sectionState(term, uniq) }); }
        catch { /* ignore */ }
      };
      try {
        const out = await mutate();
        await snap();
        return out;
      } catch (e) {
        await snap();                 // a multi-step save that failed part-way is still undoable
        throw e;
      }
    },
    undo: (term) => step(term, "undo"),
    redo: (term) => step(term, "redo"),
  };
}, {
  name: "econ-schedule-history",
  storage: createJSONStorage(() => sessionStorage),
  partialize: (s) => ({ stacks: s.stacks }) as unknown as HistoryState,
}));
