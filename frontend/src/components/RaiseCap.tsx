// Raise Section Cap: resolve "Demand Over Capacity" by raising seat limits on a course's existing
// sections. Each change is saved as a Manual Edit (cap override) that Revert restores.
import { useEffect, useMemo, useState } from "react";
import { api, type ScheduleResponse } from "../api";
import { useAuth } from "../store/auth";
import { useDemand } from "../store/demand";
import { useHistory } from "../store/history";
import { usePlan } from "../store/plan";
import { useSchedule } from "../store/schedule";
import { useUI } from "../store/ui";
import { Alert, Badge, Button, Modal, cx, inputBase } from "./ui";

const REMOTE_CAP = 25;
const MAX_CAP = 300;

export function RaiseCapModal({ open, onClose, data, code, remote }: {
  open: boolean; onClose: () => void; data: ScheduleResponse; code: number | null; remote: boolean;
}) {
  const settings = usePlan((s) => s.settings);
  const success = useUI((s) => s.success);
  const me = useAuth((s) => s.user);
  const [caps, setCaps] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const sections = useMemo(() => (code === null ? [] : data.master.filter((r) =>
    r.course === `ECON ${code}` && r.component === "Lecture" && r.modality.startsWith("Online") === remote)), [data, code, remote]);
  const gap = data.capacity_gaps.find((g) => g.code === code && g.virtual === remote);
  const projected = gap?.projected ?? sections.reduce((n, r) => n + r.projected_enrollment, 0);
  const lockedBy = (id: string) => { const l = data.locks.find((x) => x.section_id === id); return l && l.user_id !== me?.id ? l.user_name : null; };

  // Start from the current caps each time the dialog opens
  useEffect(() => {
    if (!open) return;
    setError(null); setBusy(false);
    setCaps(Object.fromEntries(sections.map((r) => [r.section_id, String(r.section_cap)])));
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  const limit = remote ? REMOTE_CAP : MAX_CAP;
  const parsed = sections.map((r) => ({ row: r, value: Number(caps[r.section_id]), raw: caps[r.section_id] ?? "" }));
  const invalid = parsed.filter((p) => !Number.isInteger(p.value) || p.value < 1 || p.value > limit);
  const changed = parsed.filter((p) => !invalid.includes(p) && p.value !== p.row.section_cap);
  // Invalid entries count as the current cap so the summary never promises seats that can't be saved
  const newSeats = parsed.reduce((n, p) => n + (invalid.includes(p) ? p.row.section_cap : p.value), 0);
  const excess = Math.max(0, projected - newSeats);

  async function save() {
    if (!changed.length || invalid.length) return;
    setBusy(true); setError(null);
    const done: string[] = [];
    try {
      // One Undo step for the whole dialog, even when several caps change
      await useHistory.getState().record("Raise Section Cap", settings.target_term, changed.map((p) => p.row.section_id), async () => {
        for (const p of changed) {
          await api.setOverride({ term: settings.target_term, section_id: p.row.section_id, cap: p.value });
          done.push(`${p.row.section_id}: ${p.row.section_cap} → ${p.value}`);
        }
      }, `ECON ${code}${remote ? " (Remote)" : ""} · ${changed.map((p) => `${p.row.section_id} → ${p.value}`).join(", ")}`);
      await useSchedule.getState().fetch(settings, { silent: true });
      useDemand.getState().refresh();
      success(excess ? "Section caps raised" : "Section caps raised · demand fully seated", done.join(" · "), changed.map((p) => `section:${p.row.section_id}`));
      onClose();
    } catch (e) {
      if (done.length) await useSchedule.getState().fetch(settings, { silent: true });
      setError(`${(e as Error).message}${done.length ? ` (saved: ${done.join(", ")})` : ""}`);
    } finally { setBusy(false); }
  }

  const label = code === null ? "" : `ECON ${code}${remote ? " (Remote)" : ""}`;
  return (
    <Modal open={open} onClose={() => !busy && onClose()} size="lg" title={`Raise Section Cap · ${label}`}
      footer={<>
        <Button variant="ghost" onClick={onClose} disabled={busy}>Cancel</Button>
        <Button variant="primary" loading={busy} disabled={!changed.length || invalid.length > 0} onClick={save}>
          Save {changed.length > 1 ? `${changed.length} New Caps` : "New Cap"}
        </Button>
      </>}>
      <div className="space-y-4 text-[13px]">
        <div className="grid grid-cols-3 gap-2">
          {[["Projected Students", projected], ["Seats After Change", newSeats], [excess ? "Still Unseated" : "Unseated", excess]].map(([k, v]) => (
            <div key={k as string} className="rounded-md border border-line bg-subtle px-3 py-2">
              <div className="text-[11px] font-medium text-muted">{k}</div>
              <div className={cx("text-lg font-semibold tabular-nums", k === "Still Unseated" && "text-amber-600 dark:text-amber-400",
                k === "Unseated" && "text-emerald-600 dark:text-emerald-400")}>{v}</div>
            </div>
          ))}
        </div>
        <p className="text-muted">
          Type the new seat capacity for any section. Changed sections are tagged <span className="font-medium text-fg">Manual Edit</span> on the
          Term Schedule; <span className="font-medium text-fg">Revert</span> restores the default cap.
          {remote && <> Remote sections are capped at {REMOTE_CAP}.</>}
        </p>
        <div className="overflow-hidden rounded-md border border-line">
          <table className="w-full text-[13px]">
            <thead className="bg-subtle text-[11px] text-muted">
              <tr><th className="px-3 py-2 text-left font-medium">Section</th><th className="px-3 py-2 text-left font-medium">Instructor</th>
                <th className="px-3 py-2 text-right font-medium">Current Cap</th><th className="px-3 py-2 text-right font-medium">Projected</th>
                <th className="px-3 py-2 text-right font-medium">New Seat Capacity</th></tr>
            </thead>
            <tbody>
              {parsed.map(({ row, raw, value }) => {
                const by = lockedBy(row.section_id);
                const bad = invalid.some((p) => p.row.section_id === row.section_id);
                return (
                  <tr key={row.section_id} className="border-t border-line">
                    <td className="whitespace-nowrap px-3 py-2 font-medium tabular-nums">
                      {row.section_id}{data.overridden.includes(row.section_id) && <Badge tone="amber" className="ml-1.5">Manual Edit</Badge>}
                    </td>
                    <td className="px-3 py-2 text-muted">{row.instructor}</td>
                    <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums text-muted">{row.section_cap} Seats</td>
                    <td className="px-3 py-2 text-right tabular-nums text-muted">{row.projected_enrollment}</td>
                    <td className="px-3 py-2 text-right">
                      <input type="number" min={1} max={limit} inputMode="numeric" aria-label={`New Seat Capacity for ${row.section_id}`}
                        disabled={!!by || busy} title={by ? `Locked by ${by}` : undefined} value={raw}
                        onChange={(e) => setCaps((c) => ({ ...c, [row.section_id]: e.target.value }))}
                        className={cx(inputBase, "h-7 w-24 text-right tabular-nums", bad && "border-nu-text", value !== row.section_cap && !bad && "border-amber-500/60")} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {!sections.length && <Alert tone="info">No sections of {label} are on the Term Schedule yet. Use Add Section instead.</Alert>}
        {invalid.length > 0 && <Alert tone="error">Enter a whole number from 1 to {limit} for {invalid.map((p) => p.row.section_id).join(", ")}.</Alert>}
        {error && <Alert tone="error">{error}</Alert>}
      </div>
    </Modal>
  );
}
