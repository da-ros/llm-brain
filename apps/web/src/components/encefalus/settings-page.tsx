import { useEffect, useState } from "react";
import { AlertTriangle, Database, LogOut, Trash2, User } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  authHeaders,
  clearSession,
  initials,
  planLabel,
  readAccount,
  saveSession,
  type Account,
} from "@/lib/account";
import { Notice, PageHeader, Panel, PanelTitle, StatusDot } from "@/components/encefalus/primitives";

type ServiceRow = { id: string; label: string; status: "online" | "offline" };
type Storage = { bytes: number; documents: number };

const SERVICES: ServiceRow[] = [
  { id: "llm", label: "LLM core", status: "offline" },
  { id: "memory", label: "Memory retrieval", status: "offline" },
  { id: "personal", label: "Personal model", status: "offline" },
  { id: "analytics", label: "Analytics", status: "offline" },
  { id: "agents", label: "Agents", status: "offline" },
  { id: "shield", label: "Shield", status: "offline" },
];

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

async function readError(response: Response, fallback: string): Promise<string> {
  const body = await response.json().catch(() => ({}));
  if (typeof body?.detail === "string") return body.detail;
  if (Array.isArray(body?.detail) && body.detail[0]?.msg) {
    return String(body.detail[0].msg).replace(/^Value error,\s*/, "");
  }
  if (response.status === 401) return "Sign in to continue.";
  return fallback;
}

export function SettingsPage() {
  const [account, setAccount] = useState<Account | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const stored = readAccount();
    const token = sessionStorage.getItem("access_token");
    if (!stored || !token) {
      setReady(true);
      return;
    }
    setAccount(stored);
    setReady(true);
  }, []);

  if (!ready || !account) return <main className="min-h-svh" />;
  return <AccountScreen account={account} onAccount={setAccount} />;
}

function AccountScreen({
  account,
  onAccount,
}: {
  account: Account;
  onAccount: (account: Account) => void;
}) {
  const [services, setServices] = useState<ServiceRow[]>(SERVICES);
  const [storage, setStorage] = useState<Storage | null>(null);
  const [error, setError] = useState("");
  const [planBusy, setPlanBusy] = useState(false);

  useEffect(() => {
    void load();
  }, []);

  async function load() {
    setError("");
    try {
      const [accountResponse, statusResponse, storageResponse] = await Promise.all([
        fetch("/api/account", { headers: authHeaders() }),
        fetch("/api/status", { headers: authHeaders() }),
        fetch("/api/storage", { headers: authHeaders() }),
      ]);
      if (accountResponse.status === 401) {
        clearSession();
        return;
      }
      if (accountResponse.ok) {
        const user = (await accountResponse.json()) as Account;
        const token = sessionStorage.getItem("access_token") ?? "";
        if (token) saveSession(token, user);
        onAccount(user);
      }
      if (statusResponse.ok) {
        const body = await statusResponse.json();
        if (Array.isArray(body.services) && body.services.length > 0) setServices(body.services);
      } else {
        setError("Service status could not be loaded.");
      }
      if (storageResponse.ok) setStorage(await storageResponse.json());
      else setStorage(null);
    } catch {
      setError("Settings could not be loaded. Sign in when the API is reachable.");
    }
  }

  async function choosePlan(plan: "free" | "premium") {
    if (plan === account.plan) return;
    setPlanBusy(true);
    setError("");
    try {
      const response = await fetch("/api/account", {
        method: "PATCH",
        headers: authHeaders(true),
        body: JSON.stringify({ plan }),
      });
      if (!response.ok) {
        setError(await readError(response, "The plan could not be changed."));
        return;
      }
      const body = await response.json();
      saveSession(body.access_token, body.user);
      onAccount(body.user);
    } catch {
      setError("The account service is not reachable.");
    } finally {
      setPlanBusy(false);
    }
  }

  function signOut() {
    clearSession();
  }

  const used = storage ? formatBytes(storage.bytes) : "—";
  const files = storage
    ? `${storage.documents} file${storage.documents === 1 ? "" : "s"} of uploaded documents in memory`
    : "Storage could not be loaded.";

  return (
    <main className="min-h-svh enter">
      <PageHeader
        eyebrow="Account and system"
        title="Settings"
        description="Your account, the product services, and the memory your documents occupy."
      />
      <div className="space-y-4 p-5 sm:p-7">
        {error && <Notice>{error}</Notice>}
        <div className="grid gap-4 xl:grid-cols-2">
          <Panel>
            <PanelTitle title="Account & plan" icon={<User className="size-4" />} />
            <div className="p-5">
              <div className="flex items-center gap-3">
                <span className="grid size-11 place-items-center rounded-full bg-secondary text-xs font-bold">
                  {initials(account.name)}
                </span>
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold">{account.name}</p>
                  <p className="truncate text-xs text-muted-foreground">{account.email}</p>
                </div>
                <span className="ml-auto rounded bg-secondary px-2 py-1 text-[10px] font-semibold">
                  {planLabel(account.plan)}
                </span>
              </div>
              <div className="mt-4 grid grid-cols-2 gap-2">
                {(["free", "premium"] as const).map((choice) => (
                  <button
                    key={choice}
                    type="button"
                    disabled={planBusy}
                    onClick={() => void choosePlan(choice)}
                    className={`rounded-md border px-3 py-2 text-left text-xs ${account.plan === choice ? "border-primary bg-accent/40" : "border-border"}`}
                  >
                    <b className="block">{planLabel(choice)}</b>
                  </button>
                ))}
              </div>
            </div>
          </Panel>
          <Panel>
            <PanelTitle title="Brain status" icon={<Database className="size-4" />} />
            <div className="grid gap-3 p-5 text-xs sm:grid-cols-2">
              {services.map((row) => (
                <div key={row.id} className="flex items-center justify-between gap-3">
                  <span>{row.label}</span>
                  <StatusDot
                    tone={row.status === "online" ? "good" : "bad"}
                    label={row.status === "online" ? "Online" : "Offline"}
                  />
                </div>
              ))}
            </div>
          </Panel>
          <Panel>
            <PanelTitle title="Memory storage" />
            <div className="p-5">
              <p className="font-mono text-2xl font-semibold">{used}</p>
              <p className="mt-1 text-xs text-muted-foreground">{files}</p>
            </div>
          </Panel>
          <Panel>
            <PanelTitle title="Data management" />
            <div className="grid gap-2 p-5">
              <DeleteDialog onDeleted={() => setStorage({ bytes: 0, documents: 0 })} />
              <Button variant="ghost" onClick={signOut}>
                <LogOut />
                Log out
              </Button>
            </div>
          </Panel>
        </div>
      </div>
    </main>
  );
}

function DeleteDialog({ onDeleted }: { onDeleted: () => void }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function confirm() {
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/data", { method: "DELETE", headers: authHeaders() });
      if (!response.ok) {
        setError(await readError(response, "Your data could not be deleted."));
        return;
      }
      setOpen(false);
      onDeleted();
    } catch {
      setError("The API is not reachable.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="destructive">
          <Trash2 />
          Delete all data
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <AlertTriangle className="size-5 text-destructive" />
            Delete all personal data?
          </DialogTitle>
          <DialogDescription>
            This permanently removes your uploaded files and the memory Brain uses to answer. This cannot be undone.
          </DialogDescription>
        </DialogHeader>
        {error && <Notice>{error}</Notice>}
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="outline">Cancel</Button>
          </DialogClose>
          <Button variant="destructive" disabled={busy} onClick={() => void confirm()}>
            {busy ? "Deleting…" : "Delete everything"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
