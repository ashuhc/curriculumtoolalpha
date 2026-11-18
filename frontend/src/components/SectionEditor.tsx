// Add Section / Edit Manual Section: lets schedulers hand-place a section (an elective the solver
// didn't offer, overflow demand, a missing core course) with its own instructor, block and cap.
import { Sparkles, Trash2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { api, type BlockSuggestion, type Course, type ManualSection, type Meta, type ScheduleResponse, type Volunteer } from "../api";
import { useDemand } from "../store/demand";
import { useHistory } from "../store/history";
import { usePlan } from "../store/plan";
import { useSchedule } from "../store/schedule";
import { useUI } from "../store/ui";
import { CourseSelect } from "./CourseSelect";
import { Alert, Button, Field, Modal, Segmented, inputCls } from "./ui";

export interface SectionPrefill { code?: number; remote?: boolean }

const REMOTE_CAP = 25;
type Modality = "In-Person" | "Remote";

export function SectionEditor({ open, onClose, data, meta, prefill, editing, onSaved, onDelete }: {
  open: boolean; onClose: () => void; data: ScheduleResponse; meta: Meta;
  prefill?: SectionPrefill; editing?: ManualSection | null; onSaved?: (sectionId: string) => void;
  /** Offered while editing: hands the section to the page's Delete Section confirmation. */
  onDelete?: (sectionId: string) => void;
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
  // Auto-Assign Time Block: suggestions for the current course/instructor, and whether the
  // block is still auto-managed (picking one by hand turns that off)
  const [volunteers, setVolunteers] = useState<Volunteer[]>([]);
  const [suggestions, setSuggestions] = useState<BlockSuggestion[] | null>(null);
  const [autoBlock, setAutoBlockState] = useState(false);
  const autoRef = useRef(false);            // read by the fetch effect in the same render as a reset
  const setAutoBlock = (v: boolean) => { autoRef.current = v; setAutoBlockState(v); };
  const [suggesting, setSuggesting] = useState(false);
  const suggestSeq = useRef(0);

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
    setSuggestions(null); setVolunteers([]);
    if (editing) {
      setAutoBlock(false);
      setCode(editing.code); setTitle(editing.title); setTitleTouched(true); setSectionNo(editing.section_no);
      setInstructor(editing.instructor ?? ""); setModality(editing.modality); setSequence(editing.sequence ?? ""); setCap(editing.cap);
    } else {
      const c = prefill?.code ?? null;
      const remote = !!prefill?.remote;
      setCode(c); setTitleTouched(false); setTitle(""); setInstructor(""); setSequence(""); setAutoBlock(false);
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

  // Fetch ranked blocks (and likely volunteers) for the current course/instructor; optionally apply the best one
  async function suggest(apply: boolean) {
    if (code === null || modality === "Remote") return;
    const id = ++suggestSeq.current;
    setSuggesting(true);
    try {
      const r = await api.suggestSection({ settings, code, instructor: instructor || null, exclude_section_id: editing?.section_id ?? null });
      if (id !== suggestSeq.current) return;
      setVolunteers(r.volunteers);
      setSuggestions(r.blocks);
      if (apply && r.blocks[0]) setSequence(r.blocks[0].sequence);
      if (apply && !r.blocks.length) setError(`No conflict-free lecture block is available${instructor ? ` for ${instructor}` : ""}.`);
    } catch (e) { if (id === suggestSeq.current) setError((e as Error).message); } finally { if (id === suggestSeq.current) setSuggesting(false); }
  }
  // Volunteers load with the course; after Auto-Assign, the block follows course/instructor changes
  useEffect(() => {
    if (!open || code === null || modality === "Remote") return;
    suggest(autoRef.current);
  }, [open, code, instructor, modality]); // eslint-disable-line react-hooks/exhaustive-deps

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
      // Recorded for Undo / Redo; a renumbered section touches both its old and new ID
      const ids = editing ? [editing.section_id, sectionId] : [sectionId];
      const saved = await useHistory.getState().record(editing ? "Edit Manual Section" : "Add Section", settings.target_term, ids,
        () => (editing ? api.updateSection(editing.id, body) : api.addSection(body)), editing && editing.section_id !== sectionId ? `${editing.section_id} → ${sectionId}` : sectionId);
      await useSchedule.getState().fetch(settings, { silent: true });
      useDemand.getState().refresh();
      success(editing ? "Section updated" : "Section added",
        `${saved.section_id} · ${saved.instructor ?? "Unstaffed"} · ${saved.modality === "Remote" ? "Remote (Async)" : saved.sequence ? `Block ${saved.sequence}` : "Unscheduled"}`,
        `section:${saved.section_id}`);
      onSaved?.(saved.section_id);
      onClose();
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }

  const classSeqs = Object.values(meta.sequences.class);
  const volunteerNames = new Set(volunteers.map((v) => v.name));
  const current = suggestions?.find((b) => b.sequence === sequence);
  return (
    <Modal open={open} onClose={() => !busy && onClose()} size="lg" title={editing ? `Edit Manual Section ${editing.section_id}` : "Add Section"}
      footer={<>
        {editing && onDelete && (
          <Button variant="danger" className="mr-auto" disabled={busy} icon={<Trash2 className="h-3.5 w-3.5" />}
            onClick={() => onDelete(editing.section_id)} title="Remove This Section From the Term Schedule">Remove Section</Button>
        )}
        <Button variant="ghost" onClick={onClose} disabled={busy}>Cancel</Button>
        <Button variant="primary" loading={busy} disabled={invalid || suggesting} onClick={save}>{editing ? "Save Changes" : "Add Section"}</Button>
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
        <Field label="Instructor"
          hint={code !== null && !volunteers.length && !suggesting ? "No one has ranked or taught this course yet; choose anyone on the roster." : "Faculty on the roster. Their workload and time conflicts update when you save."}>
          <select className={inputCls} value={instructor} onChange={(e) => setInstructor(e.target.value)}>
            <option value="">Unstaffed</option>
            {volunteers.length > 0 && (
              <optgroup label="Likely Volunteers">
                {volunteers.map((v) => <option key={v.name} value={v.name}>{v.name} · {v.basis} · {v.assigned}/{v.term_target} Assigned</option>)}
              </optgroup>
            )}
            <optgroup label="All Faculty">
              {data.instructors.filter((n) => !volunteerNames.has(n)).map((n) => <option key={n} value={n}>{n}</option>)}
            </optgroup>
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
        <div>
          <div className="mb-1.5 flex items-center justify-between gap-2">
            <span className="text-xs font-medium text-fg">Day / Time Block</span>
            {modality !== "Remote" && (
              <Button size="sm" variant="ghost" icon={<Sparkles className="h-3.5 w-3.5" />} loading={suggesting} disabled={code === null}
                onClick={() => { setAutoBlock(true); setError(null); suggest(true); }}>Auto-Assign Time Block</Button>
            )}
          </div>
          <select aria-label="Day / Time Block" className={inputCls} value={modality === "Remote" ? "ASYNC" : sequence} disabled={modality === "Remote"}
            onChange={(e) => { setSequence(e.target.value); setAutoBlock(false); }}>
            {modality === "Remote" ? <option value="ASYNC">Asynchronous (Remote)</option> : <>
              <option value="">Unscheduled</option>
              {classSeqs.map((x) => <option key={x.code} value={x.code}>{x.code} — {x.label}</option>)}
            </>}
          </select>
          <p className="mt-1 text-xs text-faint">{modality === "Remote" ? "Remote sections are asynchronous." : "Lecture sequences from Course_Sequences.pdf. Leave unscheduled to place it later."}</p>
          {modality !== "Remote" && autoBlock && current && (
            <div className="mt-2 rounded-md border border-emerald-600/25 bg-emerald-500/5 px-3 py-2 text-xs">
              <div className="font-medium text-emerald-700 dark:text-emerald-400">Auto-Assigned: Block {current.sequence} · {current.label}</div>
              <ul className="mt-1 list-disc space-y-0.5 pl-4 text-muted">{current.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
              {suggestions && suggestions.length > 1 && (
                <div className="mt-2 flex flex-wrap items-center gap-1.5 text-muted">
                  <span>Alternatives:</span>
                  {suggestions.filter((b) => b.sequence !== current.sequence).map((b) => (
                    <button key={b.sequence} type="button" onClick={() => setSequence(b.sequence)} title={b.reasons.join(" · ")}
                      className="rounded border border-line bg-surface px-1.5 py-0.5 text-[11px] font-medium text-fg hover:bg-hover">
                      {b.sequence} · {b.label}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
        {error && <Alert tone="error">{error}</Alert>}
      </div>
    </Modal>
  );
}
