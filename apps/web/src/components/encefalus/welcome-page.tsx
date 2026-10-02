import { useState, type FormEvent, type ReactNode } from "react";
import {
  ArrowRight,
  BarChart3,
  ChartLine,
  Eye,
  EyeOff,
  FileText,
  Image as ImageIcon,
  Laptop,
  Lightbulb,
  Lock,
  Mail,
  MessageCircle,
  ShieldCheck,
  Smartphone,
  User,
} from "lucide-react";
import { Checkbox } from "@/components/ui/checkbox";
import { Notice } from "@/components/encefalus/primitives";
import { saveSession } from "@/lib/account";

type Mode = "signup" | "signin";

const features = [
  {
    icon: Lock,
    title: "Private lifelong memory",
    text: "Keep your notes, files, and conversations in one secure, personal knowledge base.",
  },
  {
    icon: Lightbulb,
    title: "Explainable AI reasoning",
    text: "Get clear, source-grounded answers you can trust and verify.",
  },
  {
    icon: BarChart3,
    title: "Decision support & insights",
    text: "Turn your knowledge into clarity, options, and next steps.",
  },
];

async function readError(response: Response, fallback: string): Promise<string> {
  const body = await response.json().catch(() => ({}));
  if (typeof body?.detail === "string") return body.detail;
  if (Array.isArray(body?.detail) && body.detail[0]?.msg) {
    return String(body.detail[0].msg).replace(/^Value error,\s*/, "");
  }
  return fallback;
}

export function WelcomePage() {
  return (
    <div className="min-h-svh bg-background font-welcome text-foreground lg:h-svh lg:p-4">
      <div className="relative isolate flex min-h-svh flex-col overflow-hidden lg:h-full lg:min-h-0 lg:rounded-[1.75rem] lg:border lg:border-border/70 lg:shadow-panel lg:[container-type:size]">
        <img
          src="/welcome-brain.jpg"
          alt=""
          aria-hidden="true"
          className="absolute inset-0 -z-10 h-full w-full object-cover object-[40%_center] lg:hidden"
        />
        <BrainScene />
        <div className="absolute inset-0 -z-10 bg-background/80 lg:hidden" />
        <header
          className={`flex items-center justify-between gap-6 px-6 pt-6 sm:px-10 lg:px-12 lg:pt-7 short:lg:pt-5`}
        >
          <div className="flex min-w-0 items-center gap-3">
            <img src="/encefalus-mark.png" alt="" className="size-9 shrink-0" />
            <span className="truncate text-[1.35rem] font-semibold tracking-[-0.01em]">
              Encefalus
            </span>
            <span className="hidden h-5 w-px bg-foreground/15 sm:block" />
            <span className="hidden text-sm text-muted-foreground sm:block">
              AI-Augmented Brain
            </span>
          </div>
          <p className="hidden items-center gap-2.5 text-xs text-muted-foreground lg:flex">
            Private <span className="size-1 rounded-full bg-muted-foreground/60" /> Personal
            <span className="size-1 rounded-full bg-muted-foreground/60" /> More Capable You.
          </p>
        </header>
        <div
          className={`grid flex-1 gap-8 px-6 pb-8 pt-8 sm:px-10 lg:min-h-0 lg:grid-cols-[minmax(0,1fr)_min(33rem,36%)] lg:gap-10 lg:px-12 lg:pb-6 lg:pt-2 short:lg:pb-4`}
        >
          <Story />
          <AuthCard />
        </div>
      </div>
    </div>
  );
}

const sources = [
  {
    icon: FileText,
    label: "Your notes",
    left: "35.2%",
    top: "21.4%",
    width: "11.3%",
    bars: [72, 60, 38],
  },
  {
    icon: ImageIcon,
    label: "Your files",
    left: "45%",
    top: "34.2%",
    width: "11.3%",
    bars: [66, 56, 34],
  },
  {
    icon: MessageCircle,
    label: "Your conversations",
    left: "24.5%",
    top: "58.3%",
    width: "13.4%",
    bars: [70, 58, 36],
  },
  {
    icon: ChartLine,
    label: "Your insights",
    left: "43.1%",
    top: "69.1%",
    width: "12.9%",
    bars: [74, 62, 40],
  },
];

function BrainScene() {
  return (
    <div
      aria-hidden="true"
      className="absolute left-0 top-1/2 -z-10 hidden aspect-video w-[max(108cqw,178cqh)] -translate-y-1/2 [container-type:inline-size] lg:block"
    >
      <img src="/welcome-brain.jpg" alt="" className="absolute inset-0 size-full" />
      {sources.map((source) => (
        <div
          key={source.label}
          className="absolute flex items-start gap-[0.8cqw] rounded-[0.85cqw] border border-white/80 bg-[#fdfbf8]/85 px-[0.85cqw] py-[1cqw] shadow-[0_0.6cqw_1.8cqw_rgb(120_70_40/0.10)] backdrop-blur-[2px]"
          style={{ left: source.left, top: source.top, width: source.width }}
        >
          <span className="grid size-[2.3cqw] shrink-0 place-items-center rounded-[0.5cqw] bg-[#f6eadf] text-[#9a4a1c]">
            <source.icon className="size-[1.35cqw]" strokeWidth={1.8} />
          </span>
          <span className="min-w-0 flex-1 pt-[0.1cqw]">
            <span className="block whitespace-nowrap text-[0.78cqw] font-semibold leading-[1.1] text-[#3a2a22]">
              {source.label}
            </span>
            <span className="mt-[0.7cqw] block space-y-[0.45cqw]">
              {source.bars.map((width) => (
                <span
                  key={width}
                  className="block h-[0.26cqw] rounded-full bg-[#e6ddd4]"
                  style={{ width: `${width}%` }}
                />
              ))}
            </span>
          </span>
        </div>
      ))}
    </div>
  );
}

function Story() {
  return (
    <section className="flex min-w-0 flex-col lg:max-w-[31rem] xl:max-w-[35rem]">
      <div className={`lg:pt-8 short:lg:pt-4`}>
        <h1
          className={`max-w-[32rem] text-[2.5rem] font-semibold leading-[1.12] tracking-[-0.025em] sm:text-5xl lg:text-[2.45rem] xl:text-[2.85rem] short:lg:text-[2.35rem]`}
        >
          Your memories.
          <br />
          Sharper decisions.
          <br />
          <span className="text-[#6e5242]">A more intentional you.</span>
        </h1>
        <p
          className={`mt-6 max-w-[27rem] text-[15px] leading-6 text-muted-foreground short:lg:mt-4`}
        >
          Encefalus helps you capture your knowledge, understand your context, and make better
          decisions with a private, AI-augmented brain.
        </p>
      </div>
      <ul className={`mt-9 space-y-7 short:lg:mt-6 short:lg:space-y-5`}>
        {features.map((feature) => (
          <li key={feature.title} className="flex gap-4">
            <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-[#efe7dd] text-[#5b4032]">
              <feature.icon className="size-[18px]" strokeWidth={1.7} />
            </span>
            <span className="max-w-[16rem]">
              <span className="block text-[15px] font-semibold">{feature.title}</span>
              <span className="mt-1 block text-[13px] leading-5 text-muted-foreground">
                {feature.text}
              </span>
            </span>
          </li>
        ))}
      </ul>
      <div
        className={`mt-10 grid gap-4 border-t border-foreground/10 pt-5 sm:grid-cols-[auto_auto] sm:gap-0 lg:mt-auto short:lg:pt-4`}
      >
        <PlatformNote
          icon={<Smartphone className="size-5" strokeWidth={1.6} />}
          title="Free local AI on iPhone"
          text="Private, fast, and offline-ready."
        />
        <PlatformNote
          icon={<Laptop className="size-5" strokeWidth={1.6} />}
          title="Premium Digital Brain on web"
          text="More memory, RAG, analytics, and tools."
          className="sm:border-l sm:border-foreground/10 sm:pl-6"
        />
      </div>
    </section>
  );
}

function PlatformNote({
  icon,
  title,
  text,
  className = "",
}: {
  icon: ReactNode;
  title: string;
  text: string;
  className?: string;
}) {
  return (
    <div className={`flex items-center gap-3.5 pr-6 xl:whitespace-nowrap ${className}`}>
      <span className="shrink-0 text-[#5b4032]">{icon}</span>
      <p>
        <span className="block text-[13px] font-semibold">{title}</span>
        <span className="block text-xs text-muted-foreground">{text}</span>
      </p>
    </div>
  );
}

function AuthCard() {
  const [mode, setMode] = useState<Mode>("signup");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [agreed, setAgreed] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  function switchMode(next: Mode) {
    setMode(next);
    setError("");
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    if (mode === "signup" && password !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    if (mode === "signup" && !agreed) {
      setError("Agree to the terms to create your Brain.");
      return;
    }
    setBusy(true);
    const path = mode === "signup" ? "/api/auth/signup" : "/api/auth/signin";
    const payload =
      mode === "signup" ? { name, email, password, plan: "free" } : { email, password };
    try {
      const response = await fetch(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        const fallback =
          response.status >= 500
            ? "The account service is not reachable."
            : mode === "signup"
              ? "The account could not be created."
              : "Sign-in could not be completed.";
        setError(await readError(response, fallback));
        return;
      }
      const body = await response.json();
      saveSession(body.access_token, body.user);
    } catch {
      setError("The account service is not reachable.");
    } finally {
      setBusy(false);
    }
  }

  const tab = (value: Mode, label: string) => (
    <button
      type="button"
      onClick={() => switchMode(value)}
      className={`rounded-[0.6rem] px-3 py-2 transition-colors ${mode === value ? "bg-[#fdfbf8] text-foreground shadow-[0_1px_3px_rgb(60_40_30/0.12)]" : "text-muted-foreground hover:text-foreground"}`}
    >
      {label}
    </button>
  );

  return (
    <section
      className={`flex flex-col rounded-[1.25rem] border border-white/80 bg-[#fcfaf7]/92 px-6 py-6 shadow-[0_18px_50px_rgb(70_45_30/0.10)] backdrop-blur-md sm:px-10 lg:min-h-0 lg:overflow-y-auto lg:px-8 lg:py-6 xl:px-10 short:lg:py-4`}
    >
      <div className="grid grid-cols-2 rounded-xl border border-foreground/5 bg-[#f1ebe3] p-1 text-sm font-medium">
        {tab("signin", "Sign in")}
        {tab("signup", "Create account")}
      </div>
      <h2
        className={`mt-6 text-[1.5rem] font-semibold leading-tight tracking-[-0.02em] short:mt-4 short:text-[1.35rem]`}
      >
        {mode === "signup" ? "Create your Encefalus account" : "Welcome back"}
      </h2>
      <p className="mt-1.5 max-w-sm text-sm leading-5 text-muted-foreground">
        {mode === "signup"
          ? "Start building your personal knowledge base and more capable you."
          : "Sign in to your personal Brain."}
      </p>
      <form className={`mt-5 space-y-3.5 short:mt-3 short:space-y-2`} onSubmit={submit}>
        {mode === "signup" && (
          <Field id="full-name" label="Full name" icon={<User className="size-4" />}>
            <WelcomeInput
              id="full-name"
              autoComplete="name"
              placeholder="Jane Doe"
              value={name}
              onChange={setName}
            />
          </Field>
        )}
        <Field id="email" label="Email" icon={<Mail className="size-4" />}>
          <WelcomeInput
            id="email"
            type="email"
            autoComplete="email"
            placeholder="jane@company.com"
            value={email}
            onChange={setEmail}
          />
        </Field>
        <Field
          id="password"
          label="Password"
          icon={<Lock className="size-4" />}
          trailing={
            <VisibilityButton
              shown={showPassword}
              onToggle={() => setShowPassword((value) => !value)}
              label="password"
            />
          }
        >
          <WelcomeInput
            id="password"
            type={showPassword ? "text" : "password"}
            autoComplete={mode === "signup" ? "new-password" : "current-password"}
            placeholder={mode === "signup" ? "Create a strong password" : "Your password"}
            value={password}
            onChange={setPassword}
            minLength={8}
            trailing
          />
        </Field>
        {mode === "signup" && (
          <Field
            id="confirm-password"
            label="Confirm password"
            icon={<Lock className="size-4" />}
            trailing={
              <VisibilityButton
                shown={showConfirm}
                onToggle={() => setShowConfirm((value) => !value)}
                label="confirm password"
              />
            }
          >
            <WelcomeInput
              id="confirm-password"
              type={showConfirm ? "text" : "password"}
              autoComplete="new-password"
              placeholder="Confirm your password"
              value={confirm}
              onChange={setConfirm}
              minLength={8}
              trailing
            />
          </Field>
        )}
        {mode === "signup" && (
          <label className="flex items-center gap-2.5 pt-1 text-[13px] text-muted-foreground">
            <Checkbox
              checked={agreed}
              onCheckedChange={(value) => setAgreed(value === true)}
              className="size-[18px] rounded-[5px] border-foreground/30 bg-white"
            />
            <span>
              I agree to the{" "}
              <span className="text-[#5b4032] underline underline-offset-2">Terms of Service</span>{" "}
              and{" "}
              <span className="text-[#5b4032] underline underline-offset-2">Privacy Policy</span>.
            </span>
          </label>
        )}
        {error && <Notice>{error}</Notice>}
        <button
          type="submit"
          disabled={busy}
          className={`flex h-11 w-full items-center justify-center gap-2.5 rounded-xl bg-[#5a3b2e] text-[15px] font-medium text-[#fbf6f1] shadow-[0_6px_16px_rgb(90_59_46/0.25)] transition-colors hover:bg-[#4d3226] disabled:opacity-60 short:h-10`}
        >
          {busy ? (
            "Please wait…"
          ) : mode === "signup" ? (
            <>
              <img src="/encefalus-mark.png" alt="" className="size-5 brightness-0 invert" />
              Create my Brain
              <ArrowRight className="size-4" />
            </>
          ) : (
            <>
              Sign in
              <ArrowRight className="size-4" />
            </>
          )}
        </button>
      </form>
      <div
        className={`mt-5 border-t border-foreground/10 pt-4 text-center text-[13px] text-muted-foreground short:mt-3 short:pt-3`}
      >
        {mode === "signup" ? "Already have an account? " : "New here? "}
        <button
          type="button"
          className="font-semibold text-[#5b4032] underline underline-offset-2"
          onClick={() => switchMode(mode === "signup" ? "signin" : "signup")}
        >
          {mode === "signup" ? "Sign in" : "Create an account"}
        </button>
      </div>
      <div
        className={`mt-4 flex items-center gap-3.5 rounded-xl bg-[#f3eee8] px-4 py-3 short:mt-3 short:py-2.5`}
      >
        <ShieldCheck className="size-5 shrink-0 text-[#5b4032]" strokeWidth={1.6} />
        <p className="text-xs leading-5 text-muted-foreground">
          <span className="block font-semibold text-foreground">
            Private by design. Your data stays under your control.
          </span>
          Your content is encrypted and never used to train public models.
        </p>
      </div>
    </section>
  );
}

function Field({
  id,
  label,
  icon,
  trailing,
  children,
}: {
  id: string;
  label: string;
  icon: ReactNode;
  trailing?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-[13px] font-medium text-foreground">
        {label}
      </label>
      <div className="relative">
        <span className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-muted-foreground">
          {icon}
        </span>
        {children}
        {trailing}
      </div>
    </div>
  );
}

function WelcomeInput({
  onChange,
  trailing = false,
  ...props
}: {
  id: string;
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  type?: string;
  autoComplete?: string;
  minLength?: number;
  trailing?: boolean;
}) {
  return (
    <input
      {...props}
      required
      onChange={(event) => onChange(event.target.value)}
      className={`h-10 w-full rounded-[0.65rem] border border-foreground/12 bg-white/80 pl-10 text-sm text-foreground outline-none transition-shadow placeholder:text-muted-foreground/70 focus:border-[#5a3b2e]/40 focus:ring-2 focus:ring-[#5a3b2e]/10 ${trailing ? "pr-10" : "pr-3"} short:h-9`}
    />
  );
}

function VisibilityButton({
  shown,
  onToggle,
  label,
}: {
  shown: boolean;
  onToggle: () => void;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      className="absolute right-2 top-1/2 grid size-8 -translate-y-1/2 place-items-center rounded-md text-muted-foreground hover:text-foreground"
      aria-label={shown ? `Hide ${label}` : `Show ${label}`}
    >
      {shown ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
    </button>
  );
}
