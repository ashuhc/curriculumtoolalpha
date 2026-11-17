// Typed REST client for the FastAPI backend.
import { useAuth } from "./store/auth";

/**
 * API base URL. Empty (the default) = same origin: the Vite dev/preview proxy, nginx, or
 * the single-container FastAPI build forward /api and /ws to the backend. Set VITE_API_URL
 * only when the API lives on a different origin.
 */
export const API_URL: string = ((import.meta.env.VITE_API_URL as string | undefined) ?? "").trim().replace(/\/+$/, "");
const API_LABEL = API_URL || "this site's /api";

export function wsUrl(token: string | null): string {
  const base = API_URL || window.location.origin;
  return base.replace(/^http/, "ws") + "/ws" + (token ? `?token=${encodeURIComponent(token)}` : "");
}

// ------------------------------------------------------------------ types ---
export type Role = "admin" | "faculty";
export interface User { id: number; email: string; name: string; role: Role; faculty_id: number | null; faculty_name: string | null; active: boolean }
export interface UserRow extends User { last_login: string | null; created_at: string }

export interface PlanSettings {
  target_term: string; growth_multiplier: number; history_window: number; apply_trend: boolean;
  large_lecture_cap: number; small_section_cap: number; virtual_cap: number; recitation_cap: number;
  min_elective_demand: number; history_fallback: boolean; force_fill_core: boolean; recitation_leader_load: number;
}

export interface Block { day: string; start: number; end: number }
export interface SequenceInfo { code: string; kind: "class" | "lab" | "recitation"; days: string; label: string; blocks: Block[] }
export interface Meta {
  terms: { upcoming: string[]; historical: string[]; default: string };
  sequences: { class: Record<string, SequenceInfo>; lab: Record<string, SequenceInfo>; recitation: Record<string, SequenceInfo>; special: string[] };
  faculty_types: Record<string, { min: number; standard: number; max: number } | null>;
  core: { econ_at_nu: number; principles: number[]; follow_ups: number[]; capstones: number[]; recitations: Record<string, number> };
  limits: { virtual_cap: number };
  special_instructors: string[];
  /** When true the deployment requires sign-in to view anything. */
  require_login: boolean;
}

export interface Course { code: number; title: string; description: string; active: boolean; label: string; level: number; category: string; prerequisites: string; times_offered: number }
export interface Faculty {
  id: number; name: string; email: string; active: boolean; faculty_type: string; type_source: string; annual_reduction: number;
  /** Courses per semester set by a scheduler; null = not set (form, then history). */
  fall_courseload: number | null; spring_courseload: number | null;
  /** Seeded overload approval, and the fields that differ from the inferred/seeded baseline. */
  default_overloading: boolean; default_overload_semester: string; customized: string[];
  overloading: boolean; overload_semester: string; ug_lectures_per_year: number; grad_sections_per_year: number; submissions: number;
}
export interface PreferenceIn {
  faculty_id: number; email: string; principles: number[]; ranks: number[]; fall_target: number; spring_target: number;
  overload: boolean; overload_semester: string; unique_circumstances: string;
}
export interface Preference extends PreferenceIn { id: number; faculty_name: string; submitted_at: string; submitted_by: string | null }

export interface DemandRow {
  course: string; title: string; category: string; level: number; modality: string; history_terms_used: number;
  hist_weighted_avg: number | null; annual_trend: number; projected_enrollment: number; planned_sections: number;
  section_caps: string; seats_offered: number; seat_fill: number; actual_enrollment: number | null;
  actual_sections: number | null; notes: string; code: number; virtual: boolean; core: boolean;
}
export interface PrereqRow { course: string; title: string; level: number; prerequisites: string; level_rule: string; pathway_offered_this_term: string; ok: boolean }
export interface DemandResponse {
  term: string;
  summary: { courses: number; lecture_sections: number; recitation_sections: number; projected_students: number; remote_sections: number; seats_offered: number };
  demand: DemandRow[]; prerequisites: PrereqRow[];
}

export interface MasterRow {
  section_id: string; course: string; section: string; title: string; category: string; level: number;
  component: "Lecture" | "Recitation"; modality: string; section_cap: number; projected_enrollment: number;
  instructor: string; faculty_type: string; match_basis: string; sequence: string; sequence_type: string;
  days: string; meeting_time: string; linked_lecture: string; prerequisites: string;
}
export interface ConflictRow { severity: "Critical" | "Warning" | "Info"; category: string; course_section: string; faculty: string; details: string; suggested_action: string }
export interface WorkloadRow {
  faculty: string; type: string; target_source: string; term_target: number; assigned_this_term: number; other_semester_planned: number;
  projected_annual: number; allowed_annual: string; annual_reduction: number; overload_approved_json: string; overload_requested_form: string; status: string;
}
export interface Lock { term: string; section_id: string; user_id: number; user_name: string; acquired_at: string; expires_at: string }
export interface Publication { id: number; term: string; version: number; published_at: string; published_by: string; note: string; sections: number; critical: number; warning: number }
export interface ScheduleResponse {
  term: string;
  summary: { sections: number; core_sections: number; core_staffed: number; electives_offered: number; preference_matches: number;
             critical: number; warning: number; info: number; submissions: number; overrides_applied: number; overrides_stale: string[] };
  master: MasterRow[]; conflicts: ConflictRow[]; workload: WorkloadRow[]; instructors: string[]; overridden: string[];
  locks: Lock[]; comment_counts: Record<string, number>; publication: Publication | null;
  /** Sections a scheduler added by hand for this term (also listed in `overridden`). */
  manual_sections: ManualSection[];
}
export interface ManualSection {
  id: number; term: string; section_id: string; code: number; section_no: number; title: string;
  instructor: string | null; modality: "In-Person" | "Remote"; sequence: string | null; cap: number; created_by: string;
}
export interface ManualSectionIn {
  term: string; code: number; section_no: number; title: string; instructor: string | null;
  modality: "In-Person" | "Remote"; sequence: string | null; cap: number; settings?: PlanSettings;
}
export interface BlockSuggestion {
  sequence: string; label: string; cost: number; core_overlaps: number; same_course_overlaps: number;
  level_overlaps: number; sections_in_block: number; reasons: string[];
}
export interface Volunteer { name: string; basis: string; score: number; assigned: number; term_target: number }
export interface Comment { id: number; term: string; section_id: string; parent_id: number | null; user_id: number | null; author_name: string; body: string; resolved: boolean; created_at: string }

// ----------------------------------------------------------------- client ---
export class ApiError extends Error {
  /** status 0 = network failure; `unavailable` = the server answered with something other than API data. */
  constructor(public status: number, message: string, public unavailable = false) { super(message); }
}

const isJson = (res: Response) => /\bjson\b/i.test(res.headers.get("Content-Type") ?? "");

/** Message for a response that isn't JSON (an HTML error page, a proxy page, the SPA fallback...). */
function nonJsonError(res: Response, path: string): ApiError {
  const msg = res.status >= 500
    ? `The scheduler API is temporarily unavailable (HTTP ${res.status}). It may be starting up or restarting; please try again in a moment.`
    : res.ok
      ? `Expected scheduler data from ${path} but received a web page instead. The app may be pointed at the wrong API address (${API_LABEL}).`
      : `The scheduler API returned an unexpected response (HTTP ${res.status}) for ${path}.`;
  return new ApiError(res.ok ? 502 : res.status, msg, true);
}

function errorMessage(body: unknown, status: number): string {
  const detail = (body as { detail?: unknown })?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail))
    return detail.map((d: { msg?: string; loc?: string[] }) =>
      `${(d.loc ?? []).slice(1).join(".")}: ${(d.msg ?? "").replace(/^Value error, /, "")}`).join("; ");
  return `Request failed (${status})`;
}

function authHeaders(): Record<string, string> {
  const token = useAuth.getState().token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request<T>(path: string, opts: { method?: string; body?: unknown; form?: FormData } = {}): Promise<T> {
  const headers = authHeaders();
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  let res: Response;
  try {
    res = await fetch(API_URL + path, {
      method: opts.method ?? "GET", headers,
      body: opts.form ?? (opts.body !== undefined ? JSON.stringify(opts.body) : undefined),
    });
  } catch {
    throw new ApiError(0, `Can't reach the scheduler API at ${API_LABEL}. Check your connection or that the backend is running, then retry.`, true);
  }
  if (res.status === 204) return undefined as T;
  const text = await res.text().catch(() => "");
  let body: unknown;
  if (text) {
    // Never hand HTML (404/502 pages, the SPA's index.html) to JSON.parse
    if (!isJson(res)) throw nonJsonError(res, path);
    try { body = JSON.parse(text); } catch {
      throw new ApiError(res.ok ? 502 : res.status, `The scheduler API sent a malformed response for ${path}. Please try again.`, true);
    }
  }
  if (!res.ok) {
    if (res.status === 401 && headers.Authorization && path !== "/api/auth/login") useAuth.getState().signOut(true);
    throw new ApiError(res.status, errorMessage(body, res.status));
  }
  return body as T;
}

/** Fetch a file endpoint and trigger a browser download. */
async function download(path: string, body?: unknown, fallbackName = "export.csv") {
  const headers = authHeaders();
  if (body !== undefined) headers["Content-Type"] = "application/json";
  let res: Response;
  try {
    res = await fetch(API_URL + path, {
      method: body !== undefined ? "POST" : "GET", headers, body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError(0, `Can't reach the scheduler API at ${API_LABEL}. Check your connection, then retry the export.`, true);
  }
  if (!res.ok) {
    if (!isJson(res)) throw nonJsonError(res, path);
    throw new ApiError(res.status, errorMessage(await res.json().catch(() => ({})), res.status));
  }
  // A 200 HTML page here means the request never reached the API; don't save it as the export
  if (/text\/html/i.test(res.headers.get("Content-Type") ?? "")) throw nonJsonError(res, path);
  const name = /filename="?([^"]+)"?/.exec(res.headers.get("Content-Disposition") ?? "")?.[1] ?? fallbackName;
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

const q = encodeURIComponent;

export const api = {
  health: () => request<{ status: string; database: string; enrollment_records: number; courses: number; faculty: number; submissions: number }>("/api/health"),
  meta: () => request<Meta>("/api/meta"),

  login: (email: string, password: string) => request<{ token: string; user: User }>("/api/auth/login", { method: "POST", body: { email, password } }),
  me: () => request<User>("/api/auth/me"),
  changePassword: (current_password: string, new_password: string) => request("/api/auth/password", { method: "POST", body: { current_password, new_password } }),
  users: () => request<UserRow[]>("/api/users"),
  createUser: (u: { email: string; name: string; role: Role; password: string; faculty_id: number | null }) => request<User>("/api/users", { method: "POST", body: u }),
  updateUser: (id: number, u: Record<string, unknown>) => request<User>(`/api/users/${id}`, { method: "PUT", body: u }),
  deleteUser: (id: number) => request(`/api/users/${id}`, { method: "DELETE" }),

  courses: (includeInactive = false) => request<Course[]>(`/api/courses?include_inactive=${includeInactive}`),
  createCourse: (c: { code: number; title: string; description: string }) => request<Course>("/api/courses", { method: "POST", body: c }),
  updateCourse: (code: number, c: Partial<Pick<Course, "title" | "description" | "active">>) => request<Course>(`/api/courses/${code}`, { method: "PUT", body: c }),
  deleteCourse: (code: number) => request(`/api/courses/${code}`, { method: "DELETE" }),

  faculty: (includeInactive = false) => request<Faculty[]>(`/api/faculty?include_inactive=${includeInactive}`),
  createFaculty: (f: { name: string; email: string }) => request<Faculty>("/api/faculty", { method: "POST", body: f }),
  updateFaculty: (id: number, f: Record<string, unknown>) => request<Faculty>(`/api/faculty/${id}`, { method: "PUT", body: f }),
  deleteFaculty: (id: number) => request(`/api/faculty/${id}`, { method: "DELETE" }),
  resetFaculty: (id: number) => request<Faculty>(`/api/faculty/${id}/reset`, { method: "POST" }),
  resetAllFaculty: () => request<{ reset: number; faculty: string[] }>("/api/faculty/reset", { method: "POST" }),

  submitPreferences: (p: PreferenceIn) => request<Preference>("/api/preferences", { method: "POST", body: p }),
  myPreferences: () => request<Preference[]>("/api/preferences/mine"),
  preferences: () => request<Preference[]>("/api/preferences"),
  deletePreference: (id: number) => request(`/api/preferences/${id}`, { method: "DELETE" }),
  clearPreferences: () => request("/api/preferences?confirm=true", { method: "DELETE" }),
  exportPreferences: () => download("/api/preferences/export", undefined, "teacher_preferences_export.csv"),

  demand: (settings: PlanSettings) => request<DemandResponse>("/api/plan/demand", { method: "POST", body: { settings } }),
  schedule: (settings: PlanSettings) => request<ScheduleResponse>("/api/plan/schedule", { method: "POST", body: { settings } }),
  /** Ranked conflict-free lecture blocks for one more section of `code`, plus likely volunteers. */
  suggestSection: (b: { settings: PlanSettings; code: number; instructor?: string | null; exclude_section_id?: string | null }) =>
    request<{ blocks: BlockSuggestion[]; volunteers: Volunteer[] }>("/api/plan/suggest-section", { method: "POST", body: b }),
  addSection: (s: ManualSectionIn) => request<ManualSection>("/api/plan/sections", { method: "POST", body: s }),
  updateSection: (id: number, s: ManualSectionIn) => request<ManualSection>(`/api/plan/sections/${id}`, { method: "PUT", body: s }),
  overrides: (term: string) => request<{ section_id: string; instructor: string | null; sequence: string | null }[]>(`/api/plan/overrides?term=${q(term)}`),
  setOverride: (o: { term: string; section_id: string; instructor?: string | null; sequence?: string | null }) => request("/api/plan/overrides", { method: "PUT", body: o }),
  /** Revert manual edits (one section, or the whole term). Bulk reverts skip sections another scheduler has locked. */
  resetOverrides: (term: string, sectionId?: string) =>
    request<{ reverted: string[]; skipped: { section_id: string; locked_by: string }[] }>(
      `/api/plan/overrides?term=${q(term)}${sectionId ? `&section_id=${q(sectionId)}` : ""}`, { method: "DELETE" }),
  exportPlan: (kind: "demand" | "master" | "catalog" | "conflicts" | "workload", settings: PlanSettings) =>
    download(`/api/export/${kind}`, { settings }, `${kind}.csv`),

  lock: (term: string, section_id: string) => request<Lock>("/api/locks", { method: "POST", body: { term, section_id } }),
  unlock: (term: string, section_id: string) => request(`/api/locks?term=${q(term)}&section_id=${q(section_id)}`, { method: "DELETE" }),
  comments: (term: string, section_id?: string) => request<Comment[]>(`/api/comments?term=${q(term)}${section_id ? `&section_id=${q(section_id)}` : ""}`),
  addComment: (c: { term: string; section_id: string; body: string; parent_id?: number | null }) => request<Comment>("/api/comments", { method: "POST", body: c }),
  updateComment: (id: number, c: { resolved?: boolean; body?: string }) => request<Comment>(`/api/comments/${id}`, { method: "PATCH", body: c }),
  deleteComment: (id: number) => request(`/api/comments/${id}`, { method: "DELETE" }),

  publications: (term?: string) => request<Publication[]>(`/api/publications${term ? `?term=${q(term)}` : ""}`),
  publish: (settings: PlanSettings, note: string, allow_critical: boolean) => request<Publication>("/api/publications", { method: "POST", body: { settings, note, allow_critical } }),
  exportPublication: (id: number) => download(`/api/publications/${id}/export`, undefined, "catalog.csv"),

  enrollmentTerms: () => request<{ term: string; sections: number; students: number }[]>("/api/enrollment/terms"),
  uploadEnrollment: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<{ added: number }>("/api/enrollment/upload", { method: "POST", form });
  },
};
