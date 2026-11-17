// Term Schedule: grid + weekly calendar with live collaboration, section drawer, publishing.
import { AlertTriangle, BookOpen, CalendarRange, Download, FileCheck2, LayoutList, Lock, MessageSquare, PencilLine, Plus, RotateCcw, Search, Send, ShieldCheck, Target, TriangleAlert } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, type ManualSection, type ScheduleResponse } from "../api";
import { SectionDrawer } from "../components/SectionDrawer";
import { SectionEditor, type SectionPrefill } from "../components/SectionEditor";
import { SettingsPanel } from "../components/SettingsPanel";
import { WeekCalendar } from "../components/WeekCalendar";
import {
  Alert, Badge, Button, CATEGORIES, CategoryDot, ConfirmDialog, ErrorState, Field, Modal, PageHeader, Panel, Segmented, Spinner, Stat, StatGrid, Switch, Table,
  cx, inputBase, textareaCls,
} from "../components/ui";
import { fmtDate, useDebounced } from "../lib/hooks";
import { titleCase } from "../lib/text";
import { useAuth, useIsAdmin } from "../store/auth";
import { usePlan } from "../store/plan";
import { useSchedule } from "../store/schedule";
import { useFlash, useUI } from "../store/ui";

/** Section IDs referenced by Critical/Warning conflicts. */
export function flaggedSections(data: ScheduleResponse | null): Set<string> {
  const out = new Set<string>();
  for (const c of data?.conflicts ?? [])
    if (c.severity !== "Info") for (const m of c.course_section.matchAll(/ECON \d{4}-\d{2}/g)) out.add(m[0]);
  return out;
}

export default function Schedule() {
  const { settings, meta, dataVersion } = usePlan();
  const { data, loading, error, fetch } = useSchedule();
  const isAdmin = useIsAdmin();
  const toast = useUI((s) => s.toast);
  const success = useUI((s) => s.success);
  const flash = useFlash();
  const s = useDebounced(settings);
  const [params, setParams] = useSearchParams();
  const [view, setView] = useState<"grid" | "calendar">("grid");
  const [q, setQ] = useState("");
  const [cat, setCat] = useState("");
  const [inst, setInst] = useState("");
  const [onlyFlagged, setOnlyFlagged] = useState(false);
  const [publishOpen, setPublishOpen] = useState(false);
  const openId = params.get("section");
  const me = useAuth((st) => st.user);
  // Sections whose revert is in flight: the badge clears immediately, the refetch settles it
  const [reverting, setReverting] = useState<Set<string>>(new Set());
  const [revertAllOpen, setRevertAllOpen] = useState(false);
  const [revertAllBusy, setRevertAllBusy] = useState(false);
  const [editor, setEditor] = useState<{ prefill?: SectionPrefill; editing?: ManualSection | null } | null>(null);

  useEffect(() => { fetch(s); }, [s, dataVersion, fetch]);

  const flagged = useMemo(() => flaggedSections(data), [data]);
  const locked = useMemo(() => new Map((data?.locks ?? []).map((l) => [l.section_id, l.user_name])), [data]);
  const overridden = useMemo(() => new Set(data?.overridden ?? []), [data]);
  const manualById = useMemo(() => new Map((data?.manual_sections ?? []).map((m) => [m.section_id, m])), [data]);
  const lockOwner = useMemo(() => new Map((data?.locks ?? []).map((l) => [l.section_id, l])), [data]);
  const lockedByOther = (id: string) => { const l = lockOwner.get(id); return l && l.user_id !== me?.id ? l.user_name : null; };

  const revertOne = async (id: string) => {
    if (reverting.has(id)) return;
    setReverting((cur) => new Set(cur).add(id));
    try {
      await api.resetOverrides(settings.target_term, id);
      await fetch(settings, { silent: true });
      success("Reverted to generated assignment", id, `section:${id}`);
    } catch (e) {
      toast({ title: "Revert failed", body: (e as Error).message, tone: "error" });
    } finally {
      setReverting((cur) => { const n = new Set(cur); n.delete(id); return n; });
    }
  };
  const revertAll = async () => {
    setRevertAllBusy(true);
    try {
      const r = await api.resetOverrides(settings.target_term);
      await fetch(settings, { silent: true });
      setRevertAllOpen(false);
      if (r.reverted.length)
        success("All manual edits reverted", `${r.reverted.length} section${r.reverted.length === 1 ? "" : "s"} back to the generated schedule`, r.reverted.map((id) => `section:${id}`));
      if (r.skipped.length)
        toast({ title: `${r.skipped.length} section${r.skipped.length === 1 ? "" : "s"} skipped`, tone: "info",
          body: r.skipped.map((x) => `${x.section_id} (being edited by ${x.locked_by})`).join(", ") });
    } catch (e) {
      toast({ title: "Revert failed", body: (e as Error).message, tone: "error" });
    } finally { setRevertAllBusy(false); }
  };
  const rows = useMemo(() => (data?.master ?? []).filter((r) =>
    (!q || `${r.section_id} ${r.title} ${r.instructor}`.toLowerCase().includes(q.toLowerCase())) &&
    (!cat || r.category === cat) && (!inst || r.instructor === inst) && (!onlyFlagged || flagged.has(r.section_id))),
  [data, q, cat, inst, onlyFlagged, flagged]);
  const openRow = data?.master.find((r) => r.section_id === openId) ?? null;
  const open = (id: string | null) => setParams(id ? { section: id } : {}, { replace: true });
  const exportKind = (k: "master" | "catalog") => api.exportPlan(k, settings)
    .then(() => success(k === "master" ? "Term schedule exported" : "Catalog CSV downloaded", `${settings.target_term} · current schedule`))
    .catch((e) => toast({ title: "Export failed", body: e.message, tone: "error" }));
  const sm = data?.summary;
  const pub = data?.publication;

  return (
    <>
      <PageHeader eyebrow="Planning" title="Term Schedule"
        description="Assign faculty and time slots across standard lecture sequences (1–5, A–H) and recitation windows (L–W), prioritizing core requirements."
        meta={pub && <><Badge tone="green"><FileCheck2 className="h-3 w-3" />Published v{pub.version}</Badge><span>{fmtDate(pub.published_at)} by {pub.published_by}{pub.note && ` · “${pub.note}”`}</span></>}
        actions={<>
          <Button icon={<Download className="h-3.5 w-3.5" />} onClick={() => exportKind("master")}>Export CSV</Button>
          <Button icon={<Download className="h-3.5 w-3.5" />} onClick={() => (pub ? api.exportPublication(pub.id) : api.exportPlan("catalog", settings))
            .then(() => success("Catalog CSV downloaded", pub ? `${pub.term} · published v${pub.version}` : `${settings.target_term} · current schedule`))
            .catch((e) => toast({ title: "Export failed", body: e.message, tone: "error" }))}
            title={pub ? `Catalog import file for published v${pub.version}` : "Catalog import file for the current schedule"}>Catalog CSV</Button>
          {isAdmin && <Button variant="primary" icon={<Send className="h-3.5 w-3.5" />} onClick={() => setPublishOpen(true)} disabled={!data}>Publish</Button>}
        </>} />

      <div className="space-y-6">
        <SettingsPanel mode="schedule" defaultOpen={false} />
        {error && <ErrorState error={error} onRetry={() => fetch(settings)} />}
        {!data && loading && <Spinner label="Matching faculty and assigning time blocks" />}
        {data && meta && sm && (
          <>
            <div className={cx("transition-opacity", loading && "opacity-60")}>
              <StatGrid cols={6}>
                <Stat icon={CalendarRange} label="Sections" value={sm.sections} />
                <Stat icon={ShieldCheck} iconTone={sm.core_staffed < sm.core_sections ? "warning" : "primary"} label="Core Staffed" value={`${sm.core_staffed}/${sm.core_sections}`} tone={sm.core_staffed < sm.core_sections ? "danger" : undefined} />
                <Stat icon={BookOpen} label="Electives Offered" value={sm.electives_offered} />
                <Stat icon={Target} label="Top-3 Preference Matches" value={sm.preference_matches} sub={`${sm.submissions} form submission${sm.submissions === 1 ? "" : "s"}`} />
                <Stat icon={AlertTriangle} iconTone="warning" label="Critical · Warnings" value={`${sm.critical} · ${sm.warning}`} tone={sm.critical ? "danger" : sm.warning ? "warning" : undefined} />
                <Stat icon={PencilLine} iconTone="neutral" label="Manual Edits" value={sm.overrides_applied} sub={sm.overrides_stale.length ? `${sm.overrides_stale.length} no longer match a section` : `${data.locks.length} section${data.locks.length === 1 ? "" : "s"} locked`} />
              </StatGrid>
            </div>
            {sm.submissions === 0 && settings.history_fallback && (
              <Alert>No preference forms submitted yet, so faculty are matched on teaching history. <Link to="/preferences" className="font-medium text-fg underline">Teaching Preferences</Link></Alert>
            )}

            <Panel flush
              title={<Segmented value={view} onChange={setView} options={[
                { id: "grid", label: <><LayoutList className="h-3.5 w-3.5" />Grid</> },
                { id: "calendar", label: <><CalendarRange className="h-3.5 w-3.5" />Weekly Calendar</> }]} />}
              actions={<>
                <div className="relative"><Search className="absolute left-2.5 top-2 h-4 w-4 text-faint" />
                  <input className={inputBase + " w-56 pl-8"} placeholder="Section, title or instructor" value={q} onChange={(e) => setQ(e.target.value)} /></div>
                <select className={inputBase + " w-40"} value={cat} onChange={(e) => setCat(e.target.value)}>
                  <option value="">All Categories</option>{CATEGORIES.map((c) => <option key={c}>{c}</option>)}
                </select>
                <select className={inputBase + " w-48"} value={inst} onChange={(e) => setInst(e.target.value)}>
                  <option value="">All Instructors</option>{[...new Set(data.master.map((r) => r.instructor))].sort().map((n) => <option key={n}>{n}</option>)}
                </select>
                <Switch checked={onlyFlagged} onChange={setOnlyFlagged} label="Conflicts Only" />
                {isAdmin && (
                  <Button size="sm" variant="primary" icon={<Plus className="h-3.5 w-3.5" />} onClick={() => setEditor({})}
                    title="Add a Section by Hand">Add Section</Button>
                )}
                {isAdmin && sm.overrides_applied > 0 && (
                  <Button size="sm" icon={<RotateCcw className="h-3.5 w-3.5" />} onClick={() => setRevertAllOpen(true)}
                    title="Revert Every Manual Edit for This Term">Revert All Edits</Button>
                )}
              </>}>
              {view === "calendar" ? (
                <div className="p-4"><WeekCalendar rows={rows} meta={meta} flagged={flagged} locked={locked} comments={data.comment_counts} onOpen={open} /></div>
              ) : (
                <Table>
                  <thead><tr>
                    <th>Section</th><th>Title</th><th>Instructor</th><th>Assignment</th><th>Seq.</th><th>Meeting Time</th>
                    <th className="text-right">Proj. / Cap</th><th>Modality</th><th className="w-20" />
                  </tr></thead>
                  <tbody>
                    {rows.map((r) => (
                      <tr key={r.section_id} onClick={() => open(r.section_id)}
                        className={cx("cursor-pointer hover:bg-hover", openId === r.section_id && "bg-hover", flash(`section:${r.section_id}`))}>
                        <td className="whitespace-nowrap"><span className="flex items-center gap-2 font-medium tabular-nums"><CategoryDot category={r.category} />{r.section_id}</span></td>
                        <td className="min-w-44 text-muted">{r.title}</td>
                        <td className="whitespace-nowrap">
                          <span className={cx(r.instructor === "UNSTAFFED" && "font-medium text-nu-text")}>{r.instructor}</span>
                          {r.faculty_type !== "—" && <div className="text-[11px] text-faint">{r.faculty_type}</div>}
                        </td>
                        <td className="text-xs">
                          {reverting.has(r.section_id) ? <span className="text-faint">Reverting…</span>
                            : overridden.has(r.section_id) ? (
                              <span className="flex items-center gap-1">
                                <Badge tone="amber">Manual Edit</Badge>
                                {isAdmin && (() => {
                                  const by = lockedByOther(r.section_id);
                                  return (
                                    <button type="button" aria-label={`Revert ${r.section_id}`} disabled={!!by}
                                      title={by ? `Locked by ${by}` : "Revert to Generated Assignment"}
                                      onClick={(e) => { e.stopPropagation(); revertOne(r.section_id); }}
                                      className="inline-flex h-6 items-center gap-1 rounded px-1.5 text-[11px] font-medium text-muted outline-none transition-colors hover:bg-hover hover:text-fg focus-visible:ring-2 focus-visible:ring-fg/20 disabled:cursor-not-allowed disabled:opacity-40">
                                      <RotateCcw className="h-3 w-3" />Revert
                                    </button>
                                  );
                                })()}
                                {isAdmin && manualById.has(r.section_id) && (
                                  <button type="button" aria-label={`Edit ${r.section_id}`} title="Edit Manual Section"
                                    disabled={!!lockedByOther(r.section_id)}
                                    onClick={(e) => { e.stopPropagation(); setEditor({ editing: manualById.get(r.section_id)! }); }}
                                    className="inline-flex h-6 items-center gap-1 rounded px-1.5 text-[11px] font-medium text-muted outline-none transition-colors hover:bg-hover hover:text-fg focus-visible:ring-2 focus-visible:ring-fg/20 disabled:cursor-not-allowed disabled:opacity-40">
                                    <PencilLine className="h-3 w-3" />Edit
                                  </button>
                                )}
                              </span>
                            ) : <span className="text-muted">{titleCase(r.match_basis)}</span>}
                        </td>
                        <td><Badge>{r.sequence === "ASYNC" ? "Async" : r.sequence}</Badge></td>
                        <td className="whitespace-nowrap text-xs tabular-nums text-muted">{r.meeting_time}</td>
                        <td className="whitespace-nowrap text-right tabular-nums text-muted">{r.projected_enrollment} / {r.section_cap}</td>
                        <td className="text-xs text-muted">{r.modality.startsWith("Online") ? "Remote" : r.component === "Recitation" ? "Recitation" : "In Person"}</td>
                        <td>
                          <span className="flex items-center justify-end gap-2 text-faint">
                            {locked.has(r.section_id) && <span title={`Locked by ${locked.get(r.section_id)}`}><Lock className="h-3.5 w-3.5 text-amber-500" /></span>}
                            {(data.comment_counts[r.section_id] ?? 0) > 0 && <span className="flex items-center gap-0.5 text-xs"><MessageSquare className="h-3.5 w-3.5" />{data.comment_counts[r.section_id]}</span>}
                            {flagged.has(r.section_id) && <span title="Has a Conflict"><TriangleAlert className="h-3.5 w-3.5 text-nu-text" /></span>}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              )}
              <div className="border-t border-line px-4 py-2 text-xs text-muted">{rows.length} of {data.master.length} sections · select a section to see details, edit or discuss it</div>
            </Panel>
          </>
        )}
      </div>

      {data && meta && openRow && (
        <SectionDrawer row={openRow} data={data} meta={meta} onClose={() => open(null)} onChanged={() => fetch(settings, { silent: true })} />
      )}
      {data && meta && (
        <SectionEditor open={!!editor} onClose={() => setEditor(null)} data={data} meta={meta}
          prefill={editor?.prefill} editing={editor?.editing ?? null} />
      )}
      {data && <PublishModal open={publishOpen} onClose={() => setPublishOpen(false)} critical={data.summary.critical} />}
      {data && (
        <ConfirmDialog open={revertAllOpen} title="Revert All Edits?" confirmLabel="Revert All Edits" tone="danger" busy={revertAllBusy}
          onConfirm={revertAll} onCancel={() => setRevertAllOpen(false)}>
          <p>This reverts all <span className="font-medium text-fg">{data.summary.overrides_applied}</span> manual edit{data.summary.overrides_applied === 1 ? "" : "s"} in <span className="font-medium text-fg">{settings.target_term}</span>: edited sections go back to their generated instructor and time block{data.manual_sections.length ? <>, and the <span className="font-medium text-fg">{data.manual_sections.length}</span> section{data.manual_sections.length === 1 ? "" : "s"} added by hand {data.manual_sections.length === 1 ? "is" : "are"} removed</> : null}.</p>
          <p>Sections another scheduler is editing right now are skipped. This can't be undone.</p>
        </ConfirmDialog>
      )}
    </>
  );
}

function PublishModal({ open, onClose, critical }: { open: boolean; onClose: () => void; critical: number }) {
  const settings = usePlan((s) => s.settings);
  const success = useUI((s) => s.success);
  const [note, setNote] = useState("");
  const [override, setOverride] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const go = async () => {
    setBusy(true);
    setError(null);
    try {
      const p = await api.publish(settings, note, override);
      success(`Published ${p.term} v${p.version}`, `${p.sections} sections frozen for catalog export`, "publication");
      setNote("");
      onClose();
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  return (
    <Modal open={open} onClose={onClose} title={`Publish ${settings.target_term}`}
      footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button>
        <Button variant="primary" loading={busy} disabled={critical > 0 && !override} onClick={go}>Publish Schedule</Button></>}>
      <div className="space-y-4 text-[13px]">
        <p className="text-muted">Publishing freezes the current schedule, including manual edits, as a new numbered version. Everyone is notified, and the catalog CSV export uses the latest published version.</p>
        {critical > 0 && (
          <Alert tone="warning" title={`${critical} Critical ${critical > 1 ? "Conflicts Remain" : "Conflict Remains"}`}>
            <div className="mt-2"><Switch checked={override} onChange={setOverride} label="Publish Anyway" /></div>
          </Alert>
        )}
        <Field label="Release Note (Optional)"><textarea className={textareaCls} rows={3} value={note} onChange={(e) => setNote(e.target.value)}
          placeholder="e.g. Final version for registrar review" /></Field>
        {error && <Alert tone="error">{error}</Alert>}
      </div>
    </Modal>
  );
}
