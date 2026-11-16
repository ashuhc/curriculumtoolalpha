// Administration (scheduler role): submissions, faculty & overloads, catalog, users, data, publications.
import { Check, Download, Plus, RotateCcw, Search, Trash2, Upload, X } from "lucide-react";
import { useMemo, useRef, useState, type FormEvent } from "react";
import { Navigate } from "react-router-dom";
import { api, type Course, type Faculty, type Role } from "../api";
import { matchCourse } from "../components/CourseSelect";
import { Alert, Badge, Button, ConfirmDialog, ErrorState, Field, IconButton, PageHeader, Panel, Spinner, Switch, Table, Tabs, inputBase, inputCls } from "../components/ui";
import { fmtDate, useAsync } from "../lib/hooks";
import { useAuth, useIsAdmin } from "../store/auth";
import { usePlan } from "../store/plan";
import { useFlash, useUI } from "../store/ui";

type Tab = "submissions" | "faculty" | "courses" | "users" | "data" | "publications";

function useFail() {
  const toast = useUI((s) => s.toast);
  return (e: unknown) => toast({ title: "Action failed", body: (e as Error).message, tone: "error" });
}

/** Toast title and body for a faculty edit. */
function facultyToast(f: Faculty, patch: Record<string, unknown>): [string, string] {
  if (patch.clear_type) return ["Faculty group unconfirmed", `${f.name}: reverted to the history-inferred group`];
  if (typeof patch.faculty_type === "string")
    return f.type_source === "Confirmed" && patch.faculty_type !== f.faculty_type
      ? ["Faculty group updated", `${f.name}: ${f.faculty_type} → ${patch.faculty_type}`]
      : ["Faculty group confirmed", `${f.name}: ${patch.faculty_type}`];
  for (const sem of ["fall", "spring"] as const) {
    const k = `${sem}_courseload`;
    if (k in patch) {
      const label = sem === "fall" ? "Fall" : "Spring";
      return ["Courseload updated", patch[k] === null
        ? `${f.name}: ${label} courseload cleared (uses the preference form, then teaching history)`
        : `${f.name}: ${label} courseload set to ${patch[k]} ${patch[k] === 1 ? "course" : "courses"}`];
    }
  }
  if ("overloading" in patch && patch.overloading === false) return ["Faculty settings updated", `${f.name}: overload approval removed`];
  if ("overload_semester" in patch)
    return ["Faculty settings updated", `${f.name}: overload approved for ${patch.overload_semester === "Both" ? "both semesters" : patch.overload_semester}`];
  if ("active" in patch) return ["Faculty settings updated", `${f.name}: ${patch.active ? "reactivated" : "deactivated"}`];
  return ["Faculty settings updated", f.name];
}

export default function Admin() {
  const isAdmin = useIsAdmin();
  const user = useAuth((s) => s.user);
  const [tab, setTab] = useState<Tab>("submissions");
  if (!user) return <Navigate to="/login" state={{ from: "/admin" }} replace />;
  if (!isAdmin) return <Alert tone="warning" title="Scheduler Access Required">Your account has the faculty role.</Alert>;
  return (
    <>
      <PageHeader eyebrow="Administration" title="Administration" description="Manage preference submissions, the faculty roster and overloads, the course catalog, user accounts and enrollment data." />
      <Tabs value={tab} onChange={setTab} className="mb-5" tabs={[
        { id: "submissions", label: "Submissions" }, { id: "faculty", label: "Faculty & Overloads" }, { id: "courses", label: "Course Catalog" },
        { id: "users", label: "Users & Roles" }, { id: "data", label: "Enrollment Data" }, { id: "publications", label: "Publications" }]} />
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
  const success = useUI((s) => s.success);
  const title = (c: number) => courses.data?.find((x) => x.code === c)?.title ?? "";
  if (subs.loading && !subs.data) return <Spinner />;
  if (subs.error) return <ErrorState error={subs.error} onRetry={subs.reload} />;
  const rows = subs.data!;
  return (
    <Panel flush title={`Preference Submissions (${rows.length})`} description="Only each faculty member's most recent submission is used by the scheduler."
      actions={<>
        <Button size="sm" icon={<Download className="h-3.5 w-3.5" />} disabled={!rows.length} onClick={() => api.exportPreferences().then(() => success("Export downloaded", "teacher_preferences_export.csv")).catch(fail)}>Export CSV</Button>
        <Button size="sm" variant="danger" disabled={!rows.length}
          onClick={() => confirm("Delete ALL preference submissions? This cannot be undone.") &&
            api.clearPreferences().then(() => success("All submissions cleared", `${rows.length} removed`)).catch(fail)}>Clear All</Button>
      </>}>
      {rows.length === 0 ? <div className="p-6 text-center text-[13px] text-muted">No submissions yet.</div> : (
        <Table>
          <thead><tr><th>Submitted</th><th>Faculty</th><th>Submitted By</th><th>Principles</th><th>Ranked Courses</th><th className="text-right">Fall</th><th className="text-right">Spring</th><th>Overload</th><th>Circumstances</th><th /></tr></thead>
          <tbody>{rows.map((s) => (
            <tr key={s.id}>
              <td className="whitespace-nowrap text-muted">{fmtDate(s.submitted_at)}</td>
              <td className="whitespace-nowrap font-medium">{s.faculty_name}<div className="text-xs font-normal text-faint">{s.email}</div></td>
              <td className="whitespace-nowrap text-xs text-muted">{s.submitted_by ?? "—"}</td>
              <td className="text-muted">{s.principles.join(", ") || "—"}</td>
              <td className="min-w-64 text-xs">{s.ranks.map((c, i) => <div key={c}><span className="tabular-nums text-faint">{i + 1}.</span> ECON {c} <span className="text-muted">{title(c)}</span></div>)}</td>
              <td className="text-right tabular-nums">{s.fall_target}</td><td className="text-right tabular-nums">{s.spring_target}</td>
              <td>{s.overload ? <Badge tone="amber">{s.overload_semester}</Badge> : <span className="text-faint">No</span>}</td>
              <td className="max-w-64 text-xs text-muted">{s.unique_circumstances || "—"}</td>
              <td><IconButton label="Delete Submission" onClick={() => confirm(`Delete ${s.faculty_name}'s submission?`) &&
                api.deletePreference(s.id).then(() => success("Submission deleted", s.faculty_name)).catch(fail)}><Trash2 className="h-3.5 w-3.5" /></IconButton></td>
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
  const success = useUI((s) => s.success);
  const flash = useFlash();
  const [q, setQ] = useState("");
  const [name, setName] = useState("");
  const types = Object.keys(meta?.faculty_types ?? {});
  // Every edit is optimistic: the row, badge and banner count change at once, then the
  // PUT response (or a reload on failure) settles it. A per-row counter drops stale
  // responses so quick successive edits can't be overwritten by an older reply.
  const seq = useRef<Record<number, number>>({});
  // Writes for one row go out one at a time: concurrent PUTs can commit out of order on the
  // server, which would let an older choice win. The UI still updates instantly (optimistic).
  const queue = useRef<Record<number, Promise<unknown>>>({});
  const mutate = async (f: Faculty, optimistic: Partial<Faculty>, request: () => Promise<Faculty>, [title, body]: [string, string]) => {
    const n = (seq.current[f.id] = (seq.current[f.id] ?? 0) + 1);
    fac.setData((l) => l?.map((x) => (x.id === f.id ? { ...x, ...optimistic } : x)) ?? null);
    try {
      const send = (queue.current[f.id] ?? Promise.resolve()).catch(() => undefined).then(request);
      queue.current[f.id] = send;
      const u = await send;
      if (seq.current[f.id] !== n) return;
      fac.setData((l) => l?.map((x) => (x.id === f.id ? u : x)) ?? null);
      success(title, body, `faculty:${f.id}`);
    } catch (e) {
      fail(e);
      if (seq.current[f.id] === n) fac.reload();
    }
  };
  const update = (f: Faculty, patch: Record<string, unknown>) => {
    const optimistic: Partial<Faculty> = { ...(patch as Partial<Faculty>) };
    if (typeof patch.faculty_type === "string") optimistic.type_source = "Confirmed";
    if (patch.clear_type) optimistic.type_source = "Inferred from history";
    delete (optimistic as Record<string, unknown>).clear_type;
    return mutate(f, optimistic, () => api.updateFaculty(f.id, patch), facultyToast(f, patch));
  };
  // Reset to Default: inferred group, automatic courseloads, seeded overload approval
  const resetRow = (f: Faculty) => mutate(f, {
    type_source: "Inferred from history", fall_courseload: null, spring_courseload: null,
    overloading: f.default_overloading, overload_semester: f.default_overload_semester,
  }, () => api.resetFaculty(f.id), ["Faculty row reset to default", `${f.name}: ${customizedOf(f).join(", ")} restored`]);
  const [resetAllOpen, setResetAllOpen] = useState(false);
  const [resetAllBusy, setResetAllBusy] = useState(false);
  const resetAll = async () => {
    setResetAllBusy(true);
    try {
      const r = await api.resetAllFaculty();
      fac.reload();
      setResetAllOpen(false);
      success("All faculty reset to default", `${r.reset} ${r.reset === 1 ? "row" : "rows"} restored to inferred groups, automatic courseloads and seeded overloads`,
        (fac.data ?? []).filter((x) => r.faculty.includes(x.name)).map((x) => `faculty:${x.id}`));
    } catch (e) { fail(e); } finally { setResetAllBusy(false); }
  };
  const add = async (e: FormEvent) => {
    e.preventDefault();
    try {
      const f = await api.createFaculty({ name: name.trim(), email: "" });
      setName("");
      success("Faculty member added", f.name, `faculty:${f.id}`);
    } catch (x) { fail(x); }
  };
  const shown = useMemo(() => (fac.data ?? []).filter((f) => f.name.toLowerCase().includes(q.toLowerCase())), [fac.data, q]);
  if (fac.loading && !fac.data) return <Spinner />;
  if (fac.error) return <ErrorState error={fac.error} onRetry={fac.reload} />;
  const inferred = fac.data!.filter((f) => f.type_source !== "Confirmed" && f.active).length;
  const customizedRows = fac.data!.filter((f) => customizedOf(f).length > 0);
  return (
    <div className="space-y-4">
      {inferred > 0
        ? <Alert tone="warning" title={`${inferred} ${inferred === 1 ? "Faculty Group Needs" : "Faculty Groups Need"} Confirmation`}>These groups were inferred from teaching history. Workload checks depend on them, so confirm each one with the checkmark, or choose a different group from the list to save it as confirmed.</Alert>
        : <Alert tone="success" title="All Faculty Groups Confirmed">Workload checks use the confirmed group for every active faculty member.</Alert>}
      <Panel flush title={`Faculty Roster (${fac.data!.length})`}
        description="Tenured track / tenured 3/yr · Full-time teaching & temporary 6/yr · Adjunct 1–2/yr. Fall and Spring Courseload set how many courses each person teaches per semester; leave one blank to use their preference form, then teaching history. An approved overload raises the annual ceiling for extra compensation."
        actions={<>
          <div className="relative"><Search className="absolute left-2.5 top-2 h-4 w-4 text-faint" />
            <input className={inputBase + " w-48 pl-8"} placeholder="Search" value={q} onChange={(e) => setQ(e.target.value)} /></div>
          <Button size="sm" icon={<RotateCcw className="h-3.5 w-3.5" />} disabled={!customizedRows.length} onClick={() => setResetAllOpen(true)}
            title={customizedRows.length ? `Reset ${customizedRows.length} Customized ${customizedRows.length === 1 ? "Row" : "Rows"} to Default` : "No Rows Differ From Their Defaults"}>
            Reset All to Default
          </Button>
          <form onSubmit={add} className="flex gap-2">
            <input className={inputBase + " w-44"} placeholder="Last, First" value={name} onChange={(e) => setName(e.target.value)} />
            <Button size="sm" type="submit" icon={<Plus className="h-3.5 w-3.5" />} disabled={name.trim().length < 3}>Add</Button>
          </form>
        </>}>
        <Table>
          <thead><tr><th>Name</th><th>Faculty Group</th><th>Fall Courseload</th><th>Spring Courseload</th><th>Approved Overload</th><th className="text-right">History (UG / Grad per Year)</th><th className="text-right">Forms</th><th>Active</th><th /></tr></thead>
          <tbody>{shown.map((f) => (
            <tr key={f.id} className={`${f.active ? "" : "opacity-50"} ${flash(`faculty:${f.id}`)}`}>
              <td className="whitespace-nowrap font-medium">
                {/* Kept beside the name so it stays visible when the wide table scrolls sideways */}
                <span className="flex items-center gap-1.5">
                  {f.name}
                  {customizedOf(f).length > 0 && (
                    <IconButton label={`Reset to Default (${customizedOf(f).join(", ")})`} onClick={() => resetRow(f)}
                      className="h-6 w-6 text-faint hover:text-fg"><RotateCcw className="h-3.5 w-3.5" /></IconButton>
                  )}
                </span>
              </td>
              <td>
                <FacultyGroupCell f={f} types={types}
                  onChange={(v) => update(f, { faculty_type: v })}
                  onConfirm={() => update(f, { faculty_type: f.faculty_type })}
                  onRevert={() => update(f, { clear_type: true })} />
              </td>
              {(["fall", "spring"] as const).map((sem) => (
                <td key={sem}><CourseloadInput f={f} sem={sem} onChange={(v) => update(f, { [`${sem}_courseload`]: v })} /></td>
              ))}
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
              <td><IconButton label="Delete Faculty Member" onClick={() => confirm(`Delete ${f.name} and their submissions?`) &&
                api.deleteFaculty(f.id).then(() => success("Faculty member removed", f.name)).catch(fail)}><Trash2 className="h-3.5 w-3.5" /></IconButton></td>
            </tr>
          ))}</tbody>
        </Table>
      </Panel>
      <ConfirmDialog open={resetAllOpen} title="Reset All to Default?" confirmLabel="Reset All to Default" tone="danger" busy={resetAllBusy}
        onConfirm={resetAll} onCancel={() => setResetAllOpen(false)}>
        <p><span className="font-medium text-fg">{customizedRows.length}</span> faculty {customizedRows.length === 1 ? "row differs" : "rows differ"} from {customizedRows.length === 1 ? "its" : "their"} defaults. Resetting restores the history-inferred faculty group, automatic Fall and Spring courseloads, and the originally approved overloads.</p>
        <p>Active status, names and preference submissions are not changed. This can't be undone.</p>
      </ConfirmDialog>
    </div>
  );
}

/** Fields that differ from the inferred / seeded baseline (mirrors the server's `customized`). */
function customizedOf(f: Faculty): string[] {
  const out: string[] = [];
  if (f.type_source === "Confirmed") out.push("Faculty Group");
  if (f.fall_courseload !== null) out.push("Fall Courseload");
  if (f.spring_courseload !== null) out.push("Spring Courseload");
  const sem = (on: boolean, s: string) => (on ? s : "None");
  if (f.overloading !== f.default_overloading || sem(f.overloading, f.overload_semester) !== sem(f.default_overloading, f.default_overload_semester))
    out.push("Approved Overload");
  return out;
}

/** Semester courseload: blank = not set (placeholder "Auto"); 0–6 courses otherwise. */
function CourseloadInput({ f, sem, onChange }: { f: Faculty; sem: "fall" | "spring"; onChange: (v: number | null) => void }) {
  const label = sem === "fall" ? "Fall" : "Spring";
  const value = sem === "fall" ? f.fall_courseload : f.spring_courseload;
  return (
    <input type="number" inputMode="numeric" min={0} max={6} placeholder="Auto" aria-label={`${label} Courseload for ${f.name}`}
      title={`${label} courses for ${f.name}. Leave blank to use their preference form, then teaching history.`}
      className={inputBase + " h-7 w-[72px] text-xs tabular-nums placeholder:text-faint"} value={value ?? ""}
      onChange={(e) => {
        const raw = e.target.value.trim();
        if (raw === "") return onChange(null);
        const n = Math.round(Number(raw));
        if (Number.isFinite(n)) onChange(Math.max(0, Math.min(6, n)));
      }} />
  );
}

/** Faculty Group column: a dropdown that always saves, plus the status control (confirm ✓ or revertible Confirmed badge). */
function FacultyGroupCell({ f, types, onChange, onConfirm, onRevert }: {
  f: Faculty; types: string[]; onChange: (v: string) => void; onConfirm: () => void; onRevert: () => void;
}) {
  const confirmed = f.type_source === "Confirmed";
  return (
    <div className="flex items-center gap-2">
      <select aria-label={`Faculty Group for ${f.name}`} className={"h-7 w-[196px] text-xs " + inputBase} value={f.faculty_type}
        onChange={(e) => onChange(e.target.value)}>
        {types.map((t) => <option key={t}>{t}</option>)}
      </select>
      {confirmed ? (
        // Clicking the badge un-confirms; on hover/focus it previews that with an X
        <button type="button" onClick={onRevert} aria-label={`Confirmed: Revert ${f.name} to Inferred`} title="Revert to Inferred"
          className="group/st inline-flex h-6 w-[100px] items-center justify-center gap-1 rounded border border-transparent bg-emerald-500/10 text-[11px] font-medium text-emerald-600 outline-none transition-colors hover:border-line hover:bg-subtle hover:text-muted focus-visible:border-line focus-visible:bg-subtle focus-visible:text-muted focus-visible:ring-2 focus-visible:ring-fg/20 dark:text-emerald-400">
          <Check className="h-3 w-3 group-hover/st:hidden group-focus-visible/st:hidden" />
          <X className="hidden h-3 w-3 group-hover/st:block group-focus-visible/st:block" />
          <span className="group-hover/st:hidden group-focus-visible/st:hidden">Confirmed</span>
          <span className="hidden group-hover/st:inline group-focus-visible/st:inline">Unconfirm</span>
        </button>
      ) : (
        <div className="flex w-[100px] items-center gap-1.5">
          <Badge tone="amber" className="h-6 flex-1 justify-center">Inferred</Badge>
          <button type="button" onClick={onConfirm} aria-label={`Confirm ${f.faculty_type} for ${f.name}`} title={`Confirm ${f.faculty_type}`}
            className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded border border-emerald-600/30 bg-emerald-500/10 text-emerald-600 outline-none transition-colors hover:bg-emerald-500/20 focus-visible:ring-2 focus-visible:ring-emerald-500/40 dark:text-emerald-400">
            <Check className="h-3.5 w-3.5" />
          </button>
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ courses ---
function CourseAdmin() {
  const dataVersion = usePlan((s) => s.dataVersion);
  const list = useAsync(() => api.courses(true), [dataVersion]);
  const fail = useFail();
  const success = useUI((s) => s.success);
  const flash = useFlash();
  const [q, setQ] = useState("");
  const [draft, setDraft] = useState({ code: "", title: "", description: "" });
  const save = async (c: Course, patch: Partial<Course>) => {
    try {
      const u = await api.updateCourse(c.code, patch);
      list.setData((l) => l?.map((x) => (x.code === c.code ? { ...x, ...u, times_offered: x.times_offered } : x)) ?? null);
      const what = patch.title !== undefined ? `title changed to “${patch.title}”` : patch.active ? "activated" : "deactivated";
      success("Course updated", `ECON ${c.code}: ${what}`, `course:${c.code}`);
    } catch (e) { fail(e); }
  };
  const add = async (e: FormEvent) => {
    e.preventDefault();
    try {
      const c = await api.createCourse({ code: Number(draft.code), title: draft.title.trim(), description: draft.description.trim() });
      setDraft({ code: "", title: "", description: "" });
      success("Course added to the catalog", `ECON ${c.code} · ${c.title}`, `course:${c.code}`);
    } catch (x) { fail(x); }
  };
  if (list.loading && !list.data) return <Spinner />;
  if (list.error) return <ErrorState error={list.error} onRetry={list.reload} />;
  const shown = list.data!.filter((c) => matchCourse(c, q));
  const core = (c: Course) => c.category.startsWith("Core") || c.category === "Recitation";
  return (
    <div className="space-y-4">
      <Panel title="Add a Course" description="Undergraduate only (1000–4999). Graduate courses are rejected.">
        <form onSubmit={add} className="grid gap-3 md:grid-cols-[110px_1fr_1.5fr_auto]">
          <input className={inputCls + " tabular-nums"} placeholder="3999" value={draft.code} onChange={(e) => setDraft({ ...draft, code: e.target.value.replace(/\D/g, "").slice(0, 4) })} />
          <input className={inputCls} placeholder="Title" value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} />
          <input className={inputCls} placeholder="Description (optional)" value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })} />
          <Button variant="primary" type="submit" icon={<Plus className="h-3.5 w-3.5" />} disabled={draft.code.length !== 4 || !draft.title.trim()}>Add Course</Button>
        </form>
      </Panel>
      <Panel flush title={`Catalog (${list.data!.length})`} description="Inactive courses are hidden from the form and excluded from planning. Titles save when the field loses focus."
        actions={<div className="relative"><Search className="absolute left-2.5 top-2 h-4 w-4 text-faint" />
          <input className={inputBase + " w-56 pl-8"} placeholder="Code, level or title" value={q} onChange={(e) => setQ(e.target.value)} /></div>}>
        <Table>
          <thead><tr><th>Code</th><th>Title</th><th>Category</th><th>Prerequisites</th><th className="text-right">Terms Offered</th><th>Active</th><th /></tr></thead>
          <tbody>{shown.map((c) => (
            <tr key={c.code} className={`${c.active ? "" : "opacity-50"} ${flash(`course:${c.code}`)}`}>
              <td className="font-medium tabular-nums">ECON {c.code}</td>
              <td className="min-w-72"><input className={inputBase + " h-7 w-full"} defaultValue={c.title}
                onBlur={(e) => e.target.value.trim() && e.target.value !== c.title && save(c, { title: e.target.value.trim() })} /></td>
              <td>{core(c) ? <Badge tone="red">{c.category}</Badge> : <Badge>{c.category}</Badge>}</td>
              <td className="text-xs text-muted">{c.prerequisites}</td>
              <td className="text-right tabular-nums">{c.times_offered}</td>
              <td><Switch checked={c.active} disabled={core(c)} onChange={(v) => save(c, { active: v })} /></td>
              <td>{!core(c) && <IconButton label="Delete Course" onClick={() => confirm(`Delete ECON ${c.code}?`) &&
                    api.deleteCourse(c.code).then(() => success("Course deleted", `ECON ${c.code} · ${c.title}`)).catch(fail)}><Trash2 className="h-3.5 w-3.5" /></IconButton>}</td>
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
  const success = useUI((s) => s.success);
  const flash = useFlash();
  const [draft, setDraft] = useState({ name: "", email: "", password: "", role: "faculty" as Role, faculty_id: 0 });
  const add = async (e: FormEvent) => {
    e.preventDefault();
    try {
      const u = await api.createUser({ ...draft, faculty_id: draft.faculty_id || null });
      success("Account created", `${u.email} · ${u.role === "admin" ? "Scheduler" : "Faculty"}`, `user:${u.id}`);
      setDraft({ name: "", email: "", password: "", role: "faculty", faculty_id: 0 });
      users.reload();
    } catch (x) { fail(x); }
  };
  const update = async (id: number, patch: Record<string, unknown>) => {
    const email = users.data?.find((u) => u.id === id)?.email ?? "";
    try {
      await api.updateUser(id, patch);
      users.reload();
      const what = patch.password ? "password reset" : patch.role ? `role set to ${patch.role === "admin" ? "Scheduler" : "Faculty"}`
        : patch.unlink_faculty ? "unlinked from the faculty roster" : "faculty_id" in patch ? "linked to the faculty roster"
        : patch.active === false ? "deactivated" : patch.active ? "reactivated" : "updated";
      success("Account updated", `${email}: ${what}`, `user:${id}`);
    } catch (e) { fail(e); }
  };
  if (users.loading && !users.data) return <Spinner />;
  if (users.error) return <ErrorState error={users.error} onRetry={users.reload} />;
  return (
    <div className="space-y-4">
      <Panel title="Create an Account" description="Faculty accounts should be linked to a roster entry so their preference submissions are attributed correctly.">
        <form onSubmit={add} className="grid gap-3 md:grid-cols-3 xl:grid-cols-6">
          <Field label="Name"><input className={inputCls} value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} /></Field>
          <Field label="Email"><input className={inputCls} type="email" value={draft.email} onChange={(e) => setDraft({ ...draft, email: e.target.value })} /></Field>
          <Field label="Temporary Password" hint="At least 8 characters"><input className={inputCls} type="password" value={draft.password} onChange={(e) => setDraft({ ...draft, password: e.target.value })} /></Field>
          <Field label="Role">
            <select className={inputCls} value={draft.role} onChange={(e) => setDraft({ ...draft, role: e.target.value as Role })}>
              <option value="faculty">Faculty</option><option value="admin">Scheduler (Admin)</option>
            </select>
          </Field>
          <Field label="Faculty Roster Link">
            <select className={inputCls} value={draft.faculty_id} onChange={(e) => {
              const f = faculty.data?.find((x) => x.id === Number(e.target.value));
              setDraft({ ...draft, faculty_id: Number(e.target.value), name: draft.name || (f ? f.name.split(", ").reverse().join(" ") : "") });
            }}>
              <option value={0}>None</option>{faculty.data?.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
            </select>
          </Field>
          <div className="flex items-end"><Button variant="primary" type="submit" className="w-full" disabled={!draft.name || !draft.email || draft.password.length < 8}>Create Account</Button></div>
        </form>
      </Panel>
      <Panel flush title={`Accounts (${users.data!.length})`}>
        <Table>
          <thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Linked Faculty</th><th>Last Sign-In</th><th>Active</th><th /></tr></thead>
          <tbody>{users.data!.map((u) => (
            <tr key={u.id} className={flash(`user:${u.id}`)}>
              <td className="font-medium">{u.name}{u.id === me?.id && <span className="ml-1.5 text-xs text-faint">(you)</span>}</td>
              <td className="text-muted">{u.email}</td>
              <td>
                <select className={inputBase + " h-7 w-36 text-xs"} value={u.role} disabled={u.id === me?.id} onChange={(e) => update(u.id, { role: e.target.value })}>
                  <option value="faculty">Faculty</option><option value="admin">Scheduler (Admin)</option>
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
                }}>Reset Password</Button>
                {u.id !== me?.id && <IconButton label="Delete Account" onClick={() => confirm(`Delete ${u.email}?`) &&
                  api.deleteUser(u.id).then(() => { users.reload(); success("Account deleted", u.email); }).catch(fail)}><Trash2 className="h-3.5 w-3.5" /></IconButton>}
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
  const success = useUI((s) => s.success);
  const flash = useFlash();
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const upload = async () => {
    if (!file) return;
    setBusy(true);
    try {
      const r = await api.uploadEnrollment(file);
      success("Enrollment data merged", `${r.added} records added from ${file.name}`, "enrollment-history");
      setFile(null);
    }
    catch (e) { toast({ title: "Upload failed", body: (e as Error).message, tone: "error" }); } finally { setBusy(false); }
  };
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Panel title="Upload Additional Semester Data"
        description="Excel or CSV with the ECON_Enrollment.xlsx columns: ACADEMIC_PERIOD_DESC, CAMPUS, Course #, Course Title, Instructional Method, Instructor, Schedule, MAXIMUM_ENROLLMENT, UG_ENROLLMENT.">
        <div className="flex flex-wrap items-center gap-3">
          <input type="file" accept=".xlsx,.csv" onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="text-[13px] file:mr-3 file:h-8 file:rounded-md file:border file:border-line-strong file:bg-surface file:px-3 file:text-[13px] file:text-fg" />
          <Button variant="primary" icon={<Upload className="h-3.5 w-3.5" />} loading={busy} disabled={!file} onClick={upload}>Upload and Merge</Button>
        </div>
      </Panel>
      <Panel flush title="Enrollment History on File" description="Undergraduate sections and students per term." className={flash("enrollment-history")}>
        {terms.loading ? <Spinner /> : terms.error ? <div className="p-4"><ErrorState error={terms.error} /></div> : (
          <Table maxH="max-h-96">
            <thead><tr><th>Term</th><th className="text-right">UG Sections</th><th className="text-right">UG Students</th></tr></thead>
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
  const success = useUI((s) => s.success);
  if (pubs.loading && !pubs.data) return <Spinner />;
  if (pubs.error) return <ErrorState error={pubs.error} onRetry={pubs.reload} />;
  return (
    <Panel flush title="Published Schedules" description="Each publication freezes a term schedule as a numbered version. Exports follow the registrar's catalog-import format.">
      {pubs.data!.length === 0 ? <div className="p-6 text-center text-[13px] text-muted">No schedules published yet. Publish a term from the Term Schedule.</div> : (
        <Table>
          <thead><tr><th>Term</th><th>Version</th><th>Published</th><th>By</th><th className="text-right">Sections</th><th>Open Issues</th><th>Note</th><th /></tr></thead>
          <tbody>{pubs.data!.map((p) => (
            <tr key={p.id}>
              <td className="font-medium">{p.term}</td><td className="tabular-nums">v{p.version}</td><td className="text-muted">{fmtDate(p.published_at)}</td>
              <td>{p.published_by}</td><td className="text-right tabular-nums">{p.sections}</td>
              <td>{p.critical ? <Badge tone="red">{p.critical} Critical</Badge> : <Badge tone="green">None Critical</Badge>} <span className="text-xs text-muted">{p.warning} Warnings</span></td>
              <td className="max-w-64 text-xs text-muted">{p.note || "—"}</td>
              <td><Button size="sm" icon={<Download className="h-3.5 w-3.5" />} onClick={() => api.exportPublication(p.id).then(() => success("Catalog CSV downloaded", `${p.term} v${p.version}`)).catch(fail)}>Catalog CSV</Button></td>
            </tr>
          ))}</tbody>
        </Table>
      )}
    </Panel>
  );
}
