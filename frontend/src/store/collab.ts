// WebSocket connection: presence, live schedule edits, locks, comments, publishes.
import { create } from "zustand";
import { wsUrl, type Comment, type Lock, type Publication } from "../api";
import { useAuth } from "./auth";
import { usePlan } from "./plan";
import { useSchedule } from "./schedule";
import { useUI } from "./ui";

export interface PresenceUser { id: number; name: string; role: string; page?: string | null; term?: string | null; section_id?: string | null }
type CommentListener = (action: string, c: Comment) => void;

interface CollabState {
  status: "connecting" | "online" | "offline";
  presence: PresenceUser[];
  connect: () => void;
  disconnect: () => void;
  sendPresence: (p: { page?: string; term?: string; section_id?: string | null }) => void;
  onComment: (fn: CommentListener) => () => void;
}

let ws: WebSocket | null = null;
let retry = 0;
let retryTimer: ReturnType<typeof setTimeout> | undefined;
let pingTimer: ReturnType<typeof setInterval> | undefined;
let refetchTimer: ReturnType<typeof setTimeout> | undefined;
let lastPresence: Record<string, unknown> = {};
const commentListeners = new Set<CommentListener>();

/** Coalesce bursts of edits into one silent refetch. */
function refetchSoon() {
  clearTimeout(refetchTimer);
  refetchTimer = setTimeout(() => useSchedule.getState().fetch(usePlan.getState().settings, { silent: true }), 250);
}

function handle(msg: Record<string, unknown>) {
  const me = useAuth.getState().user;
  const term = usePlan.getState().settings.target_term;
  const toast = useUI.getState().toast;
  switch (msg.type) {
    case "presence":
      useCollab.setState({ presence: msg.users as PresenceUser[] });
      break;
    case "schedule":
      if (msg.term === term) {
        refetchSoon();
        if (msg.by && msg.by !== me?.name) toast({ title: `${msg.by} updated the schedule`, body: (msg.section_id as string) ?? "Manual edits reset" });
      }
      break;
    case "lock":
      useSchedule.getState().applyLock(msg.term as string, msg.section_id as string, (msg.lock as Lock) ?? null);
      if (msg.broken_by && msg.broken_by !== me?.name) toast({ title: `${msg.broken_by} released a lock`, body: msg.section_id as string });
      break;
    case "comment": {
      const c = msg.comment as Comment;
      if (msg.action === "created" && !c.resolved) useSchedule.getState().bumpComments(msg.term as string, msg.section_id as string, 1);
      if (msg.action === "updated" || msg.action === "deleted") refetchSoon();
      commentListeners.forEach((fn) => fn(msg.action as string, c));
      if (msg.action === "created" && c.user_id !== me?.id && msg.term === term)
        toast({ title: `${c.author_name} commented on ${c.section_id}`, body: c.body.slice(0, 90) });
      break;
    }
    case "data":
      usePlan.getState().bumpData();
      refetchSoon();
      break;
    case "published": {
      const p = msg.publication as Publication;
      if (msg.term === term) refetchSoon();
      toast({ title: `${p.term} schedule published (v${p.version})`, body: `by ${p.published_by}`, tone: "success" });
      break;
    }
  }
}

export const useCollab = create<CollabState>()((set) => ({
  status: "offline",
  presence: [],
  connect: () => {
    clearTimeout(retryTimer);
    if (ws) { ws.onclose = null; ws.close(); }
    set({ status: "connecting" });
    const sock = new WebSocket(wsUrl(useAuth.getState().token));
    ws = sock;
    sock.onopen = () => {
      retry = 0;
      set({ status: "online" });
      if (Object.keys(lastPresence).length) sock.send(JSON.stringify({ type: "presence", ...lastPresence }));
      clearInterval(pingTimer);
      pingTimer = setInterval(() => sock.readyState === WebSocket.OPEN && sock.send('{"type":"ping"}'), 25000);
    };
    sock.onmessage = (e) => { try { handle(JSON.parse(e.data)); } catch { /* ignore malformed */ } };
    sock.onclose = () => {
      clearInterval(pingTimer);
      set({ status: "offline", presence: [] });
      retry = Math.min(retry + 1, 6);
      retryTimer = setTimeout(() => useCollab.getState().connect(), 500 * 2 ** retry);
    };
  },
  disconnect: () => {
    clearTimeout(retryTimer);
    clearInterval(pingTimer);
    if (ws) { ws.onclose = null; ws.close(); ws = null; }
    set({ status: "offline", presence: [] });
  },
  sendPresence: (p) => {
    lastPresence = { ...lastPresence, ...p };
    if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "presence", ...lastPresence }));
  },
  onComment: (fn) => { commentListeners.add(fn); return () => { commentListeners.delete(fn); }; },
}));

// Reconnect with the new identity whenever the user signs in or out
useAuth.subscribe((s, prev) => { if (s.token !== prev.token) useCollab.getState().connect(); });
