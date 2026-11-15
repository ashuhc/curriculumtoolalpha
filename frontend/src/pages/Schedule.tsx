// Master Schedule: grid + weekly calendar with live collaboration, section drawer, publishing.
import { CalendarRange, Download, FileCheck2, LayoutList, Lock, MessageSquare, Search, Send, TriangleAlert } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, type ScheduleResponse } from "../api";
import { SectionDrawer } from "../components/SectionDrawer";
import { SettingsPanel } from "../components/SettingsPanel";
import { WeekCalendar } from "../components/WeekCalendar";
import {
  Alert, Badge, Button, CATEGORIES, CategoryDot, ErrorState, Field, Modal, PageHeader, Panel, Segmented, Spinner, Stat, StatGrid, Switch, Table,
  cx, inputBase, textareaCls,
} from "../components/ui";
import { fmtDate, useDebounced } from "../lib/hooks";
import { titleCase } from "../lib/text";
import { useIsAdmin } from "../store/auth";
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

  useEffect(() => { fetch(s); }, [s, dataVersion, fetch]);

  const flagged = useMemo(() => flaggedSections(data), [data]);
  const locked = useMemo(() => new Map((data?.locks ?? []).map((l) => [l.section_id, l.user_name])), [data]);
  const overridden = useMemo(() => new Set(data?.overridden ?? []), [data]);
  const rows = useMemo(() => (data?.master ?? []).filter((r) =>
    (!q || `${r.section_id} ${r.title} ${r.instructor}`.toLowerCase().includes(q.toLowerCase())) &&
    (!cat || r.category === cat) && (!inst || r.instructor === inst) && (!onlyFlagged || flagged.has(r.section_id))),
  [data, q, cat, inst, onlyFlagged, flagged]);
  const openRow = data?.master.find((r) => r.section_id === openId) ?? null;
  const open = (id: string | null) => setParams(id ? { section: id } : {}, { replace: true });
  const exportKind = (k: "master" | "catalog") => api.exportPlan(k, settings)
    .then(() => success(k === "master" ? "Master schedule exported" : "Catalog CSV downloaded", `${settings.target_term} · current schedule`))
    .catch((e) => toast({ title: "Export failed", body: e.message, tone: "error" }));
  const sm = data?.summary;
  const pub = data?.publication;

  return (
    <>
      <PageHeader title="Master Schedule"
        description="Core courses are staffed first, then recitations, then preference-driven electives. Lectures use class sequences 1–5 and A–H; recitations use 65-minute slots in lab windows L–W."
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
                <Stat label="Sections" value={sm.sections} />
                <Stat label="Core Staffed" value={`${sm.core_staffed}/${sm.core_sections}`} tone={sm.core_staffed < sm.core_sections ? "danger" : undefined} />
                <Stat label="Electives Offered" value={sm.electives_offered} />
                <Stat label="Top-3 Preference Matches" value={sm.preference_matches} sub={`${sm.submissions} form submission${sm.submissions === 1 ? "" : "s"}`} />
                <Stat label="Critical · Warnings" value={`${sm.critical} · ${sm.warning}`} tone={sm.critical ? "danger" : sm.warning ? "warning" : undefined} />
                <Stat label="Manual Edits" value={sm.overrides_applied} sub={sm.overrides_stale.length ? `${sm.overrides_stale.length} no longer match a section` : `${data.locks.length} section${data.locks.length === 1 ? "" : "s"} locked`} />
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
                {isAdmin && sm.overrides_applied > 0 && (
                  <Button size="sm" variant="ghost" onClick={() => confirm(`Discard all ${sm.overrides_applied} manual edits for ${settings.target_term}?`) &&
                    api.resetOverrides(settings.target_term)
                      .then(() => success("Manual edits discarded", `${sm.overrides_applied} section${sm.overrides_applied === 1 ? "" : "s"} back to the generated schedule`, data.overridden.map((id) => `section:${id}`)))
                      .catch((e) => toast({ title: "Reset failed", body: e.message, tone: "error" }))}>Reset Edits</Button>
                )}
              </>}>
              {view === "calendar" ? (
                <div className="p-4"><WeekCalendar rows={rows} meta={meta} flagged={flagged} locked={locked} comments={data.comment_counts} onOpen={open} /></div>
              ) : (
                <Table maxH="max-h-[680px]">
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
                        <td className="text-xs">{overridden.has(r.section_id) ? <Badge tone="amber">Manual Edit</Badge> : <span className="text-muted">{titleCase(r.match_basis)}</span>}</td>
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
      {data && <PublishModal open={publishOpen} onClose={() => setPublishOpen(false)} critical={data.summary.critical} />}
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
          <Alert tone="warning" title={`${critical} critical conflict${critical > 1 ? "s" : ""} remain`}>
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
