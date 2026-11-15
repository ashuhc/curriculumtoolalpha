// Demand Estimator: projected enrollment, section sizing, recitation scaling, prerequisites.
import { Download, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { api } from "../api";
import { SettingsPanel } from "../components/SettingsPanel";
import { Alert, Badge, Button, CategoryDot, ErrorState, PageHeader, Panel, Spinner, Stat, StatGrid, Switch, Table, cx, inputBase } from "../components/ui";
import { useAsync, useDebounced } from "../lib/hooks";
import { usePlan } from "../store/plan";
import { useUI } from "../store/ui";

export default function Demand() {
  const { settings, dataVersion } = usePlan();
  const toast = useUI((s) => s.toast);
  const s = useDebounced(settings);
  const res = useAsync(() => (s.target_term ? api.demand(s) : Promise.resolve(null)), [JSON.stringify(s), dataVersion]);
  const [q, setQ] = useState("");
  const [cat, setCat] = useState("");
  const [plannedOnly, setPlannedOnly] = useState(true);

  const d = res.data;
  const rows = useMemo(() => (d?.demand ?? []).filter((r) =>
    (!q || `${r.course} ${r.title}`.toLowerCase().includes(q.toLowerCase())) && (!cat || r.category === cat) &&
    (!plannedOnly || r.planned_sections > 0)), [d, q, cat, plannedOnly]);
  const cats = useMemo(() => [...new Set((d?.demand ?? []).map((r) => r.category))], [d]);
  const recitations = (d?.demand ?? []).filter((r) => r.category === "Recitation");
  const backtest = (d?.demand ?? []).some((r) => r.actual_enrollment !== null);
  const failedPrereqs = d?.prerequisites.filter((p) => !p.ok).length ?? 0;

  return (
    <>
      <PageHeader title="Demand Estimator"
        description={<>Projected undergraduate enrollment and section plan for <span className="font-medium text-fg">{settings.target_term}</span>. Projection = recency-weighted average of prior same-season terms × annual trend × growth multiplier.</>}
        actions={<Button icon={<Download className="h-3.5 w-3.5" />} onClick={() => api.exportPlan("demand", settings).catch((e) => toast({ title: "Export failed", body: e.message, tone: "error" }))}>Export CSV</Button>} />

      <div className="space-y-6">
        <SettingsPanel mode="demand" />
        {res.error && <ErrorState error={res.error} onRetry={res.reload} />}
        {!d && res.loading && <Spinner label="Forecasting demand" />}
        {d && (
          <>
            <div className={cx("transition-opacity", res.loading && "opacity-60")}>
              <StatGrid cols={6}>
                <Stat label="Courses planned" value={d.summary.courses} />
                <Stat label="Lecture sections" value={d.summary.lecture_sections} />
                <Stat label="Recitations" value={d.summary.recitation_sections} />
                <Stat label="Projected students" value={d.summary.projected_students.toLocaleString()} />
                <Stat label="Seats offered" value={d.summary.seats_offered.toLocaleString()}
                  sub={`${Math.round((100 * d.summary.projected_students) / Math.max(1, d.summary.seats_offered))}% seat fill`} />
                <Stat label="Remote sections" value={d.summary.remote_sections} sub={`≤ ${settings.virtual_cap} students each`} />
              </StatGrid>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              {recitations.map((r) => (
                <Panel key={r.code} title={`${r.course} recitations`} description={`${r.title} · weekly, 65 minutes`}>
                  <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1 text-[13px] text-muted">
                    <span className="text-lg font-semibold tabular-nums text-fg">{r.projected_enrollment.toLocaleString()}</span> on-campus lecture students
                    <span>÷</span><span className="text-lg font-semibold tabular-nums text-fg">{settings.recitation_cap}</span> per recitation
                    <span>=</span><span className="text-lg font-semibold tabular-nums text-fg">{r.planned_sections}</span> sections
                  </div>
                  <p className="mt-2 text-xs text-faint">Each recitation is linked to one lecture section and scheduled so it never overlaps it.
                    {r.actual_sections !== null && ` Actual that term: ${r.actual_sections} sections.`}</p>
                </Panel>
              ))}
            </div>

            <Panel flush title="Projected demand and section plan"
              description={`Principles run as ${settings.large_lecture_cap}-seat lectures plus ${settings.small_section_cap}-seat sections. Electives under ${settings.min_elective_demand} students aren't planned and only run if a faculty member is matched to them.`}
              actions={<>
                <div className="relative"><Search className="absolute left-2.5 top-2 h-4 w-4 text-faint" />
                  <input className={inputBase + " w-52 pl-8"} placeholder="Filter courses" value={q} onChange={(e) => setQ(e.target.value)} /></div>
                <select className={inputBase + " w-44"} value={cat} onChange={(e) => setCat(e.target.value)}>
                  <option value="">All categories</option>{cats.map((c) => <option key={c}>{c}</option>)}
                </select>
                <Switch checked={plannedOnly} onChange={setPlannedOnly} label="Planned only" />
              </>}>
              {backtest && <div className="border-b border-line p-3"><Alert>Back-test: {settings.target_term} already has enrollment on file, so actual figures appear next to the forecast (which uses only earlier terms).</Alert></div>}
              <Table maxH="max-h-[640px]">
                <thead><tr>
                  <th>Course</th><th>Title</th><th>Category</th><th>Modality</th><th className="text-right">Hist. avg</th><th className="text-right">Trend / yr</th>
                  <th className="text-right">Projected</th><th className="text-right">Sections</th><th>Section caps</th><th className="w-36">Seat fill</th>
                  {backtest && <th className="text-right">Actual</th>}<th>Notes</th>
                </tr></thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={`${r.code}-${r.virtual}`} className={cx("hover:bg-hover", r.planned_sections === 0 && "text-faint")}>
                      <td className="whitespace-nowrap font-medium tabular-nums">{r.course}</td>
                      <td className="min-w-48">{r.title}</td>
                      <td className="whitespace-nowrap"><span className="flex items-center gap-1.5 text-xs text-muted"><CategoryDot category={r.category} />{r.category}</span></td>
                      <td className="whitespace-nowrap">{r.virtual ? <Badge tone="blue">Remote</Badge> : <span className="text-muted">In person</span>}</td>
                      <td className="text-right tabular-nums text-muted">{r.hist_weighted_avg ?? "—"}</td>
                      <td className={cx("text-right tabular-nums", r.annual_trend > 0.005 ? "text-emerald-600" : r.annual_trend < -0.005 ? "text-nu-text" : "text-faint")}>
                        {r.annual_trend ? `${r.annual_trend > 0 ? "+" : ""}${(r.annual_trend * 100).toFixed(1)}%` : "—"}</td>
                      <td className="text-right font-medium tabular-nums">{r.projected_enrollment}</td>
                      <td className="text-right font-medium tabular-nums">{r.planned_sections}</td>
                      <td className="whitespace-nowrap tabular-nums text-muted">{r.section_caps}</td>
                      <td>
                        <div className="flex items-center gap-2">
                          <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-subtle">
                            <div className={cx("h-full rounded-full", r.seat_fill > 0.98 ? "bg-nu" : "bg-fg/50")} style={{ width: `${Math.min(100, r.seat_fill * 100)}%` }} />
                          </div>
                          <span className="w-9 text-right text-xs tabular-nums text-muted">{Math.round(r.seat_fill * 100)}%</span>
                        </div>
                      </td>
                      {backtest && <td className="text-right tabular-nums">{r.actual_enrollment ?? "—"}{r.actual_sections !== null && <span className="text-faint"> ({r.actual_sections})</span>}</td>}
                      <td className="max-w-60 text-xs text-muted">{r.notes}</td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </Panel>

            <Panel flush title="Prerequisite validation"
              description="1000-level: none · 3000-level: Principles · 4000-level: multiple prerequisites including theory. Each prerequisite must also be offered this term."
              actions={<Badge tone={failedPrereqs ? "amber" : "green"}>{d.prerequisites.length - failedPrereqs} of {d.prerequisites.length} pass</Badge>}>
              <Table maxH="max-h-96">
                <thead><tr><th>Course</th><th>Title</th><th>Level</th><th>Prerequisites</th><th>Level rule</th><th>Pathway offered</th></tr></thead>
                <tbody>{d.prerequisites.map((p) => (
                  <tr key={p.course}>
                    <td className="font-medium tabular-nums">{p.course}</td><td>{p.title}</td><td className="tabular-nums text-muted">{p.level}</td>
                    <td className="text-muted">{p.prerequisites}</td>
                    <td>{p.level_rule.startsWith("✅") ? <Badge tone="green">Valid</Badge> : <Badge tone="red">{p.level_rule.replace(/^❌ /, "")}</Badge>}</td>
                    <td>{p.pathway_offered_this_term.startsWith("✅") ? <Badge tone="green">Offered</Badge> : <Badge tone="amber">{p.pathway_offered_this_term.replace(/^⚠️ /, "")}</Badge>}</td>
                  </tr>
                ))}</tbody>
              </Table>
            </Panel>
          </>
        )}
      </div>
    </>
  );
}
