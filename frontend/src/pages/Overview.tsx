import { ArrowRight, BarChart3, CalendarRange, ClipboardList, FileCheck2, TriangleAlert } from "lucide-react";
import { useEffect } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { Badge, Button, ErrorState, PageHeader, Panel, Stat, StatGrid } from "../components/ui";
import { fmtDate, useAsync } from "../lib/hooks";
import { useAuth } from "../store/auth";
import { usePlan } from "../store/plan";
import { useSchedule } from "../store/schedule";

const STEPS = [
  { to: "/preferences", icon: ClipboardList, title: "Collect Teaching Preferences", text: "Faculty rank up to six courses, set Fall/Spring loads and note overloads or special circumstances." },
  { to: "/demand", icon: BarChart3, title: "Forecast Demand", text: "Project enrollment from history, apply a growth multiplier and size lectures, small sections and recitations." },
  { to: "/schedule", icon: CalendarRange, title: "Build the Master Schedule", text: "Core courses are staffed first, then electives; sections are placed on Course_Sequences.pdf time blocks." },
  { to: "/conflicts", icon: TriangleAlert, title: "Resolve Conflicts and Publish", text: "Clear unstaffed core sections, workload issues and overlaps, then publish and export for the catalog." },
];

export default function Overview() {
  const user = useAuth((s) => s.user);
  const { settings, dataVersion } = usePlan();
  const { data, error, fetch } = useSchedule();
  const health = useAsync(() => api.health(), [dataVersion]);
  const mine = useAsync(() => (user?.role === "faculty" ? api.myPreferences() : Promise.resolve([])), [user?.id, dataVersion]);

  useEffect(() => { fetch(settings); }, [settings, dataVersion, fetch]);
  const s = data?.summary;

  return (
    <>
      <PageHeader title={user ? `Welcome Back, ${user.name}` : "Curriculum Planning"}
        description="Plan the undergraduate economics curriculum: collect faculty preferences, forecast demand, build and publish the master schedule." />

      {user?.role === "faculty" && (
        <Panel className="mb-6" title="Your Teaching Preferences"
          actions={<Link to="/preferences"><Button size="sm" variant="primary">{mine.data?.length ? "Update Preferences" : "Submit Preferences"}</Button></Link>}>
          {mine.data?.length
            ? <p className="text-[13px] text-muted">Last submitted {fmtDate(mine.data[0].submitted_at)}. Ranked: {mine.data[0].ranks.map((c) => `ECON ${c}`).join(", ") || "none"}.</p>
            : <p className="text-[13px] text-muted">You haven't submitted preferences yet. Electives are only offered when a faculty member asks to teach them.</p>}
        </Panel>
      )}

      {error && <div className="mb-6"><ErrorState error={error} /></div>}
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-[13px] font-semibold">{settings.target_term || "—"} at a Glance</h2>
        {data?.publication && (
          <Badge tone="green"><FileCheck2 className="h-3 w-3" />Published v{data.publication.version} · {fmtDate(data.publication.published_at)}</Badge>
        )}
      </div>
      <StatGrid cols={6}>
        <Stat label="Sections Planned" value={s?.sections ?? "—"} />
        <Stat label="Core Staffed" value={s ? `${s.core_staffed}/${s.core_sections}` : "—"} tone={s && s.core_staffed < s.core_sections ? "danger" : undefined} />
        <Stat label="Electives Offered" value={s?.electives_offered ?? "—"} />
        <Stat label="Critical Conflicts" value={s?.critical ?? "—"} tone={s?.critical ? "danger" : undefined} />
        <Stat label="Preference Forms" value={health.data?.submissions ?? "—"} sub={`${health.data?.faculty ?? "—"} faculty on roster`} />
        <Stat label="Enrollment History" value={health.data ? health.data.enrollment_records.toLocaleString() : "—"} sub={health.data ? `sections · ${health.data.database}` : undefined} />
      </StatGrid>
      {health.error && <div className="mt-4"><ErrorState error={health.error} onRetry={health.reload} /></div>}

      <h2 className="mb-2 mt-8 text-[13px] font-semibold">Planning Workflow</h2>
      <div className="grid gap-px overflow-hidden rounded-lg border border-line bg-line md:grid-cols-2">
        {STEPS.map((st, i) => (
          <Link key={st.to} to={st.to} className="group flex gap-4 bg-surface p-4 transition-colors hover:bg-hover">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-line text-muted"><st.icon className="h-4 w-4" strokeWidth={1.75} /></div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2 text-[13px] font-medium"><span className="tabular-nums text-faint">{i + 1}</span>{st.title}
                <ArrowRight className="ml-auto h-3.5 w-3.5 text-faint transition-transform group-hover:translate-x-0.5" /></div>
              <p className="mt-1 text-xs leading-relaxed text-muted">{st.text}</p>
            </div>
          </Link>
        ))}
      </div>
    </>
  );
}
