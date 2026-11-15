// Weekly calendar aligned with Course_Sequences.pdf (Mon–Fri, 8:00 AM – 5:40 PM).
// Sections sharing a sequence on a day are grouped into one block; overlapping
// blocks are laid out side by side in lanes.
import { Lock, MessageSquare } from "lucide-react";
import { useMemo, useState } from "react";
import type { MasterRow, Meta, SequenceInfo } from "../api";
import { Badge, CATEGORIES, CategoryDot, categoryStyle, cx } from "./ui";

const DAYS = [["M", "Mon"], ["T", "Tue"], ["W", "Wed"], ["R", "Thu"], ["F", "Fri"]] as const;
const START = 8 * 60;
const END = 17 * 60 + 45;
const PX = 1.1;

const fmt = (m: number) => {
  const h = Math.floor(m / 60), mm = m % 60;
  return `${h % 12 || 12}:${String(mm).padStart(2, "0")}`;
};

interface Ev { key: string; day: string; start: number; end: number; seq: SequenceInfo; rows: MasterRow[]; lane: number; lanes: number }

function layout(events: Omit<Ev, "lane" | "lanes">[]): Ev[] {
  const sorted = [...events].sort((a, b) => a.start - b.start || b.end - a.end);
  const out: Ev[] = [];
  let cluster: Ev[] = [];
  let clusterEnd = -1;
  const flush = () => {
    const lanes = Math.max(1, ...cluster.map((e) => e.lane + 1));
    cluster.forEach((e) => (e.lanes = lanes));
    cluster = [];
  };
  for (const e of sorted) {
    if (e.start >= clusterEnd && cluster.length) flush();
    const used = new Set(cluster.filter((c) => c.end > e.start).map((c) => c.lane));
    let lane = 0;
    while (used.has(lane)) lane++;
    const ev: Ev = { ...e, lane, lanes: 1 };
    cluster.push(ev);
    out.push(ev);
    clusterEnd = Math.max(clusterEnd, e.end);
  }
  if (cluster.length) flush();
  return out;
}

export function WeekCalendar({ rows, meta, flagged, locked, comments, onOpen }: {
  rows: MasterRow[]; meta: Meta; flagged: Set<string>; locked: Map<string, string>; comments: Record<string, number>;
  onOpen: (sectionId: string) => void;
}) {
  const [selected, setSelected] = useState<string | null>(null);
  const seqs = useMemo(() => ({ ...meta.sequences.class, ...meta.sequences.lab, ...meta.sequences.recitation }), [meta]);

  const byDay = useMemo(() => {
    const groups = new Map<string, Omit<Ev, "lane" | "lanes">>();
    for (const r of rows) {
      const seq = seqs[r.sequence];
      if (!seq) continue;
      for (const b of seq.blocks) {
        const key = `${b.day}|${seq.code}|${b.start}`;
        const g = groups.get(key) ?? { key, day: b.day, start: b.start, end: b.end, seq, rows: [] };
        g.rows.push(r);
        groups.set(key, g);
      }
    }
    const res: Record<string, Ev[]> = {};
    for (const [d] of DAYS) res[d] = layout([...groups.values()].filter((g) => g.day === d));
    return res;
  }, [rows, seqs]);

  const unplaced = rows.filter((r) => !seqs[r.sequence]);
  const selectedEv = selected ? Object.values(byDay).flat().find((e) => e.key === selected) : null;
  const hours: number[] = [];
  for (let h = 8; h <= 17; h++) hours.push(h * 60);

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted">
        {CATEGORIES.map((k) => <span key={k} className="flex items-center gap-1.5"><CategoryDot category={k} />{k}</span>)}
        <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm ring-1 ring-nu" />Has a Critical or Warning Conflict</span>
      </div>
      <div className="overflow-x-auto rounded-md border border-line">
        <div className="grid min-w-[860px]" style={{ gridTemplateColumns: "48px repeat(5, 1fr)" }}>
          <div className="border-b border-line bg-subtle" />
          {DAYS.map(([d, name]) => (
            <div key={d} className="border-b border-l border-line bg-subtle px-2 py-1.5 text-center text-[11px] font-medium text-muted">{name}</div>
          ))}
          <div className="relative" style={{ height: (END - START) * PX }}>
            {hours.map((m) => (
              <div key={m} className="absolute right-2 -translate-y-1/2 text-[10px] tabular-nums text-faint" style={{ top: (m - START) * PX }}>{fmt(m)}</div>
            ))}
          </div>
          {DAYS.map(([d]) => (
            <div key={d} className="relative border-l border-line" style={{ height: (END - START) * PX }}>
              {hours.map((m) => <div key={m} className="absolute inset-x-0 border-t border-line/70" style={{ top: (m - START) * PX }} />)}
              {byDay[d].map((e) => {
                // Category mix of the block, in legend order, for the left stripe
                const counts = CATEGORIES.map((c) => [c, e.rows.filter((r) => r.category === c).length] as const).filter(([, n]) => n > 0);
                const other = e.rows.length - counts.reduce((n, [, k]) => n + k, 0);
                const hot = e.rows.some((r) => flagged.has(r.section_id));
                const h = (e.end - e.start) * PX;
                const chipRows = Math.max(0, Math.floor((h - (h > 34 ? 32 : 18)) / 15));
                return (
                  <button key={e.key} onClick={() => setSelected(e.key === selected ? null : e.key)}
                    title={`${e.seq.code} · ${e.seq.label}\n${e.rows.map((r) => `${r.section_id}  ${r.category}  ${r.instructor}`).join("\n")}`}
                    className={cx("absolute flex overflow-hidden rounded-[3px] border border-line bg-subtle text-left text-[11px] leading-tight text-fg transition hover:z-20 hover:border-line-strong hover:bg-hover",
                      hot && "ring-1 ring-nu", selected === e.key && "z-20 ring-2 ring-fg/50")}
                    style={{
                      top: (e.start - START) * PX + 1, height: h - 2,
                      left: `calc(${(100 / e.lanes) * e.lane}% + 2px)`, width: `calc(${100 / e.lanes}% - 4px)`,
                    }}>
                    {/* Stripe split by category share, so mixed blocks show every category */}
                    <span className="flex w-[3px] shrink-0 flex-col">
                      {counts.map(([c, n]) => <span key={c} className={categoryStyle(c).bar} style={{ flexGrow: n }} />)}
                      {other > 0 && <span className={categoryStyle("").bar} style={{ flexGrow: other }} />}
                    </span>
                    <span className="min-w-0 flex-1 px-1.5 py-1">
                      <span className="flex items-center justify-between gap-1 font-semibold">
                        <span>{e.seq.code}</span><span className="tabular-nums text-muted">{e.rows.length}</span>
                      </span>
                      {h > 34 && <span className="block tabular-nums text-muted">{fmt(e.start)}–{fmt(e.end)}</span>}
                      {chipRows > 0 && (
                        <span className="mt-0.5 flex flex-wrap content-start gap-0.5 overflow-hidden" style={{ maxHeight: chipRows * 15 }}>
                          {e.rows.map((r) => (
                            <span key={r.section_id} className={cx("rounded-sm px-1 font-medium tabular-nums ring-1 ring-inset", categoryStyle(r.category).chip)}>
                              {r.course.replace("ECON ", "")}
                            </span>
                          ))}
                        </span>
                      )}
                    </span>
                  </button>
                );
              })}
            </div>
          ))}
        </div>
      </div>

      {selectedEv && (
        <div className="animate-fade-up mt-3 rounded-md border border-line">
          <div className="border-b border-line bg-subtle px-3 py-2 text-xs font-medium">
            Sequence {selectedEv.seq.code} · {selectedEv.seq.label} · {selectedEv.rows.length} Section{selectedEv.rows.length > 1 ? "s" : ""}
          </div>
          <div className="divide-y divide-line">
            {selectedEv.rows.map((r) => (
              <button key={r.section_id} onClick={() => onOpen(r.section_id)} className="flex w-full items-center gap-3 px-3 py-1.5 text-left text-[13px] hover:bg-hover">
                <CategoryDot category={r.category} />
                <span className="w-28 font-medium tabular-nums">{r.section_id}</span>
                <span className="flex-1 truncate text-muted">{r.title}</span>
                <span className="w-44 truncate">{r.instructor}</span>
                {locked.has(r.section_id) && <Lock className="h-3.5 w-3.5 text-amber-500" />}
                {(comments[r.section_id] ?? 0) > 0 && <span className="flex items-center gap-0.5 text-xs text-muted"><MessageSquare className="h-3.5 w-3.5" />{comments[r.section_id]}</span>}
                {flagged.has(r.section_id) && <Badge tone="red">Conflict</Badge>}
              </button>
            ))}
          </div>
        </div>
      )}
      {unplaced.length > 0 && (
        <p className="mt-3 text-xs text-muted">
          <span className="font-medium text-fg">Not on the Grid:</span>{" "}
          {unplaced.map((r) => `${r.section_id} (${r.sequence === "ASYNC" ? "online, asynchronous" : r.sequence.toLowerCase()})`).join(", ")}
        </p>
      )}
    </div>
  );
}
