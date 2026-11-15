// Planning settings (persisted in the Zustand plan store, shared by every view).
import { RotateCcw } from "lucide-react";
import { useState } from "react";
import { usePlan } from "../store/plan";
import { useFlash } from "../store/ui";
import { Button, Field, Panel, Switch, cx, inputCls } from "./ui";

export function TermSelect({ compact }: { compact?: boolean }) {
  const meta = usePlan((s) => s.meta);
  const term = usePlan((s) => s.settings.target_term);
  const update = usePlan((s) => s.update);
  return (
    <select aria-label="Target Semester" className={cx(inputCls, compact && "h-7 text-xs")} value={term}
      onChange={(e) => update({ target_term: e.target.value })}>
      {!meta && <option>{term || "Loading…"}</option>}
      {meta && (
        <>
          <optgroup label="Upcoming (Forecast)">{meta.terms.upcoming.map((t) => <option key={t} value={t}>{t}</option>)}</optgroup>
          <optgroup label="Past Terms (Back-Test)">{meta.terms.historical.map((t) => <option key={t} value={t}>{t}</option>)}</optgroup>
        </>
      )}
    </select>
  );
}

const GROWTH = { min: 0.85, max: 1.5, step: 0.05, ticks: [0.85, 1.0, 1.25, 1.5] };
/** Thumb diameter in px — must match `--thumb` in index.css (.range-nu). */
const THUMB = 14;

/** Horizontal position of a value's thumb center, matching how browsers lay out a range thumb. */
const thumbLeft = (v: number) => {
  const pct = (v - GROWTH.min) / (GROWTH.max - GROWTH.min);
  return `calc(${THUMB / 2}px + ${pct} * (100% - ${THUMB}px))`;
};

/**
 * Enrollment growth slider. Tick labels are placed at their true values using the
 * same geometry as the thumb, so 1.00× sits exactly under the thumb at 1.00×
 * (it is ~23% along the 0.85–1.50 track, not the midpoint).
 */
function GrowthSlider({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  const v = Math.min(GROWTH.max, Math.max(GROWTH.min, Math.round(value * 100) / 100));
  return (
    <div className="mt-2">
      <input type="range" className="range-nu" aria-label="Enrollment Growth Multiplier" aria-valuetext={`${v.toFixed(2)} times`}
        min={GROWTH.min} max={GROWTH.max} step={GROWTH.step} value={v}
        style={{ ["--fill" as string]: thumbLeft(v) }}
        // Round away floating-point drift (0.85 + 4 × 0.05 = 1.0500000000000003)
        onChange={(e) => onChange(Math.round(Number(e.target.value) * 100) / 100)} />
      <div className="relative mt-1 h-5 text-[11px] tabular-nums text-faint" aria-hidden>
        {GROWTH.ticks.map((t) => (
          <span key={t} className="absolute top-0 flex -translate-x-1/2 flex-col items-center" style={{ left: thumbLeft(t) }}>
            <span className={cx("h-1 w-px", t === 1 ? "bg-fg/60" : "bg-line-strong")} />
            <span className={cx(t === 1 && "font-medium text-muted", Math.abs(t - v) < 0.001 && "text-fg")}>{t.toFixed(2)}×</span>
          </span>
        ))}
      </div>
    </div>
  );
}

function NumberField({ label, value, min, max, step = 1, onChange, hint }: {
  label: string; value: number; min: number; max: number; step?: number; onChange: (v: number) => void; hint?: string;
}) {
  return (
    <Field label={label} hint={hint}>
      <input type="number" className={inputCls + " tabular-nums"} value={value} min={min} max={max} step={step}
        onChange={(e) => { const v = Number(e.target.value); if (!Number.isNaN(v)) onChange(Math.min(max, Math.max(min, v))); }} />
    </Field>
  );
}

export function SettingsPanel({ mode, defaultOpen = true }: { mode: "demand" | "schedule"; defaultOpen?: boolean }) {
  const s = usePlan((st) => st.settings);
  const u = usePlan((st) => st.update);
  const reset = usePlan((st) => st.reset);
  const [open, setOpen] = useState(defaultOpen);
  const flash = useFlash();
  return (
    <Panel className={flash("settings")} title="Planning Settings" description="Saved in this browser and shared across Demand, Schedule and Conflicts."
      actions={<>
        <Button size="sm" variant="ghost" icon={<RotateCcw className="h-3.5 w-3.5" />} onClick={reset}>Defaults</Button>
        <Button size="sm" onClick={() => setOpen(!open)}>{open ? "Collapse" : "Expand"}</Button>
      </>}
      bodyClass={open ? "" : "hidden"}>
      <div className="grid gap-x-5 gap-y-4 md:grid-cols-2 xl:grid-cols-4">
        <Field label="Target Semester" hint="Upcoming terms forecast; past terms back-test."><TermSelect /></Field>
        <Field label={<span className="flex justify-between">Enrollment Growth Multiplier <span className="tabular-nums text-muted">{s.growth_multiplier.toFixed(2)}×</span></span>}
          hint="Scales projected demand, not section caps.">
          <GrowthSlider value={s.growth_multiplier} onChange={(v) => u({ growth_multiplier: v })} />
        </Field>
        {mode === "demand" ? (
          <>
            <NumberField label="History Window" value={s.history_window} min={1} max={5} onChange={(v) => u({ history_window: v })}
              hint="Prior Fall-only or Spring-only terms, recency-weighted." />
            <NumberField label="Minimum Elective Enrollment" value={s.min_elective_demand} min={0} max={40}
              onChange={(v) => u({ min_elective_demand: v })} hint="Electives below this aren't planned." />
            <NumberField label="Large Lecture Cap" value={s.large_lecture_cap} min={100} max={300} step={10}
              onChange={(v) => u({ large_lecture_cap: v })} hint="Principles lectures, 100–200+." />
            <NumberField label="Small Section Cap" value={s.small_section_cap} min={30} max={60}
              onChange={(v) => u({ small_section_cap: v })} hint="Typical small classes, 40–45." />
            <NumberField label="Remote Section Cap" value={s.virtual_cap} min={10} max={25}
              onChange={(v) => u({ virtual_cap: v })} hint="Hard limit of 25." />
            <NumberField label="Recitation Cap" value={s.recitation_cap} min={15} max={60}
              onChange={(v) => u({ recitation_cap: v })} hint="Students per weekly 65-min recitation." />
            <div className="flex items-end pb-1">
              <Switch checked={s.apply_trend} onChange={(v) => u({ apply_trend: v })} label="Apply Historical Trend (±10%/yr)" />
            </div>
          </>
        ) : (
          <>
            <NumberField label="Recitations per Leader" value={s.recitation_leader_load} min={1} max={10}
              onChange={(v) => u({ recitation_leader_load: v })} hint="Default when there's no history." />
            <div className="flex flex-col justify-end gap-2.5 pb-1 xl:col-span-1">
              <Switch checked={s.history_fallback} onChange={(v) => u({ history_fallback: v })} label="Use Teaching History Without a Form" />
              <Switch checked={s.force_fill_core} onChange={(v) => u({ force_fill_core: v })} label="Force-Fill Unstaffed Core" />
            </div>
          </>
        )}
      </div>
    </Panel>
  );
}
