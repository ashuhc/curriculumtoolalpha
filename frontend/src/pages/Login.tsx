import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { api } from "../api";
import { Alert, Button, Field, inputCls } from "../components/ui";
import { useAuth } from "../store/auth";

const DEMO = [
  { label: "Scheduler", email: "admin@northeastern.edu", password: "econpassword123" },
  { label: "Second scheduler", email: "scheduler2@northeastern.edu", password: "scheduler123" },
  { label: "Faculty", email: "m.stone@northeastern.edu", password: "faculty123" },
];

export default function Login() {
  const { user, signIn, expired } = useAuth();
  const navigate = useNavigate();
  const from = (useLocation().state as { from?: string } | null)?.from ?? "/";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  if (user) return <Navigate to={from} replace />;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await api.login(email, password);
      signIn(r.token, r.user);
      navigate(from, { replace: true });
    } catch (x) { setError((x as Error).message); } finally { setBusy(false); }
  };

  return (
    <div className="mx-auto mt-10 max-w-sm">
      <div className="mb-6">
        <div className="mb-4 flex h-9 w-9 items-center justify-center rounded bg-nu text-xs font-bold text-white">NU</div>
        <h1 className="text-xl font-semibold tracking-tight">Sign in</h1>
        <p className="mt-1 text-[13px] text-muted">Faculty submit teaching preferences; schedulers edit, lock and publish the master schedule.</p>
      </div>
      {expired && <div className="mb-4"><Alert tone="warning">Your session expired. Please sign in again.</Alert></div>}
      <form onSubmit={submit} className="space-y-4 rounded-lg border border-line bg-surface p-5">
        <Field label="Email"><input className={inputCls} type="email" autoComplete="username" autoFocus value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
        <Field label="Password"><input className={inputCls} type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} /></Field>
        {error && <Alert tone="error">{error}</Alert>}
        <Button variant="primary" type="submit" className="w-full" loading={busy} disabled={!email || !password}>Sign in</Button>
      </form>
      {import.meta.env.DEV && (
        <div className="mt-5 rounded-lg border border-dashed border-line-strong p-4">
          <div className="mb-2 text-xs font-medium text-muted">Local demo accounts (seeded by seed_db.py)</div>
          <div className="space-y-1">
            {DEMO.map((d) => (
              <button key={d.email} type="button" onClick={() => { setEmail(d.email); setPassword(d.password); }}
                className="flex w-full items-center justify-between rounded px-2 py-1 text-left text-xs hover:bg-hover">
                <span className="font-medium">{d.label}</span><span className="text-muted">{d.email}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
