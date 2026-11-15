// Intent-based knowledge for the site assistant. Answers are written against how
// this application actually behaves (engine.py / the API), not generic advice.
// Matching: each intent lists keywords/phrases; the highest-scoring intent wins.

import type { Course, PlanSettings, ScheduleResponse } from "../../api";

export interface Answer { text: string; links?: { label: string; to: string }[] }
interface Intent { id: string; keywords: string[]; answer: Answer | ((ctx: Ctx) => Answer) }
export interface Ctx { settings: PlanSettings; schedule: ScheduleResponse | null; courses: Course[] | null; role: string | null }

export const STARTER_PROMPTS = [
  "How do I use planning settings?",
  "What does seat fill mean?",
  "How are recitations calculated?",
  "How do I submit my preferences?",
  "How are time slots assigned?",
  "How do I resolve conflicts?",
];

const INTENTS: Intent[] = [
  {
    id: "settings",
    keywords: ["planning settings", "settings", "target semester", "target term", "growth", "multiplier", "history window", "persist", "saved", "trend", "configure"],
    answer: (ctx) => ({
      text:
        `**Planning settings** control every forecast and schedule. They're saved in your browser and shared across Demand Estimator, Master Schedule and Conflicts, so changing one updates them all.\n\n` +
        `• **Target semester**: pick it in the top bar. Upcoming terms are forecasts. Past terms run as a back-test, with actual enrollment shown next to the projection.\n` +
        `• **Enrollment growth** (0.85×–1.50×) scales projected *students*, not section caps. More students means more sections.\n` +
        `• **History window**: how many prior terms of the same season (Fall or Spring only) feed the forecast. Recent terms count more.\n` +
        `• **Apply historical trend**: extends each course's year-over-year trend, capped at ±10% per year.\n` +
        `• **Caps**: large lecture (Principles), small section, remote (max 25) and recitation sizes.\n\n` +
        `You're currently planning **${ctx.settings.target_term || "—"}** at **${ctx.settings.growth_multiplier.toFixed(2)}×** growth with a ${ctx.settings.history_window}-term window.`,
      links: [{ label: "Open Demand Estimator", to: "/demand" }],
    }),
  },
  {
    id: "seat-fill",
    keywords: ["seat fill", "seats fill", "fill", "seats offered", "class cap", "section cap", "capacity", "utilization", "cap mean"],
    answer: {
      text:
        `**Class (section) cap** is the most seats a single section can hold. It comes from the course's typical historical cap.\n\n` +
        `**Seats offered** is the sum of the caps of all planned sections of a course.\n\n` +
        `**Seat fill** = projected enrollment ÷ seats offered. For example, 573 projected students in three 200-seat lectures is 573 ÷ 600 = **96%**. ` +
        `High fill means sections will be nearly full; low fill can mean an extra section isn't needed.\n\n` +
        `A small class can go up to 10% over its historical cap before a second section is opened. That way 44 students get one 44-seat section, not two half-empty ones.`,
    },
  },
  {
    id: "remote",
    keywords: ["remote", "online", "virtual", "async", "asynchronous", "25"],
    answer: {
      text:
        `**Remote and online sections are capped at 25 students.** It's a hard limit; the settings won't go higher, and the conflict report flags any remote section above 25.\n\n` +
        `Remote demand is forecast separately from in-person demand, using history from terms that offered online sections. Online sections are asynchronous, so they get no time slot and never cause time conflicts. ` +
        `Online Principles students aren't counted toward recitations.`,
    },
  },
  {
    id: "recitations",
    keywords: ["recitation", "recitations", "1125", "1126", "lab section", "discussion section"],
    answer: (ctx) => {
      // Use the live plan when it's loaded so the example matches what's on screen
      const macro = ctx.schedule?.master.filter((r) => r.course === "ECON 1115" && r.component === "Lecture" && !r.modality.startsWith("Online"))
        .reduce((n, r) => n + r.projected_enrollment, 0) || 573;
      const cap = ctx.settings.recitation_cap;
      return {
      text:
        `Recitations are weekly **65-minute** sessions: **ECON 1125** for Macro (1115) and **ECON 1126** for Micro (1116).\n\n` +
        `**Count** = ⌈on-campus lecture students ÷ recitation cap⌉. ${ctx.schedule ? `For ${ctx.schedule.term}, Macro has` : "For example,"} **${macro}** on-campus students at a cap of **${cap}** → ⌈${macro} ÷ ${cap}⌉ = **${Math.ceil(macro / cap)}** recitations.\n\n` +
        `• Recitations are split across lecture sections in proportion to their enrollment, and each one is **linked to a single lecture**.\n` +
        `• They're scheduled in 65-minute slots inside the lab/studio windows (sequences L–W) and **never overlap their linked lecture**. The scheduler also tries to keep them clear of the course's other lectures.\n` +
        `• They're staffed by recitation leaders, not by lecture faculty, and don't count toward faculty course loads.`,
      links: [{ label: "See Recitation Math", to: "/demand" }],
      };
    },
  },
  {
    id: "forecast",
    keywords: ["forecast", "projection", "projected", "demand", "estimate", "how many sections", "sections calculated", "enrollment"],
    answer: {
      text:
        `**Projected enrollment** = recency-weighted average of prior terms of the same season × annual trend (±10% per year cap) × growth multiplier.\n\n` +
        `**Section counts**:\n` +
        `• **Principles (1115/1116)**: large lectures at the large-lecture cap (default 200) while demand supports them, then the rest in small sections (default 45).\n` +
        `• **Other courses**: the course's historical cap. A new section opens only when demand is more than 10% over the cap.\n` +
        `• **Remote**: sections of at most 25.\n` +
        `• **Electives** under the minimum enrollment aren't planned. Planned electives still only run if a faculty member is matched to them.\n\n` +
        `Missing historical counts are estimated as cap × the course's usual fill rate, so they don't drag the forecast down.`,
      links: [{ label: "Open Demand Estimator", to: "/demand" }],
    },
  },
  {
    id: "preferences",
    keywords: ["submit", "preference", "preferences", "form", "rank", "ranking", "overload", "teaching load", "sabbatical", "buyout"],
    answer: (ctx) => ({
      text:
        `To submit teaching preferences:\n` +
        `1. **Sign in** with your faculty account. Your account is linked to your roster entry, so your name is filled in.\n` +
        `2. Optionally choose the **Principles** courses you'd teach (1115 / 1116).\n` +
        `3. **Rank up to 6** undergraduate courses. Search by code ("3424"), level ("3000s"), title or topic. Graduate (5000+) courses can't be selected.\n` +
        `4. Enter your **Fall and Spring course counts**, *including* any overload (e.g. 3 + 1 overload → 4), and which semester you're overloading.\n` +
        `5. Note **unique circumstances**: joint appointment, course reduction, buyout or sabbatical.\n\n` +
        `You can resubmit any time; only your **latest** submission is used. Electives run only when someone ranks them.` +
        (ctx.role ? "" : `\n\nYou're not signed in yet.`),
      links: [{ label: "Go to Teaching Preferences", to: "/preferences" }, ...(ctx.role ? [] : [{ label: "Sign In", to: "/login" }])],
    }),
  },
  {
    id: "core",
    keywords: ["core", "mandatory", "required", "priority", "prioritize", "prioritization", "staffed first", "unstaffed", "matching", "assign instructors", "who teaches"],
    answer: {
      text:
        `**Mandatory core courses are staffed first.** These are ECON 1000, Principles (1115, 1116, 2350), the follow-ups (2315, 2316, 2560) and the capstones (4692 Senior Seminar, 4997 Senior Thesis).\n\n` +
        `Matching is a single optimization over all sections:\n` +
        `• Higher-ranked preferences score higher (Rank 1 counts most; a Principles preference counts like a strong rank).\n` +
        `• Leaving a core section unstaffed is heavily penalized, so it only happens when *no* willing instructor has capacity.\n` +
        `• Electives are offered only when a willing instructor still has capacity after core is covered.\n` +
        `• Load is spread so one person isn't given every section.\n\n` +
        `Faculty without a form are matched on teaching history while "Use Teaching History Without a Form" is on.`,
      links: [{ label: "Open Master Schedule", to: "/schedule" }],
    },
  },
  {
    id: "time-slots",
    keywords: ["time slot", "time slots", "sequence", "sequences", "course_sequences", "time block", "blocks", "when", "schedule time", "a-h", "1-5", "l-w", "calendar"],
    answer: {
      text:
        `Time blocks follow **Course_Sequences.pdf**:\n` +
        `• **Sequences 1–5**: Mon/Wed/Thu, 65 minutes (8:00, 9:15, 10:30, 1:35, 4:35).\n` +
        `• **Sequences A–H**: two 100-minute meetings a week (e.g. C = Tue/Fri 8:00–9:40; H = Tue 11:45 + Thu 2:50).\n` +
        `• **Sequences L–W**: lab/studio windows. Recitations use 65-minute slots inside them.\n` +
        `• Sequences 6 and 7 are administrative and never used.\n\n` +
        `The scheduler never double-books an instructor and never overlaps a recitation with its lecture. It also spreads sections of the same course, avoids stacking core courses students take together, and favors historically popular times.`,
      links: [{ label: "View Weekly Calendar", to: "/schedule" }],
    },
  },
  {
    id: "conflicts",
    keywords: ["conflict", "conflicts", "resolve", "fix", "critical", "warning", "overlap", "error", "issue"],
    answer: (ctx) => ({
      text:
        `To resolve conflicts:\n` +
        `1. Open **Conflicts** and filter to **Critical** first: unstaffed core sections, instructor double-bookings, recitation and lecture overlaps, remote caps over 25.\n` +
        `2. Click into the section on **Master Schedule** and choose **Edit section**. This locks it so other schedulers can't change it at the same time.\n` +
        `3. Change the instructor or sequence. Conflicts recompute immediately for everyone.\n` +
        `4. Use **comments** on the section to discuss trade-offs, then **Done editing** to release the lock.\n` +
        `5. **Warnings** (over/under-allocation, overload mismatches) usually mean updating the faculty roster or overload approvals in Administration.` +
        (ctx.schedule ? `\n\nRight now **${ctx.schedule.term}** has **${ctx.schedule.summary.critical} critical** and **${ctx.schedule.summary.warning} warnings**.` : ""),
      links: [{ label: "Open Conflicts", to: "/conflicts" }],
    }),
  },
  {
    id: "workload",
    keywords: ["workload", "load", "tenured", "adjunct", "full-time", "full time", "temporary", "contract", "over-allocation", "under-allocation", "allocation", "6/yr", "3/yr"],
    answer: {
      text:
        `**Annual teaching loads**:\n• Tenured: 3 courses per year (may teach fewer)\n• Full-time teaching and temporary: 6 per year\n• Adjuncts: 1–2 per year\n\n` +
        `Each person's annual load = sections assigned this term + their planned load for the other semester. An **approved overload** (Administration → Faculty) raises the ceiling and is flagged for extra compensation. ` +
        `An **annual reduction** (graduate teaching, buyout, sabbatical) lowers it. Faculty groups are inferred from teaching history until a scheduler confirms them.`,
      links: [{ label: "See Workload", to: "/conflicts" }],
    },
  },
  {
    id: "prereqs",
    keywords: ["prerequisite", "prerequisites", "prereq", "level", "1000-level", "3000-level", "4000-level"],
    answer: {
      text:
        `Prerequisite rules by level:\n• **1000-level**: none\n• **3000-level**: require the Principles courses\n• **4000-level**: multiple prerequisites including theory (2315/2316); the capstones also require Econometrics (2560)\n\n` +
        `The Demand Estimator checks every offered course against these rules, and confirms its prerequisites are offered that term so students have a path in. Graduate (5000+) courses are excluded everywhere.`,
    },
  },
  {
    id: "collab",
    keywords: ["lock", "locking", "comment", "comments", "collaborat", "real-time", "realtime", "live", "who else", "presence", "publish", "publishing", "export", "csv", "catalog import"],
    answer: {
      text:
        `**Collaboration**:\n• **Live updates**: edits, locks, comments and publishes appear instantly for everyone. "Live" in the top bar shows the connection, and avatars show who's online.\n` +
        `• **Section locks**: *Edit section* locks a section to you; others see "Locked by …" and can't change it. Locks release when you click *Done*, close your last tab, or after 15 idle minutes.\n` +
        `• **Comments**: threaded discussion on each section, with replies and resolve.\n` +
        `• **Publishing** (schedulers only) freezes the current schedule as a numbered version. It's blocked while critical conflicts remain unless you confirm.\n` +
        `• **Export**: *Catalog CSV* gives one row per meeting pattern (subject, number, section, days, start/end time, instructor, capacity) for registrar import.`,
      links: [{ label: "Open Master Schedule", to: "/schedule" }],
    },
  },
  {
    id: "roles",
    keywords: ["sign in", "login", "log in", "account", "role", "admin", "permission", "access", "password"],
    answer: (ctx) => ({
      text:
        `There are two roles:\n• **Faculty** can submit their own teaching preferences and comment on sections.\n• **Schedulers (admins)** can also edit and lock sections, publish schedules, and manage the catalog, faculty roster, overloads, user accounts and enrollment data.\n\n` +
        `Anyone can view the dashboards read-only.` + (ctx.role ? ` You're signed in as **${ctx.role === "admin" ? "a scheduler" : "faculty"}**.` : ""),
      links: ctx.role ? [] : [{ label: "Sign In", to: "/login" }],
    }),
  },
  {
    id: "navigation",
    keywords: ["navigate", "navigation", "where", "pages", "workflow", "get started", "how do i use", "help", "what can you do", "overview"],
    answer: {
      text:
        `A typical planning cycle:\n1. **Teaching Preferences**: faculty submit rankings and loads.\n2. **Demand Estimator**: set the term and growth, and review sections and recitations.\n` +
        `3. **Master Schedule**: review instructor matches and time slots in the grid or weekly calendar, and edit sections.\n4. **Conflicts**: clear critical issues and check workloads.\n5. **Publish** and export the catalog CSV.\n\n` +
        `Ask me about any step, a course ("ECON 3424"), a level ("3000s"), or your current settings.`,
    },
  },
];

function norm(s: string) {
  return s.toLowerCase().replace(/[^a-z0-9\s/–-]/g, " ").replace(/\s+/g, " ").trim();
}

/** Dynamic answers that use live data (courses, levels, current numbers). */
function dynamicAnswer(q: string, ctx: Ctx): Answer | null {
  const code = /\b(?:econ\s*)?(\d{4})\b/i.exec(q)?.[1];
  const level = /\b([1-4])000s?\b|\b([1-4])000-level\b/i.exec(q);
  if (code && Number(code) >= 5000) return { text: `ECON ${code} is a graduate course. This scheduler covers undergraduate courses only (below 5000).` };
  if (code && ctx.courses) {
    const c = ctx.courses.find((x) => x.code === Number(code));
    if (c) {
      const secs = ctx.schedule?.master.filter((r) => r.course === `ECON ${c.code}`) ?? [];
      return {
        text: `**ECON ${c.code}: ${c.title}** (${c.category})\n\n${c.description || "No description on file."}\n\n` +
          `**Prerequisites:** ${c.prerequisites}\n**Offered** in ${c.times_offered} past term(s) on record.` +
          (ctx.schedule ? `\n**${ctx.schedule.term}:** ${secs.length ? `${secs.length} section(s), taught by ${[...new Set(secs.map((s) => s.instructor))].join(", ")}` : "not currently planned"}.` : ""),
        links: [{ label: "Open Master Schedule", to: "/schedule" }],
      };
    }
    // Bare 4-digit numbers are often years ("Spring 2027"); only report a miss for explicit "ECON ####"
    if (!level && /econ\s*\d{4}/.test(q)) return { text: `I couldn't find ECON ${code} in the active undergraduate catalog.` };
  }
  if (level && ctx.courses && /course|class|list|show|what|which|level|s\b/.test(q)) {
    const lv = Number((level[1] ?? level[2]) + "000");
    const list = ctx.courses.filter((c) => c.level === lv);
    return { text: `**${lv}-level courses (${list.length}):**\n` + list.map((c) => `• ECON ${c.code}: ${c.title}`).join("\n") };
  }
  if (/my settings|current settings|what term|which term/.test(q))
    return INTENTS.find((i) => i.id === "settings")!.answer instanceof Function
      ? (INTENTS.find((i) => i.id === "settings")!.answer as (c: Ctx) => Answer)(ctx) : null;
  return null;
}

export function answer(question: string, ctx: Ctx): Answer {
  const q = norm(question);
  const dyn = dynamicAnswer(q, ctx);
  if (dyn) return dyn;
  let best: Intent | null = null;
  let bestScore = 0;
  for (const intent of INTENTS) {
    let score = 0;
    for (const k of intent.keywords) {
      if (q.includes(k)) score += k.includes(" ") ? 3 : 1;   // phrases are stronger signals
    }
    if (score > bestScore) { best = intent; bestScore = score; }
  }
  if (!best) {
    return {
      text: `I can help with planning settings, forecasts and seat fill, recitations, time slots, matching and core priority, conflicts, workloads, prerequisites, collaboration (locks, comments, publishing) and specific courses like "ECON 3424". Try one of the suggestions below.`,
    };
  }
  return typeof best.answer === "function" ? best.answer(ctx) : best.answer;
}
