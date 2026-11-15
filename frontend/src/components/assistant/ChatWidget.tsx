// Floating site assistant (bottom-right). Rule-based intents over this app's
// own documentation + live data — no external AI service or API key required.
import { ArrowUp, MessageSquare, RotateCcw, X } from "lucide-react";
import { Fragment, useEffect, useRef, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { api, type Course } from "../../api";
import { useAuth } from "../../store/auth";
import { usePlan } from "../../store/plan";
import { useSchedule } from "../../store/schedule";
import { useUI } from "../../store/ui";
import { IconButton, cx } from "../ui";
import { STARTER_PROMPTS, answer, type Answer } from "./knowledge";

interface Msg { role: "user" | "assistant"; text: string; links?: Answer["links"] }

const GREETING: Msg = {
  role: "assistant",
  text: "Hi, I'm the scheduler assistant. I can explain planning settings, metrics like seat fill, how recitations and time slots work, and how to submit preferences or resolve conflicts.",
};

/** Minimal formatting: **bold**, line breaks and bullet lines. */
function Rich({ text }: { text: string }) {
  return (
    <>
      {text.split("\n").map((line, i) => {
        const parts: ReactNode[] = line.split(/(\*\*[^*]+\*\*|\*[^*]+\*)/g).map((p, j) =>
          p.startsWith("**") ? <strong key={j} className="font-semibold">{p.slice(2, -2)}</strong>
            : p.startsWith("*") && p.length > 2 ? <em key={j}>{p.slice(1, -1)}</em> : <Fragment key={j}>{p}</Fragment>);
        return line.trim() === "" ? <div key={i} className="h-2" /> : <div key={i} className={cx(/^[•\d]/.test(line) && "pl-1")}>{parts}</div>;
      })}
    </>
  );
}

export function ChatWidget() {
  const open = useUI((s) => s.chatOpen);
  const setOpen = useUI((s) => s.setChatOpen);
  const settings = usePlan((s) => s.settings);
  const schedule = useSchedule((s) => s.data);
  const role = useAuth((s) => s.user?.role ?? null);
  const navigate = useNavigate();
  const [msgs, setMsgs] = useState<Msg[]>([GREETING]);
  const [input, setInput] = useState("");
  const [courses, setCourses] = useState<Course[] | null>(null);
  const [typing, setTyping] = useState(false);
  const scroller = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open && !courses) api.courses().then(setCourses).catch(() => undefined);
    if (open) setTimeout(() => inputRef.current?.focus(), 50);
  }, [open, courses]);
  useEffect(() => { scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" }); }, [msgs, typing]);

  const ask = (q: string) => {
    const text = q.trim();
    if (!text) return;
    setInput("");
    setMsgs((m) => [...m, { role: "user", text }]);
    setTyping(true);
    // Short pause so the reply reads as a response rather than an instant swap
    setTimeout(() => {
      const a = answer(text, { settings, schedule, courses, role });
      setMsgs((m) => [...m, { role: "assistant", text: a.text, links: a.links }]);
      setTyping(false);
    }, 280);
  };

  const asked = new Set(msgs.filter((m) => m.role === "user").map((m) => m.text));
  const chips = STARTER_PROMPTS.filter((p) => !asked.has(p)).slice(0, 3);

  return (
    <>
      {!open && (
        <button onClick={() => setOpen(true)} aria-label="Open Assistant"
          className="fixed bottom-5 right-5 z-40 flex h-11 items-center gap-2 rounded-full bg-nu pl-3.5 pr-4 text-[13px] font-medium text-white shadow-lg transition-colors hover:bg-nu-hover">
          <MessageSquare className="h-4 w-4" /> Ask the Assistant
        </button>
      )}
      {open && (
        <div className="animate-fade-up fixed bottom-5 right-5 z-50 flex h-[580px] max-h-[calc(100vh-40px)] w-[380px] max-w-[calc(100vw-24px)] flex-col overflow-hidden rounded-lg border border-line bg-surface shadow-2xl">
          <header className="flex items-center gap-3 border-b border-line px-4 py-3">
            <div className="flex h-7 w-7 items-center justify-center rounded bg-nu text-white"><MessageSquare className="h-3.5 w-3.5" /></div>
            <div className="flex-1 leading-tight">
              <div className="text-[13px] font-semibold">Scheduler Assistant</div>
              <div className="text-[11px] text-muted">Site Help · Built-In Documentation</div>
            </div>
            <IconButton label="Clear Conversation" onClick={() => setMsgs([GREETING])}><RotateCcw className="h-3.5 w-3.5" /></IconButton>
            <IconButton label="Close Assistant" onClick={() => setOpen(false)}><X className="h-4 w-4" /></IconButton>
          </header>

          <div ref={scroller} className="flex-1 space-y-4 overflow-y-auto px-4 py-4">
            {msgs.map((m, i) => (
              <div key={i} className={cx("flex", m.role === "user" && "justify-end")}>
                <div className={cx("max-w-[88%] text-[13px] leading-relaxed",
                  m.role === "user" ? "rounded-lg rounded-br-sm bg-subtle px-3 py-2" : "text-fg")}>
                  <Rich text={m.text} />
                  {m.links && m.links.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {m.links.map((l) => (
                        <button key={l.to + l.label} onClick={() => { navigate(l.to); }}
                          className="rounded border border-line-strong px-2 py-0.5 text-xs font-medium hover:bg-hover">{l.label} →</button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}
            {typing && <div className="flex gap-1 px-1">{[0, 1, 2].map((i) => <span key={i} className="h-1.5 w-1.5 animate-pulse rounded-full bg-faint" style={{ animationDelay: `${i * 150}ms` }} />)}</div>}
          </div>

          {chips.length > 0 && (
            <div className="flex flex-wrap gap-1.5 border-t border-line px-4 pt-3">
              {chips.map((c) => (
                <button key={c} onClick={() => ask(c)}
                  className="rounded-full border border-line-strong px-2.5 py-1 text-xs text-muted transition-colors hover:border-nu hover:text-fg">{c}</button>
              ))}
            </div>
          )}
          <form className="flex items-center gap-2 px-3 py-3" onSubmit={(e) => { e.preventDefault(); ask(input); }}>
            <input ref={inputRef} value={input} onChange={(e) => setInput(e.target.value)} placeholder="Ask about settings, metrics, courses…"
              className="h-9 flex-1 rounded-md border border-line-strong bg-surface px-3 text-[13px] outline-none placeholder:text-faint focus:border-fg/40" />
            <button type="submit" disabled={!input.trim()} aria-label="Send"
              className="flex h-9 w-9 items-center justify-center rounded-md bg-nu text-white transition-colors hover:bg-nu-hover disabled:opacity-40">
              <ArrowUp className="h-4 w-4" />
            </button>
          </form>
        </div>
      )}
    </>
  );
}
