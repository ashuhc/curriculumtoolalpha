// Searchable course picker (code, level such as "3000s", title, or topic keyword).
import { ChevronsUpDown, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import type { Course } from "../api";
import { cx, inputCls } from "./ui";

export function matchCourse(c: Course, q: string) {
  const s = q.trim().toLowerCase().replace(/^econ\s*/, "");
  if (!s) return true;
  if (/^\d{1,4}$/.test(s)) return String(c.code).startsWith(s);
  if (/^\d000s?$/.test(s)) return c.level === Number(s.slice(0, 4));
  return `${c.code} ${c.title} ${c.description}`.toLowerCase().includes(s);
}

export function CourseSelect({ courses, value, onChange, exclude = [], placeholder = "Search by code, title or topic" }: {
  courses: Course[]; value: number | null; onChange: (code: number | null) => void; exclude?: number[]; placeholder?: string;
}) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [hi, setHi] = useState(0);
  const box = useRef<HTMLDivElement>(null);
  const selected = courses.find((c) => c.code === value) ?? null;
  const options = useMemo(() => courses.filter((c) => !exclude.includes(c.code) && matchCourse(c, q)).slice(0, 50), [courses, exclude, q]);

  useEffect(() => {
    const close = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);
  useEffect(() => setHi(0), [q]);
  const pick = (c: Course | null) => { onChange(c ? c.code : null); setQ(""); setOpen(false); };

  return (
    <div ref={box} className="relative">
      <div className="relative">
        <input className={cx(inputCls, "pr-14")} value={open ? q : selected ? `ECON ${selected.code} · ${selected.title}` : ""}
          placeholder={placeholder} onFocus={() => setOpen(true)} onChange={(e) => { setQ(e.target.value); setOpen(true); }}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") { e.preventDefault(); setHi((h) => Math.min(h + 1, options.length - 1)); }
            if (e.key === "ArrowUp") { e.preventDefault(); setHi((h) => Math.max(h - 1, 0)); }
            if (e.key === "Enter" && open && options[hi]) { e.preventDefault(); pick(options[hi]); }
            if (e.key === "Escape") setOpen(false);
          }} />
        <div className="absolute inset-y-0 right-2 flex items-center gap-1 text-faint">
          {selected && <button type="button" aria-label="Clear" onClick={() => pick(null)} className="hover:text-fg"><X className="h-3.5 w-3.5" /></button>}
          <ChevronsUpDown className="h-3.5 w-3.5" />
        </div>
      </div>
      {open && (
        <ul className="absolute z-30 mt-1 max-h-72 w-full overflow-auto rounded-md border border-line bg-surface py-1 shadow-lg">
          {options.length === 0 && <li className="px-3 py-2 text-[13px] text-muted">No matching undergraduate courses</li>}
          {options.map((c, i) => (
            <li key={c.code} onMouseDown={(e) => { e.preventDefault(); pick(c); }} onMouseEnter={() => setHi(i)}
              className={cx("cursor-pointer px-3 py-1.5", i === hi && "bg-hover")}>
              <div className="flex items-center justify-between gap-3 text-[13px]">
                <span className="truncate"><span className="font-medium tabular-nums">ECON {c.code}</span> <span className="text-muted">·</span> {c.title}</span>
                <span className="shrink-0 text-[11px] text-faint">{c.category}</span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
