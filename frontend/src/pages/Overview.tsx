import {
  AlertTriangle, ArrowRight, BarChart3, BookOpen, CalendarRange, ClipboardList, Database, FileCheck2, ShieldCheck, TriangleAlert, Users,
} from "lucide-react";
import { useEffect } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { Badge, Button, CARD, CARD_INTERACTIVE, ErrorState, IconBadge, PageHeader, Panel, Stat, StatGrid, cx } from "../components/ui";
import { fmtDate, useAsync } from "../lib/hooks";
import { useAuth } from "../store/auth";
import { usePlan } from "../store/plan";
import { useSchedule } from "../store/schedule";

const STEPS = [
  { to: "/preferences", icon: ClipboardList, title: "Collect Teaching Preferences", text: "Faculty rank up to six preferred courses, set fall and spring teaching loads, and note overloads or special circumstances." },
  { to: "/demand", icon: BarChart3, title: "Review Enrollment Projections", text: "Forecast course demand from historical enrollment and set the number of lectures, small sections, and recitations." },
  { to: "/schedule", icon: CalendarRange, title: "Build the Term Schedule", text: "Staff core requirements first, then place each section on a standard lecture or recitation time block." },
  { to: "/conflicts", icon: TriangleAlert, title: "Resolve Conflicts & Audits", text: "Clear unstaffed core sections, workload issues, and time overlaps, then publish the term for catalog export." },
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
      <PageHeader eyebrow="Dashboard" title={user ? `Welcome Back, ${user.name}` : "Curriculum Planning"}
        description="Coordinate undergraduate economics course offerings, faculty teaching assignments, and term schedules." />

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
        <Stat to="/schedule" icon={CalendarRange} label="Sections Planned" value={s?.sections ?? "—"} sub="View in Term Schedule" />
        <Stat to="/schedule" icon={ShieldCheck} label="Core Staffed" value={s ? `${s.core_staffed}/${s.core_sections}` : "—"}
          tone={s && s.core_staffed < s.core_sections ? "danger" : undefined} iconTone={s && s.core_staffed < s.core_sections ? "warning" : "primary"} sub="Mandatory core sections" />
        <Stat to="/schedule" icon={BookOpen} label="Electives Offered" value={s?.electives_offered ?? "—"} sub="Matched to willing faculty" />
        <Stat to="/conflicts" icon={AlertTriangle} iconTone="warning" label="Critical Conflicts" value={s?.critical ?? "—"}
          tone={s?.critical ? "danger" : undefined} sub={s ? `${s.warning} warnings to review` : undefined} />
        <Stat to="/preferences" icon={Users} label="Preference Forms" value={health.data?.submissions ?? "—"} sub={`${health.data?.faculty ?? "—"} faculty on roster`} />
        <Stat to="/demand" icon={Database} iconTone="neutral" label="Enrollment History" value={health.data ? health.data.enrollment_records.toLocaleString() : "—"}
          sub={health.data ? `sections · ${health.data.database}` : undefined} />
      </StatGrid>
      {health.error && <div className="mt-4"><ErrorState error={health.error} onRetry={health.reload} /></div>}

      <h2 className="mb-2 mt-8 text-[13px] font-semibold">Planning Workflow</h2>
      <div className="grid gap-3 md:grid-cols-2">
        {STEPS.map((st, i) => (
          <Link key={st.to} to={st.to} className={cx(CARD, CARD_INTERACTIVE, "group flex gap-4 p-4")}>
            <IconBadge icon={st.icon} tone={st.to === "/conflicts" ? "warning" : "primary"} size={32} />
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2 text-[13px] font-medium"><span className="tabular-nums text-faint">{i + 1}</span>{st.title}
                <ArrowRight className="ml-auto h-3.5 w-3.5 text-faint transition group-hover:translate-x-0.5 group-hover:text-nu-text" /></div>
              <p className="mt-1 text-xs leading-relaxed text-muted">{st.text}</p>
            </div>
          </Link>
        ))}
      </div>
    </>
  );
}
