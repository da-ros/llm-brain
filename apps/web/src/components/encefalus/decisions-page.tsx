import { useEffect, useState } from "react";
import { Link } from "@tanstack/react-router";
import { BrainCircuit, RotateCcw, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Notice,
  PageHeader,
  Panel,
  PanelTitle,
  PremiumNotice,
} from "@/components/encefalus/primitives";
import { useAccount } from "@/lib/account";

type Scenario = {
  id: string;
  title: string;
  outcome: string;
  assumptions: string[];
  severity: string;
};

type Simulation = {
  assumptions: string[];
  sources: string[];
  scenarios: Scenario[];
};

type Run = Simulation & {
  simulation_id: string;
  question: string;
  created_at: string;
};

const SLOTS = [
  { severity: "pessimistic", label: "Pessimistic", tone: "bg-risk/10 border-risk/25" },
  { severity: "baseline", label: "Baseline", tone: "bg-muted/40" },
  { severity: "optimistic", label: "Optimistic", tone: "bg-success/10 border-success/25" },
];

function authHeaders(): HeadersInit {
  const token = sessionStorage.getItem("access_token") ?? "";
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

async function readError(response: Response): Promise<string> {
  const body = await response.json().catch(() => ({}));
  if (typeof body?.detail === "string") return body.detail;
  if (response.status === 401 || response.status === 403)
    return "Sign in with a premium token to run a simulation.";
  return "The simulation could not be completed.";
}

export function DecisionsPage() {
  const account = useAccount();
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<Simulation | null>(null);
  const [runs, setRuns] = useState<Run[]>([]);
  const [activeRun, setActiveRun] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (account?.plan !== "premium") return;
    void loadRuns();
  }, [account?.plan]);

  async function loadRuns() {
    try {
      const response = await fetch("/api/simulations", { headers: authHeaders() });
      if (!response.ok) {
        setError(await readError(response));
        return;
      }
      const body = await response.json();
      setRuns((body.simulations ?? []) as Run[]);
    } catch {
      setError("Decisions is not reachable. Start the API router and sign in.");
    }
  }

  function openRun(run: Run) {
    setActiveRun(run.simulation_id);
    setQuestion(run.question);
    setResult({
      assumptions: run.assumptions ?? [],
      sources: run.sources ?? [],
      scenarios: run.scenarios ?? [],
    });
    setError("");
  }

  async function run() {
    const text = question.trim();
    if (!text || busy) return;
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/simulate", {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({ question: text }),
      });
      if (!response.ok) {
        setError(await readError(response));
        setBusy(false);
        return;
      }
      const body = await response.json();
      const saved: Run = {
        simulation_id: body.simulation_id || "",
        question: body.question || text,
        created_at: body.created_at || new Date().toISOString(),
        assumptions: body.assumptions ?? [],
        sources: body.sources ?? [],
        scenarios: body.scenarios ?? [],
      };
      setResult(saved);
      setActiveRun(saved.simulation_id);
      setRuns((current) => [
        saved,
        ...current.filter((item) => item.simulation_id !== saved.simulation_id),
      ]);
    } catch {
      setError("Decisions is not reachable. Start the API router and sign in.");
    }
    setBusy(false);
  }

  function reset() {
    setResult(null);
    setError("");
    setQuestion("");
    setActiveRun("");
  }

  if (account?.plan === "free") return <PremiumNotice title="Decision simulator" />;

  return (
    <main className="min-h-svh">
      <PageHeader
        eyebrow="Decision support"
        title="Decision simulator"
        description="Compare what-if pessimistic, baseline, and optimistic scenarios using explicit assumptions and evidence from your memories."
        action={
          <Button onClick={() => void run()} disabled={busy || !question.trim()}>
            <Sparkles />
            Run simulation
          </Button>
        }
      />
      <div className="p-5 sm:p-7">
        <label className="text-xs font-semibold" htmlFor="decision-question">
          What decision do you want to explore?
        </label>
        <textarea
          id="decision-question"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="Should I leave my job to start an independent consulting business?"
          className="mt-2 min-h-24 w-full resize-none rounded-lg border border-input bg-card p-4 text-lg font-medium outline-none focus:ring-1 focus:ring-ring"
        />
        {error && (
          <div className="mt-4">
            <Notice>{error}</Notice>
          </div>
        )}
        <Panel className="mt-6">
          <PanelTitle
            title="Past runs"
            aside={<span className="text-xs text-muted-foreground">{runs.length}</span>}
          />
          {runs.length === 0 ? (
            <p className="px-4 py-3 text-xs text-muted-foreground">No simulations yet.</p>
          ) : (
            <ul>
              {runs.map((run) => (
                <li
                  key={run.simulation_id || run.created_at}
                  className="border-t border-border first:border-0"
                >
                  <button
                    type="button"
                    onClick={() => openRun(run)}
                    className={`grid w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-3 px-4 py-3 text-left ${activeRun === run.simulation_id ? "bg-accent/60" : "hover:bg-muted/50"}`}
                  >
                    <span className="truncate text-sm font-medium">
                      {run.question || "Simulation"}
                    </span>
                    <span className="text-[11px] text-muted-foreground">
                      {formatWhen(run.created_at)}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Panel>
        <h2 className="mb-3 mt-6 text-xs font-semibold uppercase tracking-[.12em] text-muted-foreground">
          Scenarios
        </h2>
        <div className="grid gap-3 lg:grid-cols-3">
          {SLOTS.map((slot) => {
            const scenario = result?.scenarios.find(
              (item) => (item.severity || item.id).toLowerCase() === slot.severity,
            );
            return (
              <Panel key={slot.severity} className={slot.tone}>
                <div className="p-4">
                  <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                    {slot.label}
                  </p>
                  <h3 className="mt-1 text-sm font-bold">{scenario?.title || slot.label}</h3>
                  <p className="mt-3 text-xs leading-5 text-muted-foreground">
                    {scenario?.outcome || "Run a simulation to fill this case."}
                  </p>
                </div>
              </Panel>
            );
          })}
        </div>
        <div className="mt-6 grid gap-4 lg:grid-cols-2">
          <Panel>
            <PanelTitle title="Key assumptions" />
            <ul className="space-y-2 p-4 text-xs leading-5 text-muted-foreground">
              {(result?.assumptions.length
                ? result.assumptions
                : ["Assumptions appear here after a simulation."]
              ).map((item) => (
                <li key={item}>• {item}</li>
              ))}
            </ul>
          </Panel>
          <Panel>
            <PanelTitle title="Evidence from your memories" />
            <div className="grid gap-2 p-4 sm:grid-cols-3">
              {result?.sources.length ? (
                result.sources.map((source) => (
                  <a
                    key={source}
                    href={`/memory?file=${encodeURIComponent(source)}`}
                    className="rounded-md bg-muted p-3 text-left text-xs font-medium hover:bg-accent"
                  >
                    {source.split(/[/\\]/).pop()}
                    <span className="mt-1 block text-[10px] text-muted-foreground">
                      Open memory
                    </span>
                  </a>
                ))
              ) : (
                <p className="col-span-full whitespace-nowrap text-xs text-muted-foreground">
                  Memory references appear here after a simulation.
                </p>
              )}
            </div>
          </Panel>
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="outline" onClick={reset}>
            <RotateCcw />
            Reset
          </Button>
          <Button asChild>
            <Link to="/brain">
              <BrainCircuit />
              Ask Brain about result
            </Link>
          </Button>
        </div>
      </div>
    </main>
  );
}

function formatWhen(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}
