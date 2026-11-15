// Administration (scheduler role): submissions, faculty & overloads, catalog, users, data, publications.
import { Download, Plus, Search, Trash2, Upload } from "lucide-react";
import { useMemo, useState, type FormEvent } from "react";
import { Navigate } from "react-router-dom";
import { api, type Course, type Faculty, type Role } from "../api";
import { matchCourse } from "../components/CourseSelect";
import { Alert, Badge, Button, ErrorState, Field, IconButton, PageHeader, Panel, Spinner, Switch, Table, Tabs, inputBase, inputCls } from "../components/ui";
import { fmtDate, useAsync } from "../lib/hooks";
import { useAuth, useIsAdmin } from "../store/auth";
import { usePlan } from "../store/plan";
import { useUI } from "../store/ui";

type Tab = "submissions" | "faculty" | "courses" | "users" | "data" | "publications";

function useFail() {
  const toast = useUI((s) => s.toast);
  return (e: unknown) => toast({ title: "Action failed", body: (e as Error).message, tone: "error" });
}

export default function Admin() {
  const isAdmin = useIsAdmin();
  const user = useAuth((s) => s.user);
  const [tab, setTab] = useState<Tab>("submissions");
  if (!user) return <Navigate to="/login" state={{ from: "/admin" }} replace />;
  if (!isAdmin) return <Alert tone="warning" title="Scheduler access required">Your account has the faculty role.</Alert>;
  return (
    <>
      <PageHeader title="Administration" description="Manage preference submissions, the faculty roster and overloads, the course catalog, user accounts and enrollment data." />
      <Tabs value={tab} onChange={setTab} className="mb-5" tabs={[
        { id: "submissions", label: "Submissions" }, { id: "faculty", label: "Faculty & overloads" }, { id: "courses", label: "Course catalog" },
        { id: "users", label: "Users & roles" }, { id: "data", label: "Enrollment data" }, { id: "publications", label: "Publications" }]} />
      {tab === "submissions" && <Submissions />}
      {tab === "faculty" && <FacultyAdmin />}
      {tab === "courses" && <CourseAdmin />}
      {tab === "users" && <UsersAdmin />}
      {tab === "data" && <DataAdmin />}
      {tab === "publications" && <Publications />}
    </>
  );
}

// ------------------------------------------------------------- submissions ---
function Submissions() {
  const dataVersion = usePlan((s) => s.dataVersion);
  const subs = useAsync(() => api.preferences(), [dataVersion]);
  const courses = useAsync(() => api.courses(true), []);
  const fail = useFail();
  const title = (c: number) => courses.data?.find((x) => x.code === c)?.title ?? "";
  if (subs.loading && !subs.data) return <Spinner />;
  if (subs.error) return <ErrorState error={subs.error} onRetry={subs.reload} />;
  const rows = subs.data!;
  return (
    <Panel flush title={`Preference submissions (${rows.length})`} description="Only each faculty member's most recent submission is used by the scheduler."
      actions={<>
        <Button size="sm" icon={<Download className="h-3.5 w-3.5" />} disabled={!rows.length} onClick={() => api.exportPreferences().catch(fail)}>Export CSV</Button>
        <Button size="sm" variant="danger" disabled={!rows.length}
          onClick={() => confirm("Delete ALL preference submissions? This cannot be undone.") && api.clearPreferences().catch(fail)}>Clear all</Button>
      </>}>
      {rows.length === 0 ? <div className="p-6 text-center text-[13px] text-muted">No submissions yet.</div> : (
        <Table>
          <thead><tr><th>Submitted</th><th>Faculty</th><th>Principles</th><th>Ranked courses</th><th className="text-right">Fall</th><th className="text-right">Spring</th><th>Overload</th><th>Circumstances</th><th /></tr></thead>
          <tbody>{rows.map((s) => (
            <tr key={s.id}>
              <td className="whitespace-nowrap text-muted">{fmtDate(s.submitted_at)}</td>
              <td className="whitespace-nowrap font-medium">{s.faculty_name}<div className="text-xs font-normal text-faint">{s.email}</div></td>
              <td className="text-muted">{s.principles.join(", ") || "—"}</td>
              <td className="min-w-64 text-xs">{s.ranks.map((c, i) => <div key={c}><span className="tabular-nums text-faint">{i + 1}.</span> ECON {c} <span className="text-muted">{title(c)}</span></div>)}</td>
              <td className="text-right tabular-nums">{s.fall_target}</td><td className="text-right tabular-nums">{s.spring_target}</td>
              <td>{s.overload ? <Badge tone="amber">{s.overload_semester}</Badge> : <span className="text-faint">No</span>}</td>
              <td className="max-w-64 text-xs text-muted">{s.unique_circumstances || "—"}</td>
              <td><IconButton label="Delete submission" onClick={() => confirm(`Delete ${s.faculty_name}'s submission?`) && api.deletePreference(s.id).catch(fail)}><Trash2 className="h-3.5 w-3.5" /></IconButton></td>
            </tr>
          ))}</tbody>
        </Table>
      )}
    </Panel>
  );
}

// ------------------------------------------------------------------ faculty ---
function FacultyAdmin() {
  const { dataVersion, meta } = usePlan();
  const fac = useAsync(() => api.faculty(true), [dataVersion]);
  const fail = useFail();
  const [q, setQ] = useState("");
  const [name, setName] = useState("");
  const types = Object.keys(meta?.faculty_types ?? {});
  const update = async (f: Faculty, patch: Record<string, unknown>) => {
    try {
      const u = await api.updateFaculty(f.id, patch);
      fac.setData((l) => l?.map((x) => (x.id === f.id ? u : x)) ?? null);
    } catch (e) { fail(e); }
  };
  const add = async (e: FormEvent) => {
    e.preventDefault();
    try { await api.createFaculty({ name: name.trim(), email: "" }); setName(""); } catch (x) { fail(x); }
  };
  const shown = useMemo(() => (fac.data ?? []).filter((f) => f.name.toLowerCase().includes(q.toLowerCase())), [fac.data, q]);
  if (fac.loading && !fac.data) return <Spinner />;
  if (fac.error) return <ErrorState error={fac.error} onRetry={fac.reload} />;
  const inferred = fac.data!.filter((f) => f.type_source !== "Confirmed" && f.active).length;
  return (
    <div className="space-y-4">
      {inferred > 0 && <Alert tone="warning" title={`${inferred} faculty groups are inferred from teaching history`}>Workload checks depend on the faculty group. Confirm each one by selecting the correct group.</Alert>}
      <Panel flush title={`Faculty roster (${fac.data!.length})`}
        description="Tenured 3/yr · Full-time teaching & temporary 6/yr · Adjunct 1–2/yr. An approved overload raises the annual ceiling for extra compensation; a reduction lowers it."
        actions={<>
          <div className="relative"><Search className="absolute left-2.5 top-2 h-4 w-4 text-faint" />
            <input className={inputBase + " w-48 pl-8"} placeholder="Search" value={q} onChange={(e) => setQ(e.target.value)} /></div>
          <form onSubmit={add} className="flex gap-2">
            <input className={inputBase + " w-44"} placeholder="Last, First" value={name} onChange={(e) => setName(e.target.value)} />
            <Button size="sm" type="submit" icon={<Plus className="h-3.5 w-3.5" />} disabled={name.trim().length < 3}>Add</Button>
          </form>
        </>}>
        <Table maxH="max-h-[640px]">
          <thead><tr><th>Name</th><th>Faculty group</th><th>Reduction / yr</th><th>Approved overload</th><th className="text-right">History (UG / grad per yr)</th><th className="text-right">Forms</th><th>Active</th><th /></tr></thead>
          <tbody>{shown.map((f) => (
            <tr key={f.id} className={f.active ? "" : "opacity-50"}>
              <td className="whitespace-nowrap font-medium">{f.name}</td>
              <td>
                <div className="flex items-center gap-2">
                  <select className={inputBase + " h-7 w-44 text-xs"} value={f.faculty_type} onChange={(e) => update(f, { faculty_type: e.target.value })}>
                    {types.map((t) => <option key={t}>{t}</option>)}
                  </select>
                  {f.type_source === "Confirmed"
                    ? <button className="text-[11px] text-faint hover:text-fg" title="Revert to the history-inferred group" onClick={() => update(f, { clear_type: true })}>Confirmed</button>
                    : <Badge tone="amber">Inferred</Badge>}
                </div>
              </td>
              <td><input type="number" min={0} max={6} className={inputBase + " h-7 w-16 text-xs tabular-nums"} value={f.annual_reduction}
                onChange={(e) => update(f, { annual_reduction: Number(e.target.value), faculty_type: f.faculty_type })} /></td>
              <td>
                <div className="flex items-center gap-2">
                  <Switch checked={f.overloading} onChange={(v) => update(f, { overloading: v, overload_semester: v ? "Both" : "None" })} />
                  {f.overloading && (
                    <select className={inputBase + " h-7 w-24 text-xs"} value={f.overload_semester} onChange={(e) => update(f, { overloading: true, overload_semester: e.target.value })}>
                      {["Fall", "Spring", "Both"].map((s) => <option key={s}>{s}</option>)}
                    </select>
                  )}
                </div>
              </td>
              <td className="text-right tabular-nums text-muted">{f.ug_lectures_per_year} / {f.grad_sections_per_year}</td>
              <td className="text-right tabular-nums">{f.submissions}</td>
              <td><Switch checked={f.active} onChange={(v) => update(f, { active: v })} /></td>
              <td><IconButton label="Delete faculty member" onClick={() => confirm(`Delete ${f.name} and their submissions?`) && api.deleteFaculty(f.id).catch(fail)}><Trash2 className="h-3.5 w-3.5" /></IconButton></td>
            </tr>
          ))}</tbody>
        </Table>
      </Panel>
    </div>
  );
}

// ------------------------------------------------------------------ courses ---
function CourseAdmin() {
  const dataVersion = usePlan((s) => s.dataVersion);
  const list = useAsync(() => api.courses(true), [dataVersion]);
  const fail = useFail();
  const [q, setQ] = useState("");
  const [draft, setDraft] = useState({ code: "", title: "", description: "" });
  const save = async (c: Course, patch: Partial<Course>) => {
    try {
      const u = await api.updateCourse(c.code, patch);
      list.setData((l) => l?.map((x) => (x.code === c.code ? { ...x, ...u, times_offered: x.times_offered } : x)) ?? null);
    } catch (e) { fail(e); }
  };
  const add = async (e: FormEvent) => {
    e.preventDefault();
    try { await api.createCourse({ code: Number(draft.code), title: draft.title.trim(), description: draft.description.trim() }); setDraft({ code: "", title: "", description: "" }); }
    catch (x) { fail(x); }
  };
  if (list.loading && !list.data) return <Spinner />;
  if (list.error) return <ErrorState error={list.error} onRetry={list.reload} />;
  const shown = list.data!.filter((c) => matchCourse(c, q));
  const core = (c: Course) => c.category.startsWith("Core") || c.category === "Recitation";
  return (
    <div className="space-y-4">
      <Panel title="Add a course" description="Undergraduate only (1000–4999). Graduate courses are rejected.">
        <form onSubmit={add} className="grid gap-3 md:grid-cols-[110px_1fr_1.5fr_auto]">
          <input className={inputCls + " tabular-nums"} placeholder="3999" value={draft.code} onChange={(e) => setDraft({ ...draft, code: e.target.value.replace(/\D/g, "").slice(0, 4) })} />
          <input className={inputCls} placeholder="Title" value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} />
          <input className={inputCls} placeholder="Description (optional)" value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })} />
          <Button variant="primary" type="submit" icon={<Plus className="h-3.5 w-3.5" />} disabled={draft.code.length !== 4 || !draft.title.trim()}>Add course</Button>
        </form>
      </Panel>
      <Panel flush title={`Catalog (${list.data!.length})`} description="Inactive courses are hidden from the form and excluded from planning. Titles save when the field loses focus."
        actions={<div className="relative"><Search className="absolute left-2.5 top-2 h-4 w-4 text-faint" />
          <input className={inputBase + " w-56 pl-8"} placeholder="Code, level or title" value={q} onChange={(e) => setQ(e.target.value)} /></div>}>
        <Table maxH="max-h-[640px]">
          <thead><tr><th>Code</th><th>Title</th><th>Category</th><th>Prerequisites</th><th className="text-right">Terms offered</th><th>Active</th><th /></tr></thead>
          <tbody>{shown.map((c) => (
            <tr key={c.code} className={c.active ? "" : "opacity-50"}>
              <td className="font-medium tabular-nums">ECON {c.code}</td>
              <td className="min-w-72"><input className={inputBase + " h-7 w-full"} defaultValue={c.title}
                onBlur={(e) => e.target.value.trim() && e.target.value !== c.title && save(c, { title: e.target.value.trim() })} /></td>
              <td>{core(c) ? <Badge tone="red">{c.category}</Badge> : <Badge>{c.category}</Badge>}</td>
              <td className="text-xs text-muted">{c.prerequisites}</td>
              <td className="text-right tabular-nums">{c.times_offered}</td>
              <td><Switch checked={c.active} disabled={core(c)} onChange={(v) => save(c, { active: v })} /></td>
              <td>{!core(c) && <IconButton label="Delete course" onClick={() => confirm(`Delete ECON ${c.code}?`) && api.deleteCourse(c.code).catch(fail)}><Trash2 className="h-3.5 w-3.5" /></IconButton>}</td>
            </tr>
          ))}</tbody>
        </Table>
      </Panel>
    </div>
  );
}

// -------------------------------------------------------------------- users ---
function UsersAdmin() {
  const me = useAuth((s) => s.user);
  const users = useAsync(() => api.users(), []);
  const faculty = useAsync(() => api.faculty(), []);
  const fail = useFail();
  const toast = useUI((s) => s.toast);
  const [draft, setDraft] = useState({ name: "", email: "", password: "", role: "faculty" as Role, faculty_id: 0 });
  const add = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await api.createUser({ ...draft, faculty_id: draft.faculty_id || null });
      toast({ title: "Account created", body: draft.email, tone: "success" });
      setDraft({ name: "", email: "", password: "", role: "faculty", faculty_id: 0 });
      users.reload();
    } catch (x) { fail(x); }
  };
  const update = async (id: number, patch: Record<string, unknown>) => { try { await api.updateUser(id, patch); users.reload(); } catch (e) { fail(e); } };
  if (users.loading && !users.data) return <Spinner />;
  if (users.error) return <ErrorState error={users.error} onRetry={users.reload} />;
  return (
    <div className="space-y-4">
      <Panel title="Create an account" description="Faculty accounts should be linked to a roster entry so their preference submissions are attributed correctly.">
        <form onSubmit={add} className="grid gap-3 md:grid-cols-3 xl:grid-cols-6">
          <Field label="Name"><input className={inputCls} value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} /></Field>
          <Field label="Email"><input className={inputCls} type="email" value={draft.email} onChange={(e) => setDraft({ ...draft, email: e.target.value })} /></Field>
          <Field label="Temporary password" hint="At least 8 characters"><input className={inputCls} type="password" value={draft.password} onChange={(e) => setDraft({ ...draft, password: e.target.value })} /></Field>
          <Field label="Role">
            <select className={inputCls} value={draft.role} onChange={(e) => setDraft({ ...draft, role: e.target.value as Role })}>
              <option value="faculty">Faculty</option><option value="admin">Scheduler (admin)</option>
            </select>
          </Field>
          <Field label="Faculty roster link">
            <select className={inputCls} value={draft.faculty_id} onChange={(e) => {
              const f = faculty.data?.find((x) => x.id === Number(e.target.value));
              setDraft({ ...draft, faculty_id: Number(e.target.value), name: draft.name || (f ? f.name.split(", ").reverse().join(" ") : "") });
            }}>
              <option value={0}>None</option>{faculty.data?.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
            </select>
          </Field>
          <div className="flex items-end"><Button variant="primary" type="submit" className="w-full" disabled={!draft.name || !draft.email || draft.password.length < 8}>Create account</Button></div>
        </form>
      </Panel>
      <Panel flush title={`Accounts (${users.data!.length})`}>
        <Table>
          <thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Linked faculty</th><th>Last sign-in</th><th>Active</th><th /></tr></thead>
          <tbody>{users.data!.map((u) => (
            <tr key={u.id}>
              <td className="font-medium">{u.name}{u.id === me?.id && <span className="ml-1.5 text-xs text-faint">(you)</span>}</td>
              <td className="text-muted">{u.email}</td>
              <td>
                <select className={inputBase + " h-7 w-36 text-xs"} value={u.role} disabled={u.id === me?.id} onChange={(e) => update(u.id, { role: e.target.value })}>
                  <option value="faculty">Faculty</option><option value="admin">Scheduler (admin)</option>
                </select>
              </td>
              <td>
                <select className={inputBase + " h-7 w-48 text-xs"} value={u.faculty_id ?? 0}
                  onChange={(e) => update(u.id, Number(e.target.value) ? { faculty_id: Number(e.target.value) } : { unlink_faculty: true })}>
                  <option value={0}>None</option>{faculty.data?.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
                </select>
              </td>
              <td className="text-xs text-muted">{u.last_login ? fmtDate(u.last_login) : "Never"}</td>
              <td><Switch checked={u.active} disabled={u.id === me?.id} onChange={(v) => update(u.id, { active: v })} /></td>
              <td className="whitespace-nowrap">
                <Button size="sm" variant="ghost" onClick={() => {
                  const pw = prompt(`New password for ${u.email} (min 8 characters)`);
                  if (pw) update(u.id, { password: pw });
                }}>Reset password</Button>
                {u.id !== me?.id && <IconButton label="Delete account" onClick={() => confirm(`Delete ${u.email}?`) && api.deleteUser(u.id).then(users.reload).catch(fail)}><Trash2 className="h-3.5 w-3.5" /></IconButton>}
              </td>
            </tr>
          ))}</tbody>
        </Table>
      </Panel>
    </div>
  );
}

// --------------------------------------------------------------------- data ---
function DataAdmin() {
  const dataVersion = usePlan((s) => s.dataVersion);
  const terms = useAsync(() => api.enrollmentTerms(), [dataVersion]);
  const toast = useUI((s) => s.toast);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const upload = async () => {
    if (!file) return;
    setBusy(true);
    try { const r = await api.uploadEnrollment(file); toast({ title: `Added ${r.added} enrollment records`, tone: "success" }); setFile(null); }
    catch (e) { toast({ title: "Upload failed", body: (e as Error).message, tone: "error" }); } finally { setBusy(false); }
  };
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Panel title="Upload additional semester data"
        description="Excel or CSV with the ECON_Enrollment.xlsx columns: ACADEMIC_PERIOD_DESC, CAMPUS, Course #, Course Title, Instructional Method, Instructor, Schedule, MAXIMUM_ENROLLMENT, UG_ENROLLMENT.">
        <div className="flex flex-wrap items-center gap-3">
          <input type="file" accept=".xlsx,.csv" onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="text-[13px] file:mr-3 file:h-8 file:rounded-md file:border file:border-line-strong file:bg-surface file:px-3 file:text-[13px] file:text-fg" />
          <Button variant="primary" icon={<Upload className="h-3.5 w-3.5" />} loading={busy} disabled={!file} onClick={upload}>Upload and merge</Button>
        </div>
      </Panel>
      <Panel flush title="Enrollment history on file" description="Undergraduate sections and students per term.">
        {terms.loading ? <Spinner /> : terms.error ? <div className="p-4"><ErrorState error={terms.error} /></div> : (
          <Table maxH="max-h-96">
            <thead><tr><th>Term</th><th className="text-right">UG sections</th><th className="text-right">UG students</th></tr></thead>
            <tbody>{terms.data!.map((t) => <tr key={t.term}><td>{t.term}</td><td className="text-right tabular-nums">{t.sections}</td><td className="text-right tabular-nums">{t.students.toLocaleString()}</td></tr>)}</tbody>
          </Table>
        )}
      </Panel>
    </div>
  );
}

// ------------------------------------------------------------- publications ---
function Publications() {
  const dataVersion = usePlan((s) => s.dataVersion);
  const pubs = useAsync(() => api.publications(), [dataVersion]);
  const fail = useFail();
  if (pubs.loading && !pubs.data) return <Spinner />;
  if (pubs.error) return <ErrorState error={pubs.error} onRetry={pubs.reload} />;
  return (
    <Panel flush title="Published schedules" description="Each publish freezes the master schedule for a term as a new version. Exports use the registrar catalog-import layout.">
      {pubs.data!.length === 0 ? <div className="p-6 text-center text-[13px] text-muted">Nothing published yet. Publish from the Master Schedule.</div> : (
        <Table>
          <thead><tr><th>Term</th><th>Version</th><th>Published</th><th>By</th><th className="text-right">Sections</th><th>Open issues</th><th>Note</th><th /></tr></thead>
          <tbody>{pubs.data!.map((p) => (
            <tr key={p.id}>
              <td className="font-medium">{p.term}</td><td className="tabular-nums">v{p.version}</td><td className="text-muted">{fmtDate(p.published_at)}</td>
              <td>{p.published_by}</td><td className="text-right tabular-nums">{p.sections}</td>
              <td>{p.critical ? <Badge tone="red">{p.critical} critical</Badge> : <Badge tone="green">None critical</Badge>} <span className="text-xs text-muted">{p.warning} warnings</span></td>
              <td className="max-w-64 text-xs text-muted">{p.note || "—"}</td>
              <td><Button size="sm" icon={<Download className="h-3.5 w-3.5" />} onClick={() => api.exportPublication(p.id).catch(fail)}>Catalog CSV</Button></td>
            </tr>
          ))}</tbody>
        </Table>
      )}
    </Panel>
  );
}
