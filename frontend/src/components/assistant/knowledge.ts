// Scheduler Assistant knowledge + natural-language understanding.
//
// Pure module (type-only imports) so it can be unit-tested outside the browser.
// Answering order:
//   1. Entities in the question: section IDs, % values, plain numbers, course codes,
//      faculty names, modality ("remote" / "in person").
//   2. Topic: every table column, metric, conflict category and workload status,
//      matched by synonyms. Combined with an entity, the answer quotes the live row.
//   3. Any scheduler-related wording without a specific match → a summary of the
//      current page with live numbers.
//   4. Only clearly unrelated questions get the generic help menu.

import type { Course, DemandResponse, DemandRow, PlanSettings, ScheduleResponse, WorkloadRow } from "../../api";

export interface Answer { text: string; links?: { label: string; to: string }[]; chips?: string[] }
export interface Ctx {
  settings: PlanSettings; schedule: ScheduleResponse | null; demand: DemandResponse | null;
  courses: Course[] | null; role: string | null; page: string;
}

export const STARTER_PROMPTS = [
  "How do I use planning settings?",
  "What does seat fill mean?",
  "How are recitations calculated?",
  "What does Trend per Year mean?",
  "How do I resolve conflicts?",
  "How are time slots assigned?",
];

// ------------------------------------------------------------------ helpers ---
const SMALL = new Set(["a", "an", "and", "as", "at", "by", "for", "in", "of", "on", "or", "per", "the", "to", "vs"]);
/** Title Case for labels quoted in answers (matches the UI's labels). */
const tc = (s: string) => s.split(" ").map((w, i) => (i > 0 && SMALL.has(w.toLowerCase()) ? w.toLowerCase()
  : w.replace(/^(\(?)(\p{Ll})/u, (_, p: string, c: string) => p + c.toUpperCase()).replace(/-(\p{Ll})/gu, (_, c: string) => "-" + c.toUpperCase()))).join(" ");
const pct1 = (t: number) => `${t > 0 ? "+" : ""}${(t * 100).toFixed(1)}%`;
const label = (r: DemandRow) => `${r.course} (${r.virtual ? "Remote" : "In Person"})`;
const seasonOf = (term: string) => term.split(" ")[0] || "same-season";
const plural = (n: number, w: string) => `${n} ${w}${n === 1 ? "" : "s"}`;
const LINK_DEMAND = { label: "Open Enrollment Projections", to: "/demand" };
const LINK_SCHEDULE = { label: "Open Term Schedule", to: "/schedule" };
const LINK_CONFLICTS = { label: "Open Conflicts & Audits", to: "/conflicts" };

function norm(s: string) {
  return s.toLowerCase().replace(/[’']/g, "'").replace(/[^a-z0-9%+.\-–−/×'\s]/g, " ").replace(/\s+/g, " ").trim();
}
function hasWord(q: string, alias: string) {
  const esc = alias.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`(^|[^a-z0-9])${esc}($|[^a-z0-9])`).test(q);
}

/** Years a projection is compounded over, recovered from the row's own numbers. */
function impliedYears(r: DemandRow, growth: number): number | null {
  if (!r.hist_weighted_avg || !r.annual_trend || r.projected_enrollment <= 0) return null;
  const y = Math.log(r.projected_enrollment / (r.hist_weighted_avg * growth)) / Math.log(1 + r.annual_trend);
  return Number.isFinite(y) && y > 0 && y < 10 ? y : null;
}

// ------------------------------------------------------- row explanations ---
type Metric = "trend" | "histavg" | "projected" | "sections" | "caps" | "seatfill" | "actual";

function explainRow(m: Metric, r: DemandRow, ctx: Ctx): string {
  const s = ctx.settings;
  const season = seasonOf(ctx.demand?.term ?? s.target_term);
  const n = r.history_terms_used;
  const caps = r.section_caps;
  const fill = Math.round(r.seat_fill * 100);
  switch (m) {
    case "trend": {
      if (!r.annual_trend) {
        const why = !s.apply_trend ? "the Apply Historical Trend setting is off"
          : n < 3 ? `it only has ${plural(n, `${season} term`)} of history, and a trend needs at least three`
          : "its enrollment has been flat";
        return `**${label(r)}** has no trend applied (shown as —) because ${why}. Its projection is just Hist. Avg ${r.hist_weighted_avg ?? "—"} × the ${s.growth_multiplier.toFixed(2)}× growth multiplier.`;
      }
      const up = r.annual_trend > 0;
      const y = impliedYears(r, s.growth_multiplier);
      const capped = Math.abs(r.annual_trend) >= 0.0995;
      return `The **${pct1(r.annual_trend)}** is the annual enrollment trend for **${label(r)}**. Over the last ${plural(n, `${season} term`)} in your history window, its enrollment has been ${up ? "growing" : "shrinking"} by about ${Math.abs(r.annual_trend * 100).toFixed(1)}% per year (a straight-line fit through those terms).` +
        (capped ? ` That's the **±10.0% cap**: the raw trend was steeper, so it's limited to keep one unusual term from dominating.` : "") +
        (y && r.hist_weighted_avg ? `\n\nIt's compounded into the projection: Hist. Avg **${r.hist_weighted_avg}** × (1 ${up ? "+" : "−"} ${Math.abs(r.annual_trend * 100).toFixed(1)}%)^${y.toFixed(1)} years × ${s.growth_multiplier.toFixed(2)}× growth ≈ **${r.projected_enrollment}** projected.` : "");
    }
    case "histavg":
      if (r.hist_weighted_avg === null) return `**${label(r)}** has no Hist. Avg: recitations aren't forecast from their own history. Their count comes from the students in the lecture's large sections (⌈large-lecture students ÷ ${s.recitation_cap}⌉).`;
      return `**${label(r)}** has a Hist. Avg of **${r.hist_weighted_avg}**: the weighted average of its enrollment in the last ${plural(n, `${season} term`)} it was offered (your History Window is ${s.history_window}). The most recent term counts most (weights 1, 2, 3 …).` +
        (r.notes ? `\n\nNote: ${r.notes}.` : "");
    case "projected": {
      if (r.category === "Recitation") return `**${r.course}** covers **${r.projected_enrollment}** students: those seated in its lecture's large (${s.large_lecture_cap}-seat) sections, which sets how many recitations are needed. Smaller sections of the same course have no recitation.`;
      const y = impliedYears(r, s.growth_multiplier);
      return `**${label(r)}** is projected at **${r.projected_enrollment}** students` +
        (r.hist_weighted_avg !== null ? ` = Hist. Avg **${r.hist_weighted_avg}**` +
          (r.annual_trend ? ` × (1 ${r.annual_trend > 0 ? "+" : "−"} ${Math.abs(r.annual_trend * 100).toFixed(1)}%)${y ? `^${y.toFixed(1)} years` : " compounded"}` : "") +
          ` × ${s.growth_multiplier.toFixed(2)}× growth multiplier.` : ".") +
        (r.actual_enrollment !== null ? ` For comparison, actual enrollment that term was **${r.actual_enrollment}**.` : "");
    }
    case "sections":
    case "caps": {
      if (r.planned_sections === 0) return `**${label(r)}** has **0 sections** planned: ${r.notes || `its projected ${r.projected_enrollment} students is below the ${s.min_elective_demand}-student minimum for electives`}.`;
      let rule: string;
      if (r.category === "Recitation") rule = `Recitations are ⌈${r.projected_enrollment} large-lecture students ÷ ${s.recitation_cap} per recitation⌉ = ${r.planned_sections}, each a weekly 65-minute session linked to one large lecture section.`;
      else if (r.virtual) rule = `Remote sections are capped at ${s.virtual_cap} students, so ⌈${r.projected_enrollment} ÷ ${s.virtual_cap}⌉ = ${r.planned_sections}.`;
      else if (r.code === 1115 || r.code === 1116) rule = `Principles run as ${s.large_lecture_cap}-seat large lectures while at least ${Math.round(0.75 * s.large_lecture_cap)} students remain, then ${s.small_section_cap}-seat small sections for the rest. ${r.projected_enrollment} students → ${caps}.`;
      else rule = `It uses the course's typical historical cap, and a new section opens only when demand is more than 10% over a full section.`;
      return `**${label(r)}** has **${plural(r.planned_sections, "section")}** (${caps}; ${r.seats_offered} seats) for ${r.projected_enrollment} projected students. ${rule}`;
    }
    case "seatfill": {
      const status = fill > 100 ? `**Over capacity**: projected students exceed the seats planned, so add a section or raise the cap.`
        : fill >= 95 ? `**Near capacity** (95%+): little room for late registrations or a forecast miss. Consider an extra section or a larger cap.`
        : fill < 70 ? `Plenty of spare seats; one section might not be needed.` : `A healthy margin of spare seats.`;
      const why = r.virtual ? `Remote sections hold at most ${s.virtual_cap}.`
        : (r.code === 1115 || r.code === 1116) ? `Principles lectures are ${s.large_lecture_cap} seats; another large lecture only opens once ${Math.round(0.75 * s.large_lecture_cap)}+ students remain, so fill runs high.`
        : r.category === "Recitation" ? `Recitations are sized as ⌈students ÷ ${s.recitation_cap}⌉, so only the last one is partly empty.`
        : `Sections use the course's usual cap, and a new one opens only past 10% over a full section, so fill can run near 100%.`;
      return `**${label(r)}** is at **${fill}%** seat fill: ${r.projected_enrollment} projected ÷ ${r.seats_offered} seats (${caps}). ${status} ${why}`;
    }
    case "actual":
      if (r.actual_enrollment === null) return `**${label(r)}** has no actual enrollment on file for ${ctx.demand?.term ?? s.target_term}. Actuals appear when you pick a past term (back-test).`;
      return `For **${label(r)}**, the forecast was **${r.projected_enrollment}** and actual enrollment was **${r.actual_enrollment}** (${r.actual_sections ?? "?"} sections), a ${Math.round(Math.abs(r.projected_enrollment - r.actual_enrollment) / Math.max(1, r.actual_enrollment) * 100)}% difference. The forecast for a past term uses only earlier terms, so this measures accuracy.`;
  }
}

// ------------------------------------------------------- glossary / topics ---
interface Topic { id: string; aliases: string[]; metric?: Metric; answer: (ctx: Ctx) => Answer }

const CONFLICT_EXPLAIN: Record<string, string> = {
  "unstaffed section": "No instructor could be matched. For a mandatory core section that's Critical; electives and recitations are Warnings.",
  "missing core course": "A mandatory core course has no sections planned at all.",
  "unscheduled section": "An in-person section has no conflict-free time block.",
  "instructor time overlap": "One instructor is assigned two sections whose time blocks overlap.",
  "recitation overlaps lecture": "A recitation meets at the same time as the lecture it's linked to, so its students can't attend both.",
  "remote cap exceeded": "A remote section's cap is over the 25-student limit.",
  "over capacity": "Projected enrollment is higher than the section's cap.",
  "core schedule clash": "Every section of two same-stage core courses overlaps, so a student can't take both in one term.",
  "low time diversity": "All sections of a core course meet in the same time block, which limits student choice.",
  "over-allocation": "A faculty member's projected annual load is above their contract ceiling (plus any approved overload).",
  "under-allocation": "A faculty member's projected annual load is below their contract minimum.",
  "overload compensation": "The load uses an approved overload, so extra compensation should be processed.",
  "overload record mismatch": "The scheduler-approved overload and the faculty member's form disagree.",
  "below requested load": "The faculty member asked for more sections than they were assigned this term.",
  "unique circumstances": "The faculty member noted something on their form (sabbatical, buyout, joint appointment) that needs a manual look.",
  "elective not offered": "There's demand for the elective, but no willing faculty member had capacity, so it isn't running. A scheduler can place it by hand with **Add Section** (Conflicts & Audits or Term Schedule), which clears this item.",
  "demand over capacity": "Projected students exceed the planned seats, but another section would be under half full, so the planner didn't open one (the half-full rule). It's a Warning for core courses and informational for electives. Use **Add Section** to place one by hand, which clears the item, or raise a section cap.",
  "prerequisite issue": "A course breaks a level rule, or one of its prerequisites isn't offered that term.",
  "assignment outside preferences": "A core section was force-assigned to someone who didn't request it.",
  "unknown instructor": "The instructor isn't on the active faculty roster.",
  "preference data": "Something in a preference submission needs checking.",
};

const STATUS_EXPLAIN: Record<string, string> = {
  "within contract": "Annual load is inside the allowed range for the faculty group.",
  "under contract": "Annual load is below the group's required minimum.",
  "over contract": "Annual load exceeds the ceiling (contract max − reduction + approved overloads).",
  "overload in use": "Load is above the base contract but covered by an approved overload, so it's eligible for extra compensation.",
  "below standard": "A tenured faculty member below the standard 3 per year. Allowed, but flagged for awareness.",
  "recitation leader": "Recitation leaders have no course contract, so no load check applies.",
};

function exampleRow(ctx: Ctx, m: Metric): DemandRow | null {
  const rows = (ctx.demand?.demand ?? []).filter((r) => r.planned_sections > 0 && r.category !== "Recitation");
  if (!rows.length) return null;
  if (m === "trend") return [...rows].filter((r) => r.annual_trend).sort((a, b) => Math.abs(b.annual_trend) - Math.abs(a.annual_trend))[0] ?? null;
  if (m === "seatfill") return [...rows].sort((a, b) => b.seat_fill - a.seat_fill)[0];
  return rows.find((r) => r.code === 1115 && !r.virtual) ?? rows[0];
}

function withExample(base: string, ctx: Ctx, m: Metric): string {
  const r = exampleRow(ctx, m);
  return r ? `${base}\n\nExample from your current forecast: ${explainRow(m, r, ctx)}` : base;
}

const TOPICS: Topic[] = [
  {
    id: "trend", metric: "trend",
    aliases: ["trend per year", "trend / yr", "trend/yr", "annual trend", "trend", "trends", "growth rate", "year over year", "year-over-year", "yoy", "per year change", "percent change", "percentage change", "rate of change", "increase per year", "decline per year"],
    answer: (ctx) => ({
      text: withExample(`**Trend per Year** is each course's annual enrollment growth rate. It comes from a straight-line fit through its enrollment in the last ${ctx.settings.history_window} ${seasonOf(ctx.settings.target_term)} terms (your History Window), capped at **±10.0% per year** so one unusual term can't swing the forecast. It's compounded into the projection: **Projected = Hist. Avg × (1 + trend)^years ahead × growth multiplier**. A dash means no trend was applied (fewer than three years of history, or the trend setting is off).`, ctx, "trend"),
      links: [LINK_DEMAND], chips: ["What does Hist. Avg mean?", "How is Projected calculated?", "Why is the trend capped at 10%?"],
    }),
  },
  {
    id: "histavg", metric: "histavg",
    aliases: ["hist. avg", "hist avg", "hist average", "historical average", "history average", "historic average", "weighted average", "average enrollment", "past enrollment", "history window"],
    answer: (ctx) => ({
      text: withExample(`**Hist. Avg** is the course's average historical enrollment across your History Window: the most recent **${ctx.settings.history_window}** ${seasonOf(ctx.settings.target_term)} terms it was offered (Fall is compared with Fall, Spring with Spring). It's recency-weighted (1, 2, 3 …), so the latest term counts most. Missing counts in the source data are estimated as section cap × the course's usual fill rate. Change the window under Planning Settings → History Window.`, ctx, "histavg"),
      links: [LINK_DEMAND], chips: ["What does Trend per Year mean?", "How is Projected calculated?"],
    }),
  },
  {
    id: "projected", metric: "projected",
    aliases: ["projected enrollment", "projected students", "projected", "projection", "projections", "forecast", "forecasted", "estimate", "estimated enrollment", "how many students", "predicted"],
    answer: (ctx) => ({
      text: withExample(`**Projected** is the forecast enrollment for the target term:\n**Projected = Hist. Avg × (1 + Trend per Year)^years ahead × Enrollment Growth Multiplier** (currently ${ctx.settings.growth_multiplier.toFixed(2)}×).\n\nYears ahead is measured from the middle of the history window to the target term. Courses with no ${seasonOf(ctx.settings.target_term)} history use their all-term average, and brand-new electives default to 40.`, ctx, "projected"),
      links: [LINK_DEMAND], chips: ["What does Trend per Year mean?", "How are sections sized?", "What does seat fill mean?"],
    }),
  },
  {
    id: "sections", metric: "sections",
    aliases: ["section caps", "section cap", "sections", "section count", "number of sections", "how many sections", "planned sections", "lecture sections", "class size", "class sizes", "cap", "caps", "seats per section", "large lecture", "small section", "section size", "sized", "sizing", "proj. / cap", "proj / cap"],
    answer: (ctx) => {
      const s = ctx.settings;
      return {
        text: withExample(`**Sections** and **Section Caps** come from projected enrollment:\n• **Principles (1115/1116), in person:** ${s.large_lecture_cap}-seat large lectures while at least ${Math.round(0.75 * s.large_lecture_cap)} students remain, then ${s.small_section_cap}-seat small sections.\n• **Remote:** at most **${s.virtual_cap}** per section.\n• **Recitations:** only for the large lectures: **${s.recitation_cap}** per section, ⌈large-lecture students ÷ ${s.recitation_cap}⌉. Small sections have none.\n• **Everything else:** the course's typical historical cap (usually 40–45; capstones about 20). A section may run up to 10% over cap; beyond that, an **additional section opens only if it would be at least half full** (e.g. ≥23 students for a 45-seat section). Smaller overflows are reported as **Demand Over Capacity** on Conflicts & Audits instead of creating a sparse section.\n• Electives under ${s.min_elective_demand} students get 0 sections.\n\n**Proj. / Cap** on the Term Schedule shows each section's share of students vs. its cap.`, ctx, "sections"),
        links: [LINK_DEMAND], chips: ["What does seat fill mean?", "How are recitations calculated?"],
      };
    },
  },
  {
    id: "seatfill", metric: "seatfill",
    aliases: ["seat fill", "seats fill", "fill rate", "fill", "filled", "how full", "utilization", "utilisation", "capacity", "seats offered", "occupancy", "full"],
    answer: (ctx) => {
      const sm = ctx.demand?.summary;
      return {
        text: withExample(`**Seat Fill = Projected ÷ total planned seats** (the sum of the course's Section Caps). **95%+** means sections will be nearly full; **over 100%** means projected students exceed the seats planned and the course needs another section or a bigger cap.` +
          (sm ? ` Across ${ctx.demand!.term}, ${sm.projected_students.toLocaleString()} projected students fill ${sm.seats_offered.toLocaleString()} seats (**${Math.round((100 * sm.projected_students) / Math.max(1, sm.seats_offered))}%**).` : ""), ctx, "seatfill"),
        links: [LINK_DEMAND], chips: ["How are sections sized?", "What does Projected mean?"],
      };
    },
  },
  {
    id: "actual", metric: "actual",
    aliases: ["actual", "actual enrollment", "back-test", "backtest", "back test", "past term", "accuracy", "how accurate"],
    answer: (ctx) => ({
      text: `**Actual** appears when you pick a past term ("back-test") as the target semester. The forecast is built only from earlier terms, so comparing Projected with Actual shows how accurate the method is. For example, Fall 2026 projected ECON 1115 at 490 vs. 476 actual, and ECON 2316 at 240 vs. 241.` +
        (ctx.demand?.demand.some((r) => r.actual_enrollment !== null) ? `\n\nYou're viewing a back-test term now, so the Actual column is filled in.` : ""),
      links: [LINK_DEMAND],
    }),
  },
  {
    id: "growth",
    aliases: ["growth multiplier", "enrollment growth", "growth slider", "multiplier", "growth factor", "scale demand", "1.05×", "1.05x"],
    answer: (ctx) => ({
      text: `The **Enrollment Growth Multiplier** (0.85×–1.50×, now **${ctx.settings.growth_multiplier.toFixed(2)}×**) scales every course's projected students up or down after the trend is applied. It doesn't change section caps; more students simply means more sections. Use it for department-wide scenarios, e.g. 1.10× for a 10% larger incoming class.`,
      links: [LINK_DEMAND], chips: ["How is Projected calculated?", "How do I use planning settings?"],
    }),
  },
  {
    id: "settings",
    aliases: ["planning settings", "settings", "target semester", "target term", "persist", "saved settings", "configure", "defaults"],
    answer: (ctx) => ({
      text: `**Planning Settings** drive every forecast and schedule. They're saved in your browser and shared across Enrollment Projections, Term Schedule, and Conflicts & Audits.\n• **Target Semester** (top bar): upcoming terms are forecasts; past terms are back-tests with actuals.\n• **Enrollment Growth Multiplier** (0.85×–1.50×): scales projected students.\n• **History Window:** how many prior ${seasonOf(ctx.settings.target_term)} terms feed Hist. Avg.\n• **Apply Historical Trend:** year-over-year trend, capped ±10%/yr.\n• **Caps:** large lecture, small section, remote (max 25), recitation.\n\nNow: **${ctx.settings.target_term || "—"}**, **${ctx.settings.growth_multiplier.toFixed(2)}×** growth, ${ctx.settings.history_window}-term window.`,
      links: [LINK_DEMAND], chips: ["What does Trend per Year mean?", "What does Hist. Avg mean?"],
    }),
  },
  {
    id: "remote",
    aliases: ["remote", "online", "virtual", "async", "asynchronous", "remote cap"],
    answer: (ctx) => ({
      text: `**Remote sections are capped at ${ctx.settings.virtual_cap} students** (hard limit 25), and the conflict report flags any above 25. Remote demand is forecast separately from in-person demand. Remote sections are asynchronous, so they get no time block and can't cause time conflicts, and online Principles students don't count toward recitations.`,
      chips: ["How are sections sized?"],
    }),
  },
  {
    id: "recitations",
    aliases: ["recitation", "recitations", "1125", "1126", "discussion section", "lab section"],
    answer: (ctx) => {
      const rec = ctx.demand?.demand.filter((r) => r.category === "Recitation") ?? [];
      const cap = ctx.settings.recitation_cap;
      const live = rec.map((r) => `**${r.course}:** ⌈${r.projected_enrollment} ÷ ${cap}⌉ = **${r.planned_sections}**`).join("\n");
      return {
        text: `Recitations are weekly **65-minute** sessions: **ECON 1125** for Macro (1115) and **ECON 1126** for Micro (1116).\n**Only large lecture sections (${ctx.settings.large_lecture_cap} seats) get recitations. Count = ⌈students in large lectures ÷ recitation cap (${cap})⌉.** Smaller (e.g. ${ctx.settings.small_section_cap}-seat) and remote sections don't need one.` + (live ? `\n${live}` : "") +
          `\n\nEach recitation is linked to one large lecture section (spread in proportion to lecture size) and placed in a 65-minute lab-window slot (sequences L–W) that **never overlaps its linked lecture**. Recitation leaders staff them, and they don't count toward faculty loads.`,
        links: [LINK_DEMAND], chips: ["How are time slots assigned?", "What does seat fill mean?"],
      };
    },
  },
  {
    id: "modality",
    aliases: ["modality", "in person", "in-person", "on campus"],
    answer: () => ({ text: `**Modality** shows whether a row is **In Person** (scheduled into a time block) or **Remote** (asynchronous, capped at 25, no time block). In-person and remote demand are forecast separately from their own history.` }),
  },
  {
    id: "notes",
    aliases: ["notes column", "notes", "note"],
    answer: () => ({ text: `**Notes** explain anything unusual about a forecast row: no history for this season (so the all-term average was used), no history at all (default 40 for a requested elective), below the elective minimum (0 sections), or the recitation formula.` }),
  },
  {
    id: "prereqs",
    aliases: ["prerequisite", "prerequisites", "prereq", "prereqs", "level rule", "pathway offered", "pathway", "1000-level", "3000-level", "4000-level"],
    answer: () => ({
      text: `**Prerequisite rules by level:**\n• **1000-level:** none\n• **3000-level:** require the Principles courses (1115, 1116)\n• **4000-level:** multiple prerequisites including theory (2315/2316); capstones also need Econometrics (2560)\n\n**Level Rule** checks each offered course against these. **Pathway Offered** confirms each prerequisite also runs that term so students have a way in.`,
      links: [LINK_DEMAND],
    }),
  },
  {
    id: "conflicts",
    aliases: ["conflict", "conflicts", "audit", "audits", "conflicts & audits", "resolve", "fix", "critical", "warning", "warnings", "severity", "flagged", "flag", "issue", "issues", "problem", "problems", "suggested action"],
    answer: (ctx) => ({
      text: `To resolve conflicts:\n1. Open **Conflicts & Audits** and start with **Critical**: unstaffed core sections, instructor double-bookings, recitation/lecture overlaps, remote caps over 25.\n2. Click the row to jump to that section on the **Term Schedule**, then **Edit Section** (this locks it for you).\n3. Change the instructor or time block. Conflicts recompute instantly for everyone.\n4. Discuss trade-offs in the section's comments, then **Done Editing**.\n5. **Warnings** (over/under-allocation, overload mismatches) usually mean updating faculty groups or overload approvals under Administration.` +
        (ctx.schedule ? `\n\n**${ctx.schedule.term}** currently has **${ctx.schedule.summary.critical} critical** and **${ctx.schedule.summary.warning} warnings**.` : ""),
      links: [LINK_CONFLICTS], chips: ["What does Under-Allocation mean?", "What is a time overlap?"],
    }),
  },
  {
    id: "overlap",
    aliases: ["overlap", "overlaps", "time overlap", "double booked", "double-booked", "clash", "time conflict", "same time", "low time diversity"],
    answer: () => ({
      text: `Time-block conflicts the scheduler checks:\n• **Instructor Time Overlap** (Critical): one person teaches two sections whose blocks overlap.\n• **Recitation Overlaps Lecture** (Critical): a recitation meets during its own linked lecture.\n• **Core Schedule Clash** (Warning): every section of two same-stage core courses overlaps, so students can't take both.\n• **Low Time Diversity** (Info): all sections of a core course share one block.\n\nThe automatic scheduler never creates the first two; they appear after manual edits.`,
      links: [LINK_CONFLICTS], chips: ["How are time slots assigned?"],
    }),
  },
  {
    id: "workload",
    aliases: ["workload", "workloads", "teaching load", "load", "loads", "contract", "ceiling", "allowed", "annual", "term target", "other semester", "assigned", "target from", "over-allocation", "under-allocation", "over allocated", "under allocated", "overallocated", "underallocated"],
    answer: () => ({
      text: `**Faculty workload** compares each person's projected annual load with their contract:\n• **Tenured Track / Tenured:** 3 per year (may teach fewer)\n• **Full-Time Teaching / Temporary:** 6 per year\n• **Adjunct:** 1–2 per year\n\n**Annual = Assigned (this term) + Other Semester** (planned load for the other semester: scheduler courseload, then the form, then teaching history). **Allowed** = contract range − graduate-teaching reduction + approved overloads. **Status** is Within Contract, Under Contract, Over Contract, or Overload in Use.`,
      links: [{ label: "See Workload", to: "/conflicts" }], chips: ["What is an overload?", "What is a courseload?"],
    }),
  },
  {
    id: "overload",
    aliases: ["overload", "overloads", "overloading", "extra compensation", "approved overload", "overload in use", "overload record mismatch"],
    answer: () => ({
      text: `An **overload** is an extra course beyond the contract, for additional compensation. Faculty request one on their preference form, and schedulers approve it under **Administration → Faculty & Overloads**. An approved overload raises that person's annual ceiling by one per approved semester, and their status shows **Overload in Use** when it's used. If the form and the approval disagree, you'll see **Overload Record Mismatch**.`,
      chips: ["What does Over Contract mean?", "What is a courseload?"],
    }),
  },
  {
    id: "reduction",
    aliases: ["courseload", "courseloads", "course load", "fall courseload", "spring courseload", "reduction", "reductions", "reduction per year", "buyout", "course release", "sabbatical", "grad teaching", "graduate teaching"],
    answer: () => ({
      text: `**Fall Courseload** and **Spring Courseload** are the number of courses a faculty member teaches each semester, set by a scheduler under **Administration → Faculty & Overloads**. They take priority over the preference form and teaching history when the term schedule is built, and they prefill the Teaching Load fields on that person's preference form. Leave one blank ("Auto") to fall back to the form, then history.
Use them to reflect course buyouts, releases, joint appointments or sabbaticals. Graduate teaching is still estimated from history and lowers the contract ceiling.`,
    }),
  },
  {
    id: "facultygroup",
    aliases: ["faculty group", "faculty type", "tenured", "tenure track", "tenured track", "adjunct", "full-time", "full time", "temporary", "recitation leader", "inferred", "confirmed"],
    answer: () => ({
      text: `**Faculty Group** sets the workload rule: Tenured Track / Tenured 3/yr, Full-Time Teaching and Temporary 6/yr, Adjunct 1–2/yr, and Recitation Leader (no contract). Groups marked **Inferred** were guessed from teaching history; confirm them under **Administration → Faculty & Overloads** so workload checks are accurate.`,
    }),
  },
  {
    id: "matching",
    aliases: ["assignment", "assignment basis", "match basis", "matching", "matched", "match", "rank", "ranked", "preference match", "top-3", "top 3", "who teaches", "assigned instructor", "core first", "priority", "teaching history", "core staffed", "staffed", "unstaffed"],
    answer: (ctx) => ({
      text: `Instructors are matched by one optimization over all sections:\n• **Mandatory core courses are staffed first.** Leaving one unstaffed is heavily penalized, so it happens only if nobody willing has capacity.\n• Higher preference ranks score higher (Rank 1 most; a Principles preference counts like a strong rank).\n• Electives run only if a willing instructor still has capacity.\n• Load is spread so no one gets every section.\n\n**Assignment** on the schedule shows why each person got a section: a rank, a Principles preference, teaching history, or Manual Edit.` +
        (ctx.schedule ? `\n\nNow: core staffed **${ctx.schedule.summary.core_staffed}/${ctx.schedule.summary.core_sections}**, **${ctx.schedule.summary.preference_matches}** top-3 preference matches from ${plural(ctx.schedule.summary.submissions, "form")}.` : ""),
      links: [LINK_SCHEDULE],
    }),
  },
  {
    id: "timeslots",
    aliases: ["time slot", "time slots", "time block", "time blocks", "sequence", "sequences", "seq", "seq.", "meeting time", "course_sequences", "calendar", "weekly calendar", "a-h", "1-5", "l-w", "when does", "linked lecture"],
    answer: () => ({
      text: `Time blocks follow **Course_Sequences.pdf**:\n• **Sequences 1–5:** Mon/Wed/Thu, 65 minutes (8:00, 9:15, 10:30, 1:35, 4:35).\n• **Sequences A–H:** two 100-minute meetings a week (e.g. C = Tue/Fri 8:00–9:40).\n• **Sequences L–W:** lab/studio windows; recitations use 65-minute slots inside them.\n• Sequences 6 and 7 are administrative and never used.\n\nThe scheduler never double-books an instructor or overlaps a recitation with its **Linked Lecture**. It also spreads sections of the same course and favors historically popular times.`,
      links: [{ label: "View Weekly Calendar", to: "/schedule" }],
    }),
  },
  {
    id: "electives",
    aliases: ["elective", "electives", "electives offered", "elective not offered", "minimum elective"],
    answer: (ctx) => ({
      text: `Electives are **preference-driven**. One is planned if demand is at least ${ctx.settings.min_elective_demand} students (Minimum Elective Enrollment), but it only **runs** if a faculty member who ranked it (or has taught it) still has capacity after core courses are staffed. Otherwise it shows as **Elective Not Offered** (Info) in Conflicts & Audits.` +
        (ctx.schedule ? ` ${ctx.schedule.term} has **${ctx.schedule.summary.electives_offered}** electives running.` : ""),
    }),
  },
  {
    id: "preferences",
    aliases: ["submit", "preference", "preferences", "preference form", "form", "forms", "rank courses", "teaching preferences"],
    answer: (ctx) => ({
      text: `To submit teaching preferences:\n1. **Sign in** with your faculty account (it's linked to your roster entry).\n2. Choose any **Principles** courses you'd teach.\n3. **Rank up to 6** undergraduate courses; search by code, level ("3000s") or topic.\n4. Enter **Fall and Spring course counts**, including any overload, and the overload semester.\n5. Add **unique circumstances** (sabbatical, buyout, joint appointment).\n\nYou can resubmit anytime; only your latest submission counts.`,
      links: [{ label: "Go to Teaching Preferences", to: "/preferences" }, ...(ctx.role ? [] : [{ label: "Sign In", to: "/login" }])],
    }),
  },
  {
    id: "collab",
    aliases: ["lock", "locked", "locking", "comment", "comments", "publish", "published", "publishing", "export", "csv", "catalog csv", "live", "presence", "real-time", "realtime", "manual edit", "manual edits"],
    answer: () => ({
      text: `**Collaboration:**\n• **Edit Section** locks a section to you; others see "Locked by …". Locks release on **Done Editing**, when you close your last tab, or after 15 idle minutes.\n• **Comments** are threaded on each section, with replies and resolve.\n• **Manual Edits** override the generated assignment until reverted.\n• **Publish** (schedulers) freezes a numbered version; it's blocked while critical conflicts remain unless you confirm.\n• **Catalog CSV** gives one row per meeting pattern for registrar import.`,
      links: [LINK_SCHEDULE],
    }),
  },
  {
    id: "roles",
    aliases: ["sign in", "login", "log in", "account", "role", "roles", "admin", "permission", "permissions", "password"],
    answer: (ctx) => ({
      text: `**Faculty** can submit their own preferences and comment on sections. **Schedulers (Admin)** can also edit and lock sections, publish, and manage the catalog, roster, overloads, accounts and enrollment data.` + (ctx.role ? ` You're signed in as **${ctx.role === "admin" ? "a scheduler" : "faculty"}**.` : ""),
      links: ctx.role ? [] : [{ label: "Sign In", to: "/login" }],
    }),
  },
];

// Words that mark a question as being about this app (for the smart fallback)
// (Scheduler vocabulary only; generic question words like "what is" or "why" don't count.)
const DOMAIN = /\b(econ|courses?|class(es)?|sections?|schedul\w*|term|semester|fall|spring|faculty|professors?|instructors?|teach\w*|students?|enroll\w*|demand|seats?|caps?|table|column|metrics?|numbers?|percent\w*|values?|rows?|page|dashboard|overview|planning|recitations?|electives?|core|conflicts?|audits?|projections?|workloads?|calendar|forecast\w*|registrar|catalog)\b|%/;

// ------------------------------------------------------- entity extraction ---
function findPercents(raw: string) {
  const out: { value: number; sign: -1 | 0 | 1; decimals: boolean }[] = [];
  for (const m of raw.matchAll(/([+\-−–])?\s?(\d{1,3}(?:\.\d+)?)\s?%/g)) {
    const sign = m[1] ? (m[1] === "+" ? 1 : -1) : 0;
    out.push({ value: parseFloat(m[2]), sign: sign as -1 | 0 | 1, decimals: m[2].includes(".") });
  }
  return out;
}

function findCourseCodes(raw: string, ctx: Ctx): number[] {
  const known = new Set<number>([...(ctx.courses ?? []).map((c) => c.code), ...(ctx.demand?.demand ?? []).map((r) => r.code)]);
  const codes = new Set<number>();
  for (const m of raw.matchAll(/\b(?:econ\s*)?(\d{4})\b(?!\s*%)/gi)) {
    const n = Number(m[1]);
    const explicit = /econ/i.test(m[0]);
    if (n >= 1000 && n < 5000 && (explicit || known.has(n))) codes.add(n);
    if (n >= 5000 && explicit) codes.add(n);
  }
  return [...codes];
}

function findFaculty(raw: string, ctx: Ctx): WorkloadRow | null {
  for (const w of ctx.schedule?.workload ?? []) {
    const last = w.faculty.split(",")[0].trim();
    if (last.length >= 3 && new RegExp(`\\b${last.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`).test(raw)) return w;
  }
  return null;
}

function modalityFilter(q: string): boolean | null {
  if (/\b(remote|online|virtual|async)\b/.test(q)) return true;
  if (/\b(in[- ]person|on[- ]campus)\b/.test(q)) return false;
  return null;
}

function bestTopic(q: string): Topic | null {
  let best: Topic | null = null;
  let score = 0;
  for (const t of TOPICS) {
    let s = 0;
    for (const a of t.aliases) if (hasWord(q, a)) s = Math.max(s, a.length + (a.includes(" ") ? 4 : 0));
    if (s > score) { best = t; score = s; }
  }
  return best;
}

function rowsFor(ctx: Ctx, code: number, virtual: boolean | null): DemandRow[] {
  const rows = (ctx.demand?.demand ?? []).filter((r) => r.code === code);
  if (virtual === null) return [...rows].sort((a, b) => Number(a.virtual) - Number(b.virtual));
  return rows.filter((r) => r.virtual === virtual);
}

// ----------------------------------------------------------- entity answers ---
function percentAnswer(raw: string, q: string, ctx: Ctx, topic: Topic | null): Answer | null {
  const pcts = findPercents(raw);
  if (!pcts.length) return null;
  if (!ctx.demand) return { text: `I'd need the forecast to look up that number. Open Enrollment Projections, then ask again. In general, signed percentages like +6.4% are **Trend per Year** (annual enrollment growth, capped ±10%), and plain ones like 98% are **Seat Fill** (projected ÷ planned seats).`, links: [LINK_DEMAND] };
  const codes = findCourseCodes(raw, ctx);
  const virt = modalityFilter(q);
  const pool = ctx.demand.demand.filter((r) => (!codes.length || codes.includes(r.code)) && (virt === null || r.virtual === virt));
  const p = pcts[0];
  const wantTrend = topic?.metric === "trend" || p.sign !== 0 || p.decimals;
  const wantFill = topic?.metric === "seatfill" || (!wantTrend && p.sign === 0);
  // The whole-term seat fill shown under "Seats Offered"
  const sm = ctx.demand.summary;
  const termFill = Math.round((100 * sm.projected_students) / Math.max(1, sm.seats_offered));

  if (Math.abs(p.value - 10) < 0.05 && /cap|limit|max|clip/.test(q)) return TOPICS.find((t) => t.id === "trend")!.answer(ctx);

  const trendHits = wantTrend ? pool.filter((r) => r.annual_trend && Math.abs(Math.abs(r.annual_trend * 100) - p.value) < 0.051 &&
    (p.sign === 0 || Math.sign(r.annual_trend) === p.sign)) : [];
  const fillHits = wantFill ? pool.filter((r) => r.planned_sections > 0 && Math.round(r.seat_fill * 100) === Math.round(p.value)) : [];
  const hits = trendHits.length ? trendHits : fillHits;
  const metric: Metric = trendHits.length ? "trend" : "seatfill";

  if (hits.length === 1) return { text: explainRow(metric, hits[0], ctx), links: [LINK_DEMAND],
    chips: metric === "trend" ? ["How is Projected calculated?", "What does Hist. Avg mean?"] : ["How are sections sized?", "What does Projected mean?"] };
  if (hits.length > 1) {
    const list = hits.slice(0, 8).map((r) => `• ${label(r)}`).join("\n");
    return { text: `**${raw.match(/[+\-−–]?\s?\d{1,3}(?:\.\d+)?\s?%/)![0].replace(/\s/g, "")}** appears for ${plural(hits.length, "row")} in the ${ctx.demand.term} forecast as **${metric === "trend" ? "Trend per Year" : "Seat Fill"}**:\n${list}\n\n${explainRow(metric, hits[0], ctx)}\n\nAsk about a specific course (e.g. "${hits[1].course}") for its numbers.`, links: [LINK_DEMAND] };
  }
  // Course named but the number differs (settings changed): give the course's current figure
  if (codes.length && pool.length) {
    const r = pool.find((x) => !x.virtual) ?? pool[0];
    const m: Metric = wantTrend ? "trend" : "seatfill";
    const now = m === "trend" ? (r.annual_trend ? pct1(r.annual_trend) : "no trend") : `${Math.round(r.seat_fill * 100)}%`;
    return { text: `With the current settings (${ctx.demand.term}, ${ctx.settings.growth_multiplier.toFixed(2)}× growth), ${label(r)} shows **${now}** rather than ${raw.match(/[+\-−–]?\s?\d{1,3}(?:\.\d+)?\s?%/)![0].replace(/\s/g, "")}; the figure changes with the term and Planning Settings.\n\n${explainRow(m, r, ctx)}`,
      links: [LINK_DEMAND] };
  }
  if (wantFill && Math.round(p.value) === termFill && !codes.length)
    return { text: `**${termFill}%** is the overall seat fill for ${ctx.demand.term}: ${sm.projected_students.toLocaleString()} projected lecture students ÷ ${sm.seats_offered.toLocaleString()} planned seats. Per-course Seat Fill is the same calculation for one course's sections.`, links: [LINK_DEMAND] };
  return {
    text: `I don't see ${raw.match(/[+\-−–]?\s?\d{1,3}(?:\.\d+)?\s?%/)![0].replace(/\s/g, "")} ${codes.length ? `for ECON ${codes.join(", ")} ` : ""}in the current **${ctx.demand.term}** forecast. Numbers change with Planning Settings, so it may come from a different term or setting.\n\n` +
      (wantTrend ? `Signed percentages are **Trend per Year**: annual enrollment growth from the history window, capped at ±10.0%, compounded into Projected.` : `Plain percentages are usually **Seat Fill**: Projected ÷ total planned seats; 95%+ is near capacity.`),
    links: [LINK_DEMAND], chips: ["What does Trend per Year mean?", "What does seat fill mean?"],
  };
}

function numberAnswer(raw: string, ctx: Ctx): Answer | null {
  if (!ctx.demand) return null;
  const nums = [...raw.matchAll(/(?<![\d.%])\b(\d{2,4})\b(?![\d.]*\s?%)/g)].map((m) => Number(m[1]))
    .filter((n) => !(n >= 1000 && n < 5000) && !(n >= 2000 && n <= 2100));
  for (const n of nums) {
    const hits: [Metric, DemandRow][] = [];
    for (const r of ctx.demand.demand) {
      if (r.projected_enrollment === n) hits.push(["projected", r]);
      else if (r.hist_weighted_avg === n) hits.push(["histavg", r]);
      else if (r.seats_offered === n && r.planned_sections > 0) hits.push(["seatfill", r]);
    }
    if (hits.length === 1) return { text: explainRow(hits[0][0], hits[0][1], ctx), links: [LINK_DEMAND] };
    if (hits.length > 1 && hits.length <= 6)
      return { text: `**${n}** appears in several places in the ${ctx.demand.term} forecast:\n` + hits.map(([m, r]) => `• ${label(r)}: ${m === "projected" ? "Projected" : m === "histavg" ? "Hist. Avg" : "Seats Offered"}`).join("\n") + `\n\nAsk about one course for the breakdown.`, links: [LINK_DEMAND] };
  }
  return null;
}

function sectionAnswer(raw: string, ctx: Ctx): Answer | null {
  const sid = /ECON\s?(\d{4})-(\d{2})/i.exec(raw);
  if (!sid) return null;
  const id = `ECON ${sid[1]}-${sid[2]}`;
  const row = ctx.schedule?.master.find((r) => r.section_id === id);
  if (!row) return { text: `I can't find **${id}** in the ${ctx.schedule?.term ?? "current"} schedule. Section numbers change with the planning settings.`, links: [LINK_SCHEDULE] };
  const cs = ctx.schedule!.conflicts.filter((c) => c.course_section.includes(id));
  const lock = ctx.schedule!.locks.find((l) => l.section_id === id);
  return {
    text: `**${id}** · ${row.title}\n• **Instructor:** ${row.instructor} (${row.faculty_type}), assigned by *${row.match_basis}*\n• **Meeting:** ${row.meeting_time} (sequence ${row.sequence})\n• **Proj. / Cap:** ${row.projected_enrollment} / ${row.section_cap}` +
      (row.linked_lecture ? `\n• **Linked Lecture:** ${row.linked_lecture}` : "") + (lock ? `\n• Locked by ${lock.user_name}` : "") +
      (cs.length ? `\n\n**Flagged (${cs.length}):**\n` + cs.map((c) => `• **${c.category}** (${c.severity}): ${c.details}`).join("\n") : `\n\nNo conflicts on this section.`),
    links: [{ label: `Open ${id}`, to: `/schedule?section=${encodeURIComponent(id)}` }],
  };
}

function facultyAnswer(w: WorkloadRow, ctx: Ctx): Answer {
  const status = tc(w.status.replace(/^[^\p{L}]+/u, ""));
  const key = Object.keys(STATUS_EXPLAIN).find((k) => status.toLowerCase().startsWith(k));
  const secs = ctx.schedule?.master.filter((r) => r.instructor === w.faculty).map((r) => r.section_id) ?? [];
  const cs = ctx.schedule?.conflicts.filter((c) => c.faculty === w.faculty && c.severity !== "Info") ?? [];
  return {
    text: `**${w.faculty}** (${w.type}) is **${status}**. ${key ? STATUS_EXPLAIN[key] : ""}\n• **Assigned this term:** ${w.assigned_this_term}${secs.length ? ` (${secs.join(", ")})` : ""}\n• **Other semester planned:** ${w.other_semester_planned} (from ${w.target_source.toLowerCase()})\n• **Projected annual:** ${w.projected_annual} vs. **allowed** ${w.allowed_annual}` +
      (w.annual_reduction ? `\n• **Annual reduction:** ${w.annual_reduction}` : "") +
      `\n• **Overload:** approved ${w.overload_approved_json}, requested ${w.overload_requested_form}` +
      (cs.length ? `\n\n**Open issues:** ` + cs.map((c) => c.category).join(", ") : ""),
    links: [{ label: "See Workload", to: "/conflicts" }],
  };
}

function courseAnswer(code: number, raw: string, q: string, ctx: Ctx, topic: Topic | null): Answer {
  if (code >= 5000) return { text: `ECON ${code} is a graduate course. This scheduler covers undergraduate courses only (below 5000).` };
  const virt = modalityFilter(q);
  const rows = rowsFor(ctx, code, virt);
  const c = ctx.courses?.find((x) => x.code === code);
  // A specific metric asked about this course → the data-backed explanation
  if (topic?.metric && rows.length) {
    const r = rows[0];
    const other = virt === null && rows.length > 1 ? `\n\nThe remote sections are a separate row: ${explainRow(topic.metric, rows[1], ctx)}` : "";
    // Follow-ups about the same course, skipping the metric just explained
    const follow: Record<string, string> = {
      trend: `What does ${r.course}'s trend mean?`, projected: `Why is ${r.course} projected at ${r.projected_enrollment}?`,
      sections: `How many sections does ${r.course} have?`, seatfill: `Why is ${r.course} at ${Math.round(r.seat_fill * 100)}% seat fill?`,
      histavg: `What is ${r.course}'s Hist. Avg?`,
    };
    const skip = topic.metric === "caps" ? "sections" : topic.metric;
    return { text: explainRow(topic.metric, r, ctx) + other, links: [LINK_DEMAND],
      chips: Object.entries(follow).filter(([k]) => k !== skip).map(([, v]) => v).slice(0, 2) };
  }
  // Overview of the course across catalog, forecast and schedule
  const secs = ctx.schedule?.master.filter((r) => r.course === `ECON ${code}`) ?? [];
  const cs = ctx.schedule?.conflicts.filter((x) => x.course_section.includes(`ECON ${code}`) && x.severity !== "Info") ?? [];
  if (!c && !rows.length && !secs.length) return { text: `I couldn't find ECON ${code} in the active undergraduate catalog or the ${ctx.settings.target_term} plan.` };
  const lines: string[] = [];
  if (c) lines.push(`**ECON ${code}: ${c.title}** (${c.category})`, c.description ? c.description : "", `**Prerequisites:** ${c.prerequisites}`);
  for (const r of rows) lines.push(`**${label(r)} forecast:** ${r.projected_enrollment} projected (Hist. Avg ${r.hist_weighted_avg ?? "—"}, trend ${r.annual_trend ? pct1(r.annual_trend) : "—"}) → ${plural(r.planned_sections, "section")} (${r.section_caps}), **${Math.round(r.seat_fill * 100)}%** seat fill.`);
  if (secs.length) lines.push(`**${ctx.schedule!.term} schedule:** ${secs.map((s) => `${s.section_id.slice(-2)} ${s.instructor} (${s.sequence})`).join(" · ")}`);
  if (cs.length) lines.push(`**Flagged:** ${cs.map((x) => `${x.category} (${x.course_section})`).join("; ")}`);
  void raw;
  return { text: lines.filter(Boolean).join("\n"), links: [LINK_DEMAND, LINK_SCHEDULE],
    chips: rows.length ? [`What does ${rows[0].course}'s trend mean?`, `Why is ${rows[0].course} at ${Math.round(rows[0].seat_fill * 100)}% seat fill?`] : undefined };
}

function categoryAnswer(q: string, ctx: Ctx): Answer | null {
  const key = Object.keys(CONFLICT_EXPLAIN).sort((a, b) => b.length - a.length).find((k) => q.includes(k));
  if (key) {
    const live = ctx.schedule?.conflicts.filter((c) => c.category.toLowerCase() === key) ?? [];
    return {
      text: `**${tc(key)}:** ${CONFLICT_EXPLAIN[key]}` +
        (ctx.schedule ? (live.length ? `\n\nRight now **${live.length}** in ${ctx.schedule.term}: ${live.slice(0, 5).map((c) => c.faculty !== "—" ? c.faculty : c.course_section).join(", ")}${live.length > 5 ? "…" : ""}.` : `\n\nNone in ${ctx.schedule.term} right now.`) : ""),
      links: [LINK_CONFLICTS],
    };
  }
  const st = Object.keys(STATUS_EXPLAIN).find((k) => q.includes(k));
  if (st) {
    const live = ctx.schedule?.workload.filter((w) => w.status.toLowerCase().includes(st)) ?? [];
    return { text: `**${tc(st)}:** ${STATUS_EXPLAIN[st]}` + (live.length ? `\n\nCurrently: ${live.slice(0, 6).map((w) => w.faculty).join("; ")}.` : ""), links: [{ label: "See Workload", to: "/conflicts" }] };
  }
  return null;
}

/** Direct, page-aware answer for scheduler questions that don't name a specific metric. */
function pageSummary(ctx: Ctx): Answer {
  const d = ctx.demand, s = ctx.schedule;
  if (ctx.page.startsWith("/demand") && d)
    return { text: `On **Enrollment Projections** for **${d.term}**: ${d.summary.courses} courses planned, ${d.summary.lecture_sections} lecture sections and ${d.summary.recitation_sections} recitations, ${d.summary.projected_students.toLocaleString()} projected students in ${d.summary.seats_offered.toLocaleString()} seats. Each row's **Projected = recency-weighted Hist. Avg of prior same-season terms × annual trend × growth multiplier**, and **Seat Fill = Projected ÷ seats**. Ask about any column, value or course.`,
      chips: ["What does Trend per Year mean?", "What does Hist. Avg mean?", "What does seat fill mean?"] };
  if ((ctx.page.startsWith("/schedule") || ctx.page.startsWith("/conflicts") || ctx.page === "/") && s)
    return { text: `For **${s.term}**: ${s.summary.sections} sections, core staffed **${s.summary.core_staffed}/${s.summary.core_sections}**, ${s.summary.electives_offered} electives running, **${s.summary.critical} critical** and **${s.summary.warning} warnings**. Ask about a section (e.g. "ECON 2315-01"), a faculty member, a conflict type or any column.`,
      chips: ["How do I resolve conflicts?", "How are time slots assigned?", "What does Under-Allocation mean?"] };
  return { text: `I can explain any column, value or course in the scheduler. Try a course ("ECON 1115"), a number on screen ("+6.4%", "98%"), a section ("ECON 2315-01"), a faculty member, or a term like "Hist. Avg".`, chips: STARTER_PROMPTS.slice(0, 3) };
}

// ------------------------------------------------------------------- answer ---
export function answer(question: string, ctx: Ctx): Answer {
  const raw = question.trim();
  const q = norm(raw);
  const topic = bestTopic(q);

  const sec = sectionAnswer(raw, ctx);
  if (sec) return sec;

  const pct = percentAnswer(raw, q, ctx, topic);
  if (pct) return pct;

  const codes = findCourseCodes(raw, ctx);
  if (codes.length) return courseAnswer(codes[0], raw, q, ctx, topic);

  const fac = findFaculty(raw, ctx);
  if (fac) return facultyAnswer(fac, ctx);

  const cat = categoryAnswer(q, ctx);
  if (cat) return cat;

  if (/\b(\d+)-level|\b([1-4])000s\b/.test(q) && ctx.courses && /course|class|list|show|which|what/.test(q)) {
    const lv = Number((/([1-4])000/.exec(q) ?? ["", "1"])[1] + "000");
    const list = ctx.courses.filter((c) => c.level === lv);
    return { text: `**${lv}-level courses (${list.length}):**\n` + list.map((c) => `• ECON ${c.code}: ${c.title}`).join("\n") };
  }

  if (topic) return topic.answer(ctx);

  const num = numberAnswer(raw, ctx);
  if (num) return num;

  if (DOMAIN.test(q)) return pageSummary(ctx);

  return {
    text: `I can help with planning settings, forecasts (Hist. Avg, Trend per Year, Projected, Seat Fill), sections and recitations, time blocks, instructor matching, conflicts, workloads, prerequisites, and collaboration (locks, comments, publishing). You can also ask about a specific course like "ECON 3424" or a number on screen.`,
    chips: STARTER_PROMPTS.slice(0, 3),
  };
}
