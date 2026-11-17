// Add Section / Edit Manual Section: lets schedulers hand-place a section (an elective the solver
// didn't offer, overflow demand, a missing core course) with its own instructor, block and cap.
import { useEffect, useMemo, useState } from "react";
import { api, type Course, type ManualSection, type Meta, type ScheduleResponse } from "../api";
import { usePlan } from "../store/plan";
import { useSchedule } from "../store/schedule";
import { useUI } from "../store/ui";
import { CourseSelect } from "./CourseSelect";
import { Alert, Button, Field, Modal, Segmented, inputCls } from "./ui";

export interface SectionPrefill { code?: number; remote?: boolean }

const REMOTE_CAP = 25;
type Modality = "In-Person" | "Remote";

export function SectionEditor({ open, onClose, data, meta, prefill, editing, onSaved }: {
  open: boolean; onClose: () => void; data: ScheduleResponse; meta: Meta;
  prefill?: SectionPrefill; editing?: ManualSection | null; onSaved?: (sectionId: string) => void;
}) {
  const settings = usePlan((s) => s.settings);
  const success = useUI((s) => s.success);
  const [courses, setCourses] = useState<Course[]>([]);
  const [code, setCode] = useState<number | null>(null);
  const [title, setTitle] = useState("");
  const [titleTouched, setTitleTouched] = useState(false);
  const [sectionNo, setSectionNo] = useState(1);
  const [instructor, setInstructor] = useState("");
  const [modality, setModality] = useState<Modality>("In-Person");
  const [sequence, setSequence] = useState("");
  const [cap, setCap] = useState(settings.small_section_cap);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => { if (open && !courses.length) api.courses().then(setCourses).catch(() => undefined); }, [open, courses.length]);

  // Section numbers in use for a course (generated + hand-added), excluding the one being edited
  const usedNumbers = (c: number) => new Set(data.master.filter((r) => r.course === `ECON ${c}` && r.section_id !== editing?.section_id)
    .map((r) => Number(r.section)));
  const nextFree = (c: number) => { const used = usedNumbers(c); let n = 1; while (used.has(n)) n++; return n; };
  const typicalCap = (c: number, remote: boolean) => {
    if (remote) return REMOTE_CAP;
    const caps = data.master.filter((r) => r.course === `ECON ${c}` && !r.modality.startsWith("Online") && r.component === "Lecture")
      .map((r) => r.section_cap).sort((a, b) => a - b);
    return caps.length ? Math.min(caps[Math.floor(caps.length / 2)], settings.large_lecture_cap) : settings.small_section_cap;
  };

  // (Re)initialise each time the dialog opens
  useEffect(() => {
    if (!open) return;
    setError(null); setBusy(false);
    if (editing) {
      setCode(editing.code); setTitle(editing.title); setTitleTouched(true); setSectionNo(editing.section_no);
      setInstructor(editing.instructor ?? ""); setModality(editing.modality); setSequence(editing.sequence ?? ""); setCap(editing.cap);
    } else {
      const c = prefill?.code ?? null;
      const remote = !!prefill?.remote;
      setCode(c); setTitleTouched(false); setTitle(""); setInstructor(""); setSequence("");
      setModality(remote ? "Remote" : "In-Person");
      setSectionNo(c ? nextFree(c) : 1); setCap(c ? typicalCap(c, remote) : remote ? REMOTE_CAP : settings.small_section_cap);
    }
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  // Course title follows the course until the user types their own
  useEffect(() => {
    if (titleTouched || code === null) return;
    setTitle(courses.find((c) => c.code === code)?.title ?? "");
  }, [code, courses, titleTouched]);

  const chooseCourse = (c: number | null) => {
    setCode(c);
    if (c !== null && !editing) { setSectionNo(nextFree(c)); setCap(typicalCap(c, modality === "Remote")); }
  };
  const chooseModality = (m: Modality) => {
    setModality(m);
    if (m === "Remote") { setSequence(""); setCap((x) => Math.min(x, REMOTE_CAP)); }
    else if (code !== null && cap === REMOTE_CAP) setCap(typicalCap(code, false));
  };

  const plannable = useMemo(() => courses.filter((c) => c.code !== 1125 && c.code !== 1126), [courses]);
  const sectionId = code ? `ECON ${code}-${String(sectionNo).padStart(2, "0")}` : "";
  const taken = code !== null && usedNumbers(code).has(sectionNo);
  const capMax = modality === "Remote" ? REMOTE_CAP : 300;
  const invalid = !code || taken || !Number.isInteger(sectionNo) || sectionNo < 1 || sectionNo > 99 || cap < 1 || cap > capMax;

  async function save() {
    if (invalid || code === null) return;
    setBusy(true); setError(null);
    const body = { term: settings.target_term, code, section_no: sectionNo, title: title.trim(), instructor: instructor || null,
      modality, sequence: modality === "Remote" ? null : sequence || null, cap, settings };
    try {
      const saved = editing ? await api.updateSection(editing.id, body) : await api.addSection(body);
      await useSchedule.getState().fetch(settings, { silent: true });
      success(editing ? "Section updated" : "Section added",
        `${saved.section_id} · ${saved.instructor ?? "Unstaffed"} · ${saved.modality === "Remote" ? "Remote (Async)" : saved.sequence ? `Block ${saved.sequence}` : "Unscheduled"}`,
        `section:${saved.section_id}`);
      onSaved?.(saved.section_id);
      onClose();
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }

  const classSeqs = Object.values(meta.sequences.class);
  return (
    <Modal open={open} onClose={() => !busy && onClose()} size="lg" title={editing ? `Edit Manual Section ${editing.section_id}` : "Add Section"}
      footer={<>
        <Button variant="ghost" onClick={onClose} disabled={busy}>Cancel</Button>
        <Button variant="primary" loading={busy} disabled={invalid} onClick={save}>{editing ? "Save Changes" : "Add Section"}</Button>
      </>}>
      <div className="space-y-4">
        <p className="text-[13px] text-muted">
          Hand-placed sections are tagged <span className="font-medium text-fg">Manual Edit</span> on the Term Schedule for {settings.target_term} and can be reverted at any time.
        </p>
        <Field label="Course">
          <CourseSelect courses={plannable} value={code} onChange={chooseCourse} placeholder="Search by code, title or topic" />
        </Field>
        <div className="grid gap-4 sm:grid-cols-[1fr_140px]">
          <Field label="Section Title"><input className={inputCls} value={title} placeholder="Course title"
            onChange={(e) => { setTitle(e.target.value); setTitleTouched(true); }} /></Field>
          <Field label="Section Number" hint={taken ? <span className="text-nu-text">{sectionId} already exists</span> : sectionId || undefined}>
            <input type="number" min={1} max={99} className={inputCls + " tabular-nums"} value={sectionNo}
              onChange={(e) => setSectionNo(Math.round(Number(e.target.value)))} />
          </Field>
        </div>
        <Field label="Instructor" hint="Faculty on the roster. Their workload and time conflicts update when you save.">
          <select className={inputCls} value={instructor} onChange={(e) => setInstructor(e.target.value)}>
            <option value="">Unstaffed</option>
            {data.instructors.map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Modality">
            <Segmented value={modality} onChange={chooseModality} options={[{ id: "In-Person", label: "In Person" }, { id: "Remote", label: "Remote" }]} />
          </Field>
          <Field label="Seat Capacity" hint={modality === "Remote" ? `Remote sections are capped at ${REMOTE_CAP}` : undefined}>
            <input type="number" min={1} max={capMax} className={inputCls + " tabular-nums"} value={cap}
              onChange={(e) => setCap(Math.round(Number(e.target.value)))} />
          </Field>
        </div>
        <Field label="Day / Time Block" hint={modality === "Remote" ? "Remote sections are asynchronous." : "Lecture sequences from Course_Sequences.pdf. Leave unscheduled to place it later."}>
          <select className={inputCls} value={modality === "Remote" ? "ASYNC" : sequence} disabled={modality === "Remote"} onChange={(e) => setSequence(e.target.value)}>
            {modality === "Remote" ? <option value="ASYNC">Asynchronous (Remote)</option> : <>
              <option value="">Unscheduled</option>
              {classSeqs.map((x) => <option key={x.code} value={x.code}>{x.code} — {x.label}</option>)}
            </>}
          </select>
        </Field>
        {error && <Alert tone="error">{error}</Alert>}
      </div>
    </Modal>
  );
}
