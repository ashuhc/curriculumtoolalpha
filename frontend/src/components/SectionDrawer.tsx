// Section detail drawer: details, lock-to-edit workflow, conflicts and threaded comments.
import { Check, CornerDownRight, Lock, LockOpen, Pencil, RotateCcw, Trash2, Unlock } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Comment, type MasterRow, type Meta, type ScheduleResponse } from "../api";
import { fmtDate } from "../lib/hooks";
import { useAuth, useIsAdmin } from "../store/auth";
import { useCollab } from "../store/collab";
import { usePlan } from "../store/plan";
import { useUI } from "../store/ui";
import { Alert, Avatar, Badge, Button, CategoryDot, Drawer, Field, SEVERITY_TONE, cx, inputCls, textareaCls } from "./ui";

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[130px_1fr] gap-3 py-1.5 text-[13px]">
      <dt className="text-muted">{label}</dt><dd className="min-w-0">{children}</dd>
    </div>
  );
}

export function SectionDrawer({ row, data, meta, onClose, onChanged }: {
  row: MasterRow | null; data: ScheduleResponse; meta: Meta; onClose: () => void; onChanged: () => void;
}) {
  const term = usePlan((s) => s.settings.target_term);
  const me = useAuth((s) => s.user);
  const isAdmin = useIsAdmin();
  const toast = useUI((s) => s.toast);
  const { presence, sendPresence, onComment } = useCollab();
  const [busy, setBusy] = useState(false);
  const [override, setOverride] = useState<{ instructor: string | null; sequence: string | null } | null>(null);
  const [comments, setComments] = useState<Comment[]>([]);
  const [draft, setDraft] = useState("");
  const [replyTo, setReplyTo] = useState<number | null>(null);
  const [showResolved, setShowResolved] = useState(false);

  const sid = row?.section_id ?? null;
  const lock = data.locks.find((l) => l.section_id === sid) ?? null;
  const mine = !!lock && lock.user_id === me?.id;
  const conflicts = useMemo(() => data.conflicts.filter((c) => sid && c.course_section.includes(sid)), [data, sid]);
  const viewers = presence.filter((p) => p.section_id === sid && p.id !== me?.id && p.term === term);

  // Presence + comments for the open section; live comment events stream in
  useEffect(() => {
    if (!sid) return;
    sendPresence({ section_id: sid });
    api.comments(term, sid).then(setComments).catch(() => setComments([]));
    const off = onComment((action, c) => {
      if (c.section_id !== sid && action !== "deleted") return;
      setComments((list) => action === "deleted" ? list.filter((x) => x.id !== c.id)
        : action === "updated" ? list.map((x) => (x.id === c.id ? c : x))
        : list.some((x) => x.id === c.id) ? list : [...list, c]);
    });
    return () => { off(); sendPresence({ section_id: null }); };
  }, [sid, term, sendPresence, onComment]);

  // Load the stored override when we start editing so changing one field keeps the other
  useEffect(() => {
    if (!mine || !sid) return;
    api.overrides(term).then((list) => {
      const o = list.find((x) => x.section_id === sid);
      setOverride(o ? { instructor: o.instructor, sequence: o.sequence } : { instructor: null, sequence: null });
    }).catch(() => setOverride({ instructor: null, sequence: null }));
  }, [mine, sid, term]);

  if (!row) return null;
  const fail = (e: unknown) => toast({ title: "Action failed", body: (e as Error).message, tone: "error" });

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    try { await fn(); } catch (e) { fail(e); } finally { setBusy(false); }
  };
  const close = () => {
    if (mine) api.unlock(term, row.section_id).catch(() => undefined);
    onClose();
  };
  const edit = (field: "instructor" | "sequence", value: string) => run(async () => {
    const next = { instructor: override?.instructor ?? null, sequence: override?.sequence ?? null, [field]: value };
    await api.setOverride({ term, section_id: row.section_id, ...next });
    setOverride(next);
    onChanged();
  });
  const isOverridden = data.overridden.includes(row.section_id);
  const seqGroups = [
    ["Class sequences (1–5, A–H)", Object.values(meta.sequences.class)],
    ["Recitation slots (lab windows)", Object.values(meta.sequences.recitation)],
    ["Lab / studio sequences (L–W)", Object.values(meta.sequences.lab)],
  ] as const;

  const roots = comments.filter((c) => !c.parent_id && (showResolved || !c.resolved));
  const replies = (id: number) => comments.filter((c) => c.parent_id === id);
  const resolvedCount = comments.filter((c) => !c.parent_id && c.resolved).length;

  const post = () => run(async () => {
    const c = await api.addComment({ term, section_id: row.section_id, body: draft, parent_id: replyTo });
    setComments((list) => (list.some((x) => x.id === c.id) ? list : [...list, c]));
    setDraft("");
    setReplyTo(null);
  });

  return (
    <Drawer open onClose={close} title={<span className="flex items-center gap-2"><CategoryDot category={row.category} />{row.section_id}</span>}
      subtitle={`${row.title} · ${row.category} · ${row.modality}`}>
      {/* Collaboration status */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-3">
        <div className="flex items-center gap-2 text-xs text-muted">
          {lock ? (
            <span className={cx("flex items-center gap-1.5", mine ? "text-emerald-600" : "text-amber-500")}>
              <Lock className="h-3.5 w-3.5" />{mine ? "You are editing this section" : `Locked by ${lock.user_name}`}
            </span>
          ) : <span className="flex items-center gap-1.5"><LockOpen className="h-3.5 w-3.5" />Unlocked</span>}
          {viewers.length > 0 && (
            <span className="ml-2 flex items-center gap-1.5">
              <span className="flex -space-x-1">{viewers.map((v) => <Avatar key={v.id} name={v.name} size={18} ring />)}</span>
              {viewers.length === 1 ? `${viewers[0].name} is viewing` : `${viewers.length} others viewing`}
            </span>
          )}
        </div>
        {isAdmin && (
          lock && !mine ? (
            <Button size="sm" variant="danger" icon={<Unlock className="h-3.5 w-3.5" />} loading={busy}
              onClick={() => confirm(`Break ${lock.user_name}'s lock on ${row.section_id}?`) && run(() => api.unlock(term, row.section_id))}>Break lock</Button>
          ) : mine ? (
            <Button size="sm" variant="primary" icon={<Check className="h-3.5 w-3.5" />} loading={busy}
              onClick={() => run(() => api.unlock(term, row.section_id))}>Done editing</Button>
          ) : (
            <Button size="sm" icon={<Pencil className="h-3.5 w-3.5" />} loading={busy}
              onClick={() => run(() => api.lock(term, row.section_id))}>Edit section</Button>
          )
        )}
      </div>

      <div className="space-y-6 px-5 py-4">
        {mine && (
          <div className="space-y-3 rounded-md border border-line bg-subtle p-3">
            <Field label="Instructor">
              <select className={inputCls} value={row.instructor} disabled={busy} onChange={(e) => edit("instructor", e.target.value)}>
                {[...new Set([...data.instructors, ...meta.special_instructors, row.instructor])].map((n) => <option key={n}>{n}</option>)}
              </select>
            </Field>
            {!row.modality.startsWith("Online") && (
              <Field label="Sequence" hint="Lectures belong in class sequences; recitations in 65-minute lab-window slots.">
                <select className={inputCls} value={row.sequence} disabled={busy} onChange={(e) => edit("sequence", e.target.value)}>
                  {seqGroups.map(([label, list]) => (
                    <optgroup key={label} label={label}>{list.map((x) => <option key={x.code} value={x.code}>{x.code} — {x.label}</option>)}</optgroup>
                  ))}
                  <option value="UNSCHEDULED">Unscheduled</option>
                </select>
              </Field>
            )}
            {isOverridden && (
              <Button size="sm" variant="ghost" icon={<RotateCcw className="h-3.5 w-3.5" />} loading={busy}
                onClick={() => run(async () => { await api.resetOverrides(term, row.section_id); setOverride({ instructor: null, sequence: null }); onChanged(); })}>
                Revert to generated assignment
              </Button>
            )}
          </div>
        )}

        <dl className="divide-y divide-line">
          <Row label="Instructor"><span className={cx(row.instructor === "UNSTAFFED" && "font-medium text-nu-text")}>{row.instructor}</span>
            <span className="ml-2 text-xs text-muted">{row.faculty_type !== "—" && row.faculty_type}</span></Row>
          <Row label="Assignment basis">{isOverridden ? <Badge tone="amber">Manual edit</Badge> : <span className="text-muted">{row.match_basis}</span>}</Row>
          <Row label="Meeting">{row.meeting_time} <span className="ml-1 text-xs text-muted">({row.sequence})</span></Row>
          <Row label="Capacity"><span className="tabular-nums">{row.projected_enrollment} projected / {row.section_cap} seats</span></Row>
          {row.linked_lecture && <Row label="Linked lecture">{row.linked_lecture}</Row>}
          <Row label="Prerequisites"><span className="text-muted">{row.prerequisites}</span></Row>
        </dl>

        {conflicts.length > 0 && (
          <div className="space-y-2">
            <h3 className="text-xs font-medium text-muted">Conflicts</h3>
            {conflicts.map((c, i) => (
              <div key={i} className="rounded-md border border-line px-3 py-2 text-[13px]">
                <div className="flex items-center gap-2"><Badge tone={SEVERITY_TONE[c.severity]}>{c.severity}</Badge><span className="font-medium">{c.category}</span></div>
                <p className="mt-1 text-muted">{c.details}</p>
                <p className="mt-0.5 text-xs text-faint">{c.suggested_action}</p>
              </div>
            ))}
          </div>
        )}

        <div>
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-xs font-medium text-muted">Discussion</h3>
            {resolvedCount > 0 && (
              <button className="text-xs text-muted hover:text-fg" onClick={() => setShowResolved(!showResolved)}>
                {showResolved ? "Hide" : "Show"} {resolvedCount} resolved
              </button>
            )}
          </div>
          {roots.length === 0 && <p className="py-2 text-[13px] text-faint">No open threads on this section.</p>}
          <div className="space-y-3">
            {roots.map((c) => (
              <div key={c.id} className={cx("rounded-md border border-line", c.resolved && "opacity-60")}>
                <CommentItem c={c} canModify={!!me && (me.id === c.user_id || isAdmin)}
                  onResolve={() => run(async () => { await api.updateComment(c.id, { resolved: !c.resolved }); })}
                  onDelete={() => run(async () => { await api.deleteComment(c.id); setComments((l) => l.filter((x) => x.id !== c.id && x.parent_id !== c.id)); })}
                  onReply={me ? () => setReplyTo(c.id) : undefined} />
                {replies(c.id).map((r) => (
                  <div key={r.id} className="border-t border-line pl-6">
                    <CommentItem c={r} reply canModify={!!me && (me.id === r.user_id || isAdmin)}
                      onDelete={() => run(async () => { await api.deleteComment(r.id); setComments((l) => l.filter((x) => x.id !== r.id)); })} />
                  </div>
                ))}
              </div>
            ))}
          </div>
          {me ? (
            <div className="mt-3 space-y-2">
              {replyTo && (
                <div className="flex items-center gap-2 text-xs text-muted">
                  <CornerDownRight className="h-3.5 w-3.5" />Replying to {comments.find((c) => c.id === replyTo)?.author_name}
                  <button className="underline" onClick={() => setReplyTo(null)}>Cancel</button>
                </div>
              )}
              <textarea className={textareaCls + " min-h-20"} placeholder={replyTo ? "Write a reply" : "Start a thread about this section"}
                value={draft} onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && draft.trim()) post(); }} />
              <div className="flex items-center justify-between">
                <span className="text-[11px] text-faint">⌘ Enter to post · visible to everyone on the schedule</span>
                <Button size="sm" variant="primary" disabled={!draft.trim()} loading={busy} onClick={post}>{replyTo ? "Reply" : "Comment"}</Button>
              </div>
            </div>
          ) : (
            <Alert>
              <Link to="/login" className="font-medium text-fg underline">Sign in</Link> to join the discussion.
            </Alert>
          )}
        </div>
      </div>
    </Drawer>
  );
}

function CommentItem({ c, reply, canModify, onResolve, onDelete, onReply }: {
  c: Comment; reply?: boolean; canModify: boolean; onResolve?: () => void; onDelete: () => void; onReply?: () => void;
}) {
  return (
    <div className="group px-3 py-2.5">
      <div className="flex items-center gap-2">
        <Avatar name={c.author_name} size={20} />
        <span className="text-[13px] font-medium">{c.author_name}</span>
        <span className="text-[11px] text-faint">{fmtDate(c.created_at)}</span>
        {c.resolved && <Badge tone="green">Resolved</Badge>}
      </div>
      <p className="mt-1.5 whitespace-pre-wrap text-[13px] leading-relaxed">{c.body}</p>
      <div className="mt-1.5 flex gap-3 text-xs text-muted">
        {onReply && !reply && <button className="hover:text-fg" onClick={onReply}>Reply</button>}
        {canModify && onResolve && !reply && <button className="hover:text-fg" onClick={onResolve}>{c.resolved ? "Reopen" : "Resolve"}</button>}
        {canModify && <button className="opacity-0 hover:text-nu-text group-hover:opacity-100" onClick={onDelete} aria-label="Delete"><Trash2 className="h-3.5 w-3.5" /></button>}
      </div>
    </div>
  );
}
