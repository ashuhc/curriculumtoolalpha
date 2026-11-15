// Faculty teaching-preference form (replaces TEACHER_PREFERENCES.py).
import { ExternalLink, Search } from "lucide-react";
import { useEffect, useMemo, useState, type FormEvent, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { api, type Course } from "../api";
import { CourseSelect, matchCourse } from "../components/CourseSelect";
import { Alert, Badge, Button, ErrorState, Field, PageHeader, Panel, Spinner, inputCls, textareaCls } from "../components/ui";
import { fmtDate, useAsync } from "../lib/hooks";
import { useAuth } from "../store/auth";
import { usePlan } from "../store/plan";
import { useFlash, useUI } from "../store/ui";

const EMPTY = {
  faculty_id: 0, email: "", principles: [] as number[], ranks: [null, null, null, null, null, null] as (number | null)[],
  fall_target: 2, spring_target: 2, overload: false, overload_semester: "None", unique_circumstances: "",
};

function Section({ n, title, description, children }: { n: number; title: string; description?: string; children: ReactNode }) {
  return (
    <div className="grid gap-4 border-b border-line py-6 last:border-b-0 md:grid-cols-[220px_1fr]">
      <div>
        <div className="text-[13px] font-semibold"><span className="mr-1.5 tabular-nums text-faint">{n}.</span>{title}</div>
        {description && <p className="mt-1 text-xs leading-relaxed text-muted">{description}</p>}
      </div>
      <div>{children}</div>
    </div>
  );
}

export default function Preferences() {
  const user = useAuth((s) => s.user);
  const dataVersion = usePlan((s) => s.dataVersion);
  const success = useUI((s) => s.success);
  const flash = useFlash();
  const courses = useAsync(() => api.courses(), [dataVersion]);
  const faculty = useAsync(() => api.faculty(), [dataVersion]);
  const mine = useAsync(() => (user?.role === "faculty" ? api.myPreferences() : Promise.resolve([])), [user?.id, dataVersion]);
  const [form, setForm] = useState(EMPTY);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const isAdmin = user?.role === "admin";

  // Faculty are bound to their own roster entry; prefill from their latest submission
  useEffect(() => {
    if (!user) return;
    const last = mine.data?.[0];
    setForm((f) => ({
      ...f, faculty_id: user.role === "faculty" ? user.faculty_id ?? 0 : f.faculty_id, email: f.email || user.email,
      ...(last ? {
        principles: last.principles, ranks: [...last.ranks, null, null, null, null, null, null].slice(0, 6),
        fall_target: last.fall_target, spring_target: last.spring_target, overload: last.overload,
        overload_semester: last.overload_semester, unique_circumstances: last.unique_circumstances,
      } : {}),
    }));
  }, [user, mine.data]);

  const set = <K extends keyof typeof EMPTY>(k: K, v: (typeof EMPTY)[K]) => setForm((f) => ({ ...f, [k]: v }));
  const principles = (courses.data ?? []).filter((c) => c.code === 1115 || c.code === 1116);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!form.faculty_id) return setError("Select the faculty member these preferences are for.");
    if (form.overload && form.overload_semester === "None") return setError("Choose which semester you're overloading.");
    setBusy(true);
    try {
      const res = await api.submitPreferences({ ...form, ranks: form.ranks.filter((r): r is number => r !== null),
        overload_semester: form.overload ? form.overload_semester : "None" });
      success("Preferences submitted", `Saved for ${res.faculty_name} · your latest submission is the one used`, "prefs-form");
      mine.reload();
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  }

  if (!user) {
    return (
      <>
        <PageHeader title="Teaching Preferences" description="Faculty submit ranked course preferences and semester loads for the coming academic year." />
        <Alert tone="info" title="Sign In to Submit Your Preferences"
          action={<Link to="/login" state={{ from: "/preferences" }}><Button size="sm" variant="primary">Sign In</Button></Link>}>
          Your account is linked to your faculty roster entry, so submissions are attributed to you.
        </Alert>
        <div className="mt-6"><CatalogBrowser courses={courses.data ?? []} /></div>
      </>
    );
  }
  if (courses.loading || faculty.loading) return <Spinner />;
  if (courses.error || faculty.error) return <ErrorState error={courses.error ?? faculty.error ?? ""} onRetry={() => { courses.reload(); faculty.reload(); }} />;
  const myFaculty = faculty.data!.find((f) => f.id === user.faculty_id);
  const last = mine.data?.[0];

  return (
    <>
      <PageHeader title="Teaching Preferences"
        description="Rank the undergraduate courses you'd like to teach and set your semester loads. Electives are offered only when a faculty member wants to teach them."
        meta={last && <Badge tone="green">Last Submitted {fmtDate(last.submitted_at)}</Badge>}
        actions={<a className="inline-flex items-center gap-1 text-xs text-muted hover:text-fg" target="_blank" rel="noreferrer"
          href="https://catalog.northeastern.edu/undergraduate/social-sciences-humanities/economics/#coursestext">Undergraduate Catalog <ExternalLink className="h-3 w-3" /></a>} />

      {user.role === "faculty" && !user.faculty_id && (
        <div className="mb-6"><Alert tone="warning" title="Account Not Linked">Ask a scheduler to link your account to your faculty roster entry before submitting.</Alert></div>
      )}

      <div className="grid gap-6 xl:grid-cols-[1fr_320px]">
        <form onSubmit={submit} className={`rounded-lg border border-line bg-surface px-5 ${flash("prefs-form")}`}>
          <Section n={1} title="Faculty Member" description={isAdmin ? "Schedulers can submit on behalf of any faculty member." : undefined}>
            <div className="grid gap-4 md:grid-cols-2">
              <Field label="Name">
                {isAdmin ? (
                  <select className={inputCls} value={form.faculty_id} onChange={(e) => set("faculty_id", Number(e.target.value))}>
                    <option value={0}>Select a Faculty Member</option>
                    {faculty.data!.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
                  </select>
                ) : <input className={inputCls} disabled value={myFaculty?.name ?? "Not Linked"} />}
              </Field>
              <Field label="Contact Email"><input className={inputCls} type="email" value={form.email} onChange={(e) => set("email", e.target.value)} /></Field>
            </div>
          </Section>

          <Section n={2} title="Principles Courses" description="Large principles lectures serve both Business School and Economics students.">
            <div className="flex flex-col gap-2">
              {principles.map((c) => (
                <label key={c.code} className="flex items-center gap-2 text-[13px]">
                  <input type="checkbox" checked={form.principles.includes(c.code)}
                    onChange={(e) => set("principles", e.target.checked ? [...form.principles, c.code] : form.principles.filter((x) => x !== c.code))} />
                  <span className="font-medium tabular-nums">ECON {c.code}</span> {c.title}
                </label>
              ))}
            </div>
          </Section>

          <Section n={3} title="Ranked Course Preferences" description="Up to six undergraduate courses. Rank 1 is your strongest preference.">
            <div className="space-y-2">
              {form.ranks.map((r, i) => (
                <div key={i} className="grid grid-cols-[28px_1fr] items-center gap-2">
                  <span className="text-right text-xs tabular-nums text-faint">{i + 1}</span>
                  <CourseSelect courses={courses.data!} value={r} exclude={form.ranks.filter((x, j) => x !== null && j !== i) as number[]}
                    onChange={(code) => set("ranks", form.ranks.map((x, j) => (j === i ? code : x)))} />
                </div>
              ))}
            </div>
          </Section>

          <Section n={4} title="Teaching Load" description="Courses per semester, including any overload (e.g. teaching 3 plus 1 overload → 4).">
            <div className="grid gap-4 md:grid-cols-2">
              <Field label="Fall Courses"><input type="number" min={0} max={5} className={inputCls} value={form.fall_target}
                onChange={(e) => set("fall_target", Math.max(0, Math.min(5, Number(e.target.value))))} /></Field>
              <Field label="Spring Courses"><input type="number" min={0} max={5} className={inputCls} value={form.spring_target}
                onChange={(e) => set("spring_target", Math.max(0, Math.min(5, Number(e.target.value))))} /></Field>
              <Field label="Overload for Additional Compensation">
                <select className={inputCls} value={form.overload ? "yes" : "no"}
                  onChange={(e) => setForm((f) => ({ ...f, overload: e.target.value === "yes", overload_semester: e.target.value === "yes" ? (f.overload_semester === "None" ? "Fall" : f.overload_semester) : "None" }))}>
                  <option value="no">No</option><option value="yes">Yes</option>
                </select>
              </Field>
              <Field label="Overload Semester">
                <select className={inputCls} disabled={!form.overload} value={form.overload_semester} onChange={(e) => set("overload_semester", e.target.value)}>
                  {(form.overload ? ["Fall", "Spring", "Both"] : ["None"]).map((s) => <option key={s}>{s}</option>)}
                </select>
              </Field>
            </div>
          </Section>

          <Section n={5} title="Unique Circumstances" description="Joint appointment, contractual reduction, course buyout, planned sabbatical, or anything else schedulers should know.">
            <textarea className={textareaCls + " min-h-24"} value={form.unique_circumstances} onChange={(e) => set("unique_circumstances", e.target.value)} />
          </Section>

          <div className="flex items-center gap-3 border-t border-line py-4">
            {error && <div className="flex-1"><Alert tone="error">{error}</Alert></div>}
            <div className="ml-auto flex gap-2">
              <Button type="button" variant="ghost" onClick={() => { setForm({ ...EMPTY, faculty_id: form.faculty_id, email: form.email }); success("Form cleared", "Nothing is submitted until you click Submit preferences"); }}>Clear</Button>
              <Button variant="primary" type="submit" loading={busy} disabled={user.role === "faculty" && !user.faculty_id}>Submit Preferences</Button>
            </div>
          </div>
        </form>
        <CatalogBrowser courses={courses.data!} />
      </div>
    </>
  );
}

function CatalogBrowser({ courses }: { courses: Course[] }) {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState<number | null>(null);
  const shown = useMemo(() => courses.filter((c) => matchCourse(c, q)), [courses, q]);
  return (
    <aside className="xl:sticky xl:top-16 xl:self-start">
      <Panel title="Course Catalog" description="Search by code, level (e.g. 3000s), title or topic." flush>
        <div className="border-b border-line p-3">
          <div className="relative">
            <Search className="absolute left-2.5 top-2 h-4 w-4 text-faint" />
            <input className={inputCls + " pl-8"} placeholder="labor, 4000s, 3424" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
        </div>
        <div className="max-h-[60vh] divide-y divide-line overflow-auto">
          {shown.map((c) => (
            <button key={c.code} type="button" onClick={() => setOpen(open === c.code ? null : c.code)} className="block w-full px-3 py-2 text-left hover:bg-hover">
              <div className="flex items-center justify-between gap-2 text-[13px]">
                <span className="truncate"><span className="font-medium tabular-nums">{c.code}</span> <span className="text-muted">{c.title}</span></span>
                {c.category.startsWith("Core") && <Badge>Core</Badge>}
              </div>
              {open === c.code && (
                <div className="mt-1.5 space-y-1 text-xs leading-relaxed text-muted">
                  <p>{c.description || "No description available."}</p>
                  <p><span className="text-fg">Prerequisites:</span> {c.prerequisites}</p>
                  <p><span className="text-fg">Offered:</span> {c.times_offered} of the past terms on record</p>
                </div>
              )}
            </button>
          ))}
          {shown.length === 0 && <p className="p-3 text-[13px] text-muted">No matches.</p>}
        </div>
      </Panel>
    </aside>
  );
}
