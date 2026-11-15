import { useEffect, useState } from "react";
import { BrainCircuit, Check, Database, MessageSquare, Smartphone, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Metric,
  Notice,
  PageHeader,
  Panel,
  PanelTitle,
  PremiumNotice,
} from "@/components/encefalus/primitives";
import { useAccount } from "@/lib/account";

type Batch = { id: string; status: string; items: number; needed: number };
type Job = { id: string; status: string; phase: string; model_version: string };
type Cycle = { id: string; version: string; date: string; signals: number; status: string };
type Learning = {
  interactions: number;
  memories: number;
  needed: number;
  model_tag: string;
  batch: Batch | null;
  job: Job | null;
  learned: string[];
  cycles: Cycle[];
};

type StepState = "done" | "active" | "wait";
type Pack = { status: string; phase: string; error: string; ready: boolean; adapter: boolean };

const EMPTY: Learning = {
  interactions: 0,
  memories: 0,
  needed: 10,
  model_tag: "",
  batch: null,
  job: null,
  learned: [],
  cycles: [],
};

const EMPTY_PACK: Pack = { status: "idle", phase: "", error: "", ready: false, adapter: false };

const PHASE_LABEL: Record<string, string> = {
  preparing: "Preparing",
  tools: "Getting the converter",
  base: "Getting the base model",
  converting: "Converting the adapter",
  merging: "Merging the adapter",
  quantizing: "Quantizing the merged model",
  completed: "File is on this Mac",
  failed: "Merge failed",
};

function authHeaders(json = false): HeadersInit {
  const token = sessionStorage.getItem("access_token") ?? "";
  return {
    ...(json ? { "Content-Type": "application/json" } : {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

async function readError(response: Response, fallback: string): Promise<string> {
  const body = await response.json().catch(() => ({}));
  if (typeof body?.detail === "string") return body.detail;
  if (response.status === 401 || response.status === 403) {
    return "Sign in with a premium token to see learning.";
  }
  return fallback;
}

export function LearningPage() {
  const account = useAccount();
  const [view, setView] = useState<Learning>(EMPTY);
  const [pack, setPack] = useState<Pack>(EMPTY_PACK);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void load();
  }, []);

  useEffect(() => {
    const training = view.job?.status === "submitted" || view.job?.status === "in_progress";
    const publishing = pack.status === "running" || pack.status === "submitted";
    if (!training && !publishing) return;
    const handle = window.setInterval(() => void load(), 4000);
    return () => window.clearInterval(handle);
  }, [view.job?.status, pack.status]);

  async function load() {
    try {
      const response = await fetch("/api/learning", { headers: authHeaders() });
      if (!response.ok) {
        setError(await readError(response, "Learning could not be loaded."));
        return;
      }
      const body = await response.json();
      setView({
        interactions: body.interactions ?? 0,
        memories: body.memories ?? 0,
        needed: body.needed ?? 10,
        model_tag: body.model_tag ?? "",
        batch: body.batch ?? null,
        job: body.job ?? null,
        learned: body.learned ?? [],
        cycles: body.cycles ?? [],
      });
      setError("");
      const packResponse = await fetch("/api/on-device-pack", { headers: authHeaders() });
      if (packResponse.ok) {
        const packBody = await packResponse.json();
        setPack({
          status: packBody.status ?? "idle",
          phase: packBody.phase ?? "",
          error: packBody.error ?? "",
          ready: Boolean(packBody.ready),
          adapter: Boolean(packBody.adapter),
        });
      }
    } catch {
      setError("Learning is not reachable. Start the API router and sign in.");
    }
  }

  async function train() {
    if (!view.batch || view.batch.status !== "ready" || busy) return;
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/finetune", {
        method: "POST",
        headers: authHeaders(true),
        body: JSON.stringify({ batch_id: view.batch.id }),
      });
      if (!response.ok) {
        setError(await readError(response, "Fine-tune could not be started."));
        setBusy(false);
        return;
      }
      await load();
    } catch {
      setError("Learning is not reachable. Start the API router and sign in.");
    }
    setBusy(false);
  }

  const ready = view.batch?.status === "ready";
  const training = view.job?.status === "submitted" || view.job?.status === "in_progress";
  const publishing = pack.status === "running" || pack.status === "submitted";

  async function publish() {
    if (!pack.adapter || busy || publishing) return;
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/on-device-pack", {
        method: "POST",
        headers: authHeaders(),
      });
      if (!response.ok) {
        setError(await readError(response, "The merge could not be started."));
        setBusy(false);
        return;
      }
      setPack((current) => ({ ...current, status: "running", phase: "preparing", error: "" }));
      await load();
    } catch {
      setError("Learning is not reachable. Start the API router and sign in.");
    }
    setBusy(false);
  }

  const checks = trainingSteps(view, pack);
  if (account?.plan === "free") return <PremiumNotice title="Your symbiotic learning loop" />;

  return (
    <main className="min-h-svh">
      <PageHeader
        eyebrow="Personalization"
        title="Your symbiotic learning loop"
        description="Encefalus learns from approved signals to become more helpful, personal, and aligned with your goals."
        action={
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
            <div className="flex flex-col items-center gap-1">
              <span className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                1
              </span>
              <Button
                disabled={!ready || busy || training || publishing}
                onClick={() => void train()}
              >
                <BrainCircuit />
                {busy && !publishing ? "Starting…" : "Fine-tune my Brain"}
              </Button>
            </div>
            <span className="h-px w-10 bg-border" />
            <div className="flex flex-col items-center gap-1">
              <span className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                2
              </span>
              <Button
                variant="outline"
                disabled={!pack.adapter || busy || training || publishing}
                onClick={() => void publish()}
              >
                <BrainCircuit />
                {publishing ? "Merging…" : "Merge into base model"}
              </Button>
              {mergeNote(pack) ? (
                <span className="max-w-36 text-center text-[10px] leading-3 text-muted-foreground">
                  {mergeNote(pack)}
                </span>
              ) : null}
            </div>
            <span className="h-px w-10 bg-border" />
            <div className="flex flex-col items-center gap-1">
              <span className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                3
              </span>
              <span
                className={`inline-flex h-9 items-center gap-2 rounded-md border px-3 text-sm ${
                  pack.ready
                    ? "border-border text-foreground"
                    : "border-border text-muted-foreground"
                }`}
              >
                <Smartphone />
                Reinstall on iPhone
              </span>
            </div>
          </div>
        }
      />
      <div className="p-5 sm:p-7">
        {error && (
          <div className="mb-4">
            <Notice>{error}</Notice>
          </div>
        )}
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          <Metric
            label="Recent interactions"
            value={String(view.interactions)}
            note="Premium turns stored"
            icon={<MessageSquare className="size-4" />}
          />
          <Metric
            label="New memories"
            value={String(view.memories)}
            note="Files in memory"
            icon={<Database className="size-4" />}
          />
          <Panel className="min-h-28 p-4">
            <div className="flex items-center justify-between text-xs font-medium text-muted-foreground">
              <span>On-device model</span>
              <Sparkles className="size-4" />
            </div>
            <p className="mt-3 break-all font-mono text-sm font-semibold text-foreground">
              {view.model_tag || "No tag yet"}
            </p>
            <p className="mt-1 text-[11px] text-muted-foreground">
              {view.model_tag ? "Premium on device" : "The next fine-tune writes a new tag"}
            </p>
          </Panel>
        </div>
        <div className="mt-5 grid gap-4 xl:grid-cols-2">
          <Panel>
            <PanelTitle title="Training status" />
            <div className="space-y-6 p-5">
              <Checklist title="Batch readiness" steps={checks.ready} />
              <Checklist title="Fine-tune" steps={checks.train} />
              <Checklist title="Merge" steps={checks.phone} />
            </div>
          </Panel>
          <Panel>
            <PanelTitle title="What your Brain learned" />
            {view.learned.length === 0 ? (
              <p className="p-5 text-xs leading-5 text-muted-foreground">
                No fine-tuned model has learned from your turns yet.
              </p>
            ) : (
              <ul className="space-y-3 p-5 text-xs leading-5">
                {view.learned.map((line) => (
                  <li key={line} className="flex gap-2">
                    <span className="mt-2 size-1.5 shrink-0 rounded-full bg-primary" />
                    {line}
                  </li>
                ))}
              </ul>
            )}
            <div className="px-5 pb-5">
              <Notice>These are turns the previous on-device model was trained on.</Notice>
            </div>
          </Panel>
        </div>
        <Panel className="mt-5">
          <PanelTitle title="Previous personalization cycles" />
          {view.cycles.length === 0 ? (
            <p className="px-4 py-3 text-xs text-muted-foreground">No fine-tune runs yet.</p>
          ) : (
            <div className="overflow-x-auto">
              <div className="grid min-w-[32rem] grid-cols-4 gap-3 px-4 py-3 text-[10px] font-semibold uppercase text-muted-foreground">
                <span>Version</span>
                <span>Date</span>
                <span>Signals</span>
                <span>Status</span>
              </div>
              {view.cycles.map((cycle) => (
                <div
                  key={cycle.id || `${cycle.version}-${cycle.date}`}
                  className="grid min-w-[32rem] grid-cols-4 gap-3 border-t border-border px-4 py-3 text-xs"
                >
                  <span className="truncate font-mono">{cycle.version || "—"}</span>
                  <span>{formatDate(cycle.date)}</span>
                  <span>{cycle.signals}</span>
                  <span>{statusLabel(cycle.status)}</span>
                </div>
              ))}
            </div>
          )}
        </Panel>
      </div>
    </main>
  );
}

function Checklist({
  title,
  steps,
}: {
  title: string;
  steps: { title: string; note: string; state: StepState }[];
}) {
  return (
    <div>
      <h3 className="text-[10px] font-semibold uppercase tracking-[.12em] text-muted-foreground">
        {title}
      </h3>
      <ol className="mt-3">
        {steps.map((step, index) => (
          <li key={step.title} className="grid grid-cols-[24px_minmax(0,1fr)] gap-3">
            <div className="flex flex-col items-center">
              <span
                className={`grid size-5 place-items-center rounded-full border ${
                  step.state === "done"
                    ? "border-success bg-success text-primary-foreground"
                    : step.state === "active"
                      ? "border-warning bg-warning/20"
                      : "border-border bg-background"
                }`}
              >
                {step.state === "done" && <Check className="size-3" />}
              </span>
              {index < steps.length - 1 && <span className="h-11 w-px bg-border" />}
            </div>
            <div className="pb-3">
              <p className="text-xs font-semibold">{step.title}</p>
              <p className="mt-1 text-[10px] leading-4 text-muted-foreground">{step.note}</p>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}

function mergeNote(pack: Pack) {
  if (pack.status === "failed") return pack.error || PHASE_LABEL.failed;
  if (pack.status === "running" || pack.status === "submitted") {
    return PHASE_LABEL[pack.phase] || "Merging";
  }
  return "";
}

function trainingSteps(view: Learning, pack: Pack) {
  const items = view.batch?.items ?? 0;
  const needed = view.batch?.needed ?? view.needed;
  const status = view.batch?.status ?? "";
  const raw = view.job?.phase || "";
  const phase = raw === "in_progress" ? "training" : raw;
  const started = Boolean(view.job);
  const past = (name: string) => rank(phase) > rank(name);
  return {
    ready: [
      {
        title: "Recent interactions",
        note: `${view.interactions} recorded`,
        state: view.interactions > 0 ? "done" : "wait",
      },
      {
        title: "Eligible turns",
        note: items >= needed ? `${items} collected` : `${items} collected, ${needed} to start`,
        state: items > 0 ? "done" : "wait",
      },
      {
        title: "Batch ready",
        note:
          status === "ready"
            ? "Ready to fine-tune"
            : items > 0
              ? "Still collecting"
              : "No open batch",
        state: status === "ready" || started ? "done" : "wait",
      },
    ] satisfies { title: string; note: string; state: StepState }[],
    train: [
      {
        title: "Job submitted",
        note: started ? "The batch was sent to fine-tune" : "Starts when you fine-tune",
        state: !started ? "wait" : phase === "submitted" ? "active" : "done",
      },
      {
        title: "Training set prepared",
        note:
          phase === "preparing"
            ? "Reading the batch"
            : past("preparing")
              ? "Examples are ready"
              : "Waiting",
        state: phase === "preparing" ? "active" : past("preparing") ? "done" : "wait",
      },
      {
        title: "LoRA training",
        note:
          phase === "training"
            ? "Usually a couple of hours"
            : past("training")
              ? "Training finished"
              : "Usually a couple of hours",
        state: phase === "training" ? "active" : past("training") ? "done" : "wait",
      },
      {
        title: "On-device tag saved",
        note:
          phase === "completed"
            ? view.job?.model_version || "Tag written"
            : "Written when training finishes",
        state: phase === "completed" ? "done" : "wait",
      },
    ] satisfies { title: string; note: string; state: StepState }[],
    phone: [
      {
        title: "Adapter saved",
        note: pack.adapter ? "The fine-tune wrote the adapter" : "Written when fine-tune finishes",
        state: pack.adapter ? "done" : "wait",
      },
      {
        title: "Merged model",
        note:
          pack.status === "running" || pack.status === "submitted"
            ? PHASE_LABEL[pack.phase] || "Merging"
            : pack.ready
              ? "One Q4 file is on this Mac"
              : "Adds the adapter into a copy of the base weights",
        state:
          pack.status === "running" || pack.status === "submitted"
            ? "active"
            : pack.ready
              ? "done"
              : "wait",
      },
      {
        title: "Manifest written",
        note: pack.ready
          ? "The iPhone downloads this file when you tap Reinstall Model"
          : pack.status === "failed"
            ? pack.error || "The merged file was not written"
            : "Written beside the merged model",
        state: pack.ready ? "done" : pack.status === "failed" ? "active" : "wait",
      },
    ] satisfies { title: string; note: string; state: StepState }[],
  };
}

function rank(phase: string) {
  const order = ["", "submitted", "preparing", "training", "tagging", "completed"];
  const index = order.indexOf(phase);
  return index === -1 ? 0 : index;
}

function statusLabel(status: string) {
  if (status === "in_progress") return "In progress";
  if (status === "completed") return "Complete";
  if (status === "failed") return "Failed";
  if (status === "cancelled") return "Cancelled";
  if (status === "submitted") return "Submitted";
  return status || "Submitted";
}

function formatDate(value: string) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString("en", { month: "short", day: "numeric", year: "numeric" });
}
