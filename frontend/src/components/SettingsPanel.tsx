// Planning settings (persisted in the Zustand plan store, shared by every view).
import { RotateCcw } from "lucide-react";
import { useState } from "react";
import { usePlan } from "../store/plan";
import { Button, Field, Panel, Switch, cx, inputCls } from "./ui";

export function TermSelect({ compact }: { compact?: boolean }) {
  const meta = usePlan((s) => s.meta);
  const term = usePlan((s) => s.settings.target_term);
  const update = usePlan((s) => s.update);
  return (
    <select aria-label="Target semester" className={cx(inputCls, compact && "h-7 text-xs")} value={term}
      onChange={(e) => update({ target_term: e.target.value })}>
      {!meta && <option>{term || "Loading…"}</option>}
      {meta && (
        <>
          <optgroup label="Upcoming (forecast)">{meta.terms.upcoming.map((t) => <option key={t} value={t}>{t}</option>)}</optgroup>
          <optgroup label="Past terms (back-test)">{meta.terms.historical.map((t) => <option key={t} value={t}>{t}</option>)}</optgroup>
        </>
      )}
    </select>
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
  return (
    <Panel title="Planning settings" description="Saved in this browser and shared across Demand, Schedule and Conflicts."
      actions={<>
        <Button size="sm" variant="ghost" icon={<RotateCcw className="h-3.5 w-3.5" />} onClick={reset}>Defaults</Button>
        <Button size="sm" onClick={() => setOpen(!open)}>{open ? "Collapse" : "Expand"}</Button>
      </>}
      bodyClass={open ? "" : "hidden"}>
      <div className="grid gap-x-5 gap-y-4 md:grid-cols-2 xl:grid-cols-4">
        <Field label="Target semester" hint="Upcoming terms forecast; past terms back-test."><TermSelect /></Field>
        <Field label={<span className="flex justify-between">Enrollment growth <span className="tabular-nums text-muted">{s.growth_multiplier.toFixed(2)}×</span></span>}
          hint="Scales projected demand, not section caps.">
          <input type="range" className="mt-2 w-full" min={0.85} max={1.5} step={0.05} value={s.growth_multiplier}
            onChange={(e) => u({ growth_multiplier: Number(e.target.value) })} />
          <div className="flex justify-between text-[11px] text-faint"><span>0.85×</span><span>1.00×</span><span>1.50×</span></div>
        </Field>
        {mode === "demand" ? (
          <>
            <NumberField label="History window" value={s.history_window} min={1} max={5} onChange={(v) => u({ history_window: v })}
              hint="Prior Fall-only or Spring-only terms, recency-weighted." />
            <NumberField label="Minimum elective enrollment" value={s.min_elective_demand} min={0} max={40}
              onChange={(v) => u({ min_elective_demand: v })} hint="Electives below this aren't planned." />
            <NumberField label="Large lecture cap" value={s.large_lecture_cap} min={100} max={300} step={10}
              onChange={(v) => u({ large_lecture_cap: v })} hint="Principles lectures, 100–200+." />
            <NumberField label="Small section cap" value={s.small_section_cap} min={30} max={60}
              onChange={(v) => u({ small_section_cap: v })} hint="Typical small classes, 40–45." />
            <NumberField label="Remote section cap" value={s.virtual_cap} min={10} max={25}
              onChange={(v) => u({ virtual_cap: v })} hint="Hard limit of 25." />
            <NumberField label="Recitation cap" value={s.recitation_cap} min={15} max={60}
              onChange={(v) => u({ recitation_cap: v })} hint="Students per weekly 65-min recitation." />
            <div className="flex items-end pb-1">
              <Switch checked={s.apply_trend} onChange={(v) => u({ apply_trend: v })} label="Apply historical trend (±10%/yr)" />
            </div>
          </>
        ) : (
          <>
            <NumberField label="Recitations per leader" value={s.recitation_leader_load} min={1} max={10}
              onChange={(v) => u({ recitation_leader_load: v })} hint="Default when there's no history." />
            <div className="flex flex-col justify-end gap-2.5 pb-1 xl:col-span-1">
              <Switch checked={s.history_fallback} onChange={(v) => u({ history_fallback: v })} label="Use teaching history without a form" />
              <Switch checked={s.force_fill_core} onChange={(v) => u({ force_fill_core: v })} label="Force-fill unstaffed core" />
            </div>
          </>
        )}
      </div>
    </Panel>
  );
}
