// Unresolved conflicts report + faculty workload, with CSV export.
import { Download, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, type ConflictRow } from "../api";
import { Alert, Badge, Button, ErrorState, PageHeader, Panel, SEVERITY_TONE, Spinner, Stat, StatGrid, Table, Tabs, cx, inputBase } from "../components/ui";
import { useDebounced } from "../lib/hooks";
import { titleCase } from "../lib/text";
import { usePlan } from "../store/plan";
import { useSchedule } from "../store/schedule";
import { useUI } from "../store/ui";

type Sev = ConflictRow["severity"];

function statusTone(s: string) {
  if (s.startsWith("❌")) return "red" as const;
  if (s.startsWith("⚠️")) return "amber" as const;
  if (s.startsWith("💲")) return "blue" as const;
  if (s.startsWith("✅")) return "green" as const;
  return "neutral" as const;
}
const stripEmoji = (s: string) => s.replace(/^[^\p{L}]+/u, "");

export default function Conflicts() {
  const { settings, dataVersion } = usePlan();
  const { data: d, loading, error, fetch } = useSchedule();
  const toast = useUI((s) => s.toast);
  const success = useUI((s) => s.success);
  const navigate = useNavigate();
  const s = useDebounced(settings);
  const [tab, setTab] = useState<"conflicts" | "workload">("conflicts");
  const [sev, setSev] = useState<Set<Sev>>(new Set<Sev>(["Critical", "Warning"]));
  const [cat, setCat] = useState("");
  const [q, setQ] = useState("");
  const [type, setType] = useState("");

  useEffect(() => { fetch(s); }, [s, dataVersion, fetch]);

  const conflicts = useMemo(() => (d?.conflicts ?? []).filter((c) => sev.has(c.severity) && (!cat || c.category === cat) &&
    (!q || `${c.course_section} ${c.faculty} ${c.details}`.toLowerCase().includes(q.toLowerCase()))), [d, sev, cat, q]);
  const cats = useMemo(() => [...new Set((d?.conflicts ?? []).map((c) => c.category))].sort(), [d]);
  const workload = useMemo(() => (d?.workload ?? []).filter((w) => (!type || w.type === type) &&
    (!q || w.faculty.toLowerCase().includes(q.toLowerCase()))), [d, type, q]);
  const toggle = (v: Sev) => setSev((cur) => { const n = new Set(cur); if (n.has(v)) n.delete(v); else n.add(v); return n; });
  const exp = (k: "conflicts" | "workload") => api.exportPlan(k, settings)
    .then(() => success(k === "conflicts" ? "Conflicts report exported" : "Workload report exported", settings.target_term))
    .catch((e) => toast({ title: "Export failed", body: e.message, tone: "error" }));
  const sectionOf = (c: ConflictRow) => /ECON \d{4}-\d{2}/.exec(c.course_section)?.[0];

  return (
    <>
      <PageHeader title="Conflicts"
        description={<>Items that need review before <span className="font-medium text-fg">{settings.target_term}</span> is published. Reflects manual edits made on the Master Schedule.</>}
        actions={<Button icon={<Download className="h-3.5 w-3.5" />} onClick={() => exp(tab)}>Export {tab === "conflicts" ? "Conflicts" : "Workload"} CSV</Button>} />
      {error && <ErrorState error={error} onRetry={() => fetch(settings)} />}
      {!d && loading && <Spinner />}
      {d && (
        <div className="space-y-6">
          <StatGrid cols={3}>
            {(["Critical", "Warning", "Info"] as Sev[]).map((v) => (
              <Stat key={v} label={v === "Info" ? "Informational" : v === "Warning" ? "Warnings" : "Critical"} active={sev.has(v)} onClick={() => toggle(v)}
                value={d.summary[v.toLowerCase() as "critical" | "warning" | "info"]} tone={v === "Critical" && d.summary.critical ? "danger" : v === "Warning" && d.summary.warning ? "warning" : undefined}
                sub={sev.has(v) ? "Shown · click to hide" : "Hidden · click to show"} />
            ))}
          </StatGrid>
          {d.summary.critical === 0 && <Alert tone="success" title="No Critical Conflicts">This term is ready to publish once warnings have been reviewed.</Alert>}

          <div>
            <Tabs value={tab} onChange={setTab} className="mb-4" tabs={[
              { id: "conflicts", label: "Conflict Report", count: d.conflicts.length },
              { id: "workload", label: "Faculty Workload", count: d.workload.length }]} />
            <Panel flush actions={<>
              <div className="relative"><Search className="absolute left-2.5 top-2 h-4 w-4 text-faint" />
                <input className={inputBase + " w-60 pl-8"} placeholder={tab === "conflicts" ? "Section, faculty or details" : "Faculty"} value={q} onChange={(e) => setQ(e.target.value)} /></div>
              {tab === "conflicts" ? (
                <select className={inputBase + " w-56"} value={cat} onChange={(e) => setCat(e.target.value)}>
                  <option value="">All Categories</option>{cats.map((c) => <option key={c} value={c}>{titleCase(c)}</option>)}
                </select>
              ) : (
                <select className={inputBase + " w-48"} value={type} onChange={(e) => setType(e.target.value)}>
                  <option value="">All Faculty Groups</option>
                  {["Tenured", "Full-Time Teaching", "Temporary", "Adjunct", "Recitation Leader"].map((t) => <option key={t}>{t}</option>)}
                </select>
              )}
            </>} title={tab === "conflicts" ? "Unresolved Conflicts" : "Annual Load vs. Contract"}
              description={tab === "workload" ? "Tenured 3/yr (may teach fewer) · Full-time teaching & temporary 6/yr · Adjunct 1–2/yr. Approved overloads raise the ceiling; reductions lower it." : undefined}>
              <div className={cx("transition-opacity", loading && "opacity-60")}>
                {tab === "conflicts" ? (
                  conflicts.length === 0 ? <div className="p-6 text-center text-[13px] text-muted">No conflicts match these filters.</div> : (
                    <Table maxH="max-h-[640px]">
                      <thead><tr><th>Severity</th><th>Category</th><th>Course / Section</th><th>Faculty</th><th>Details</th><th>Suggested Action</th></tr></thead>
                      <tbody>{conflicts.map((c, i) => {
                        const sid = sectionOf(c);
                        return (
                          <tr key={i} className={cx(sid && "cursor-pointer hover:bg-hover")} onClick={() => sid && navigate(`/schedule?section=${encodeURIComponent(sid)}`)}>
                            <td><Badge tone={SEVERITY_TONE[c.severity]}>{c.severity}</Badge></td>
                            <td className="whitespace-nowrap font-medium">{titleCase(c.category)}</td>
                            <td className="whitespace-nowrap tabular-nums">{c.course_section}</td>
                            <td className="whitespace-nowrap text-muted">{c.faculty}</td>
                            <td className="min-w-64">{c.details}</td>
                            <td className="min-w-56 text-muted">{c.suggested_action}</td>
                          </tr>
                        );
                      })}</tbody>
                    </Table>
                  )
                ) : (
                  <Table maxH="max-h-[640px]">
                    <thead><tr><th>Faculty</th><th>Group</th><th>Target From</th><th className="text-right">Term Target</th><th className="text-right">Assigned</th>
                      <th className="text-right">Other Semester</th><th className="text-right">Annual</th><th>Allowed</th><th>Overload (Approved / Requested)</th><th>Status</th></tr></thead>
                    <tbody>{workload.map((w) => (
                      <tr key={w.faculty} className="hover:bg-hover">
                        <td className="whitespace-nowrap font-medium">{w.faculty}</td><td className="whitespace-nowrap text-muted">{w.type}</td>
                        <td className="text-xs text-muted">{titleCase(w.target_source)}</td><td className="text-right tabular-nums">{w.term_target}</td>
                        <td className="text-right font-medium tabular-nums">{w.assigned_this_term}</td><td className="text-right tabular-nums text-muted">{w.other_semester_planned}</td>
                        <td className="text-right font-medium tabular-nums">{w.projected_annual}</td><td className="whitespace-nowrap tabular-nums text-muted">{w.allowed_annual}</td>
                        <td className="text-muted">{w.overload_approved_json} / {w.overload_requested_form}</td>
                        <td><Badge tone={statusTone(w.status)}>{titleCase(stripEmoji(w.status))}</Badge></td>
                      </tr>
                    ))}</tbody>
                  </Table>
                )}
              </div>
            </Panel>
          </div>
        </div>
      )}
    </>
  );
}
