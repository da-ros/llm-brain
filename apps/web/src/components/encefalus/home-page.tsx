import { Link } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { ArrowRight, Waypoints } from "lucide-react";
import { primaryItems } from "@/components/encefalus/app-shell";
import { readAccount } from "@/lib/account";

const descriptions: Record<(typeof primaryItems)[number]["to"], string> = {
  "/brain": "Chat, write, analyze and get things done.",
  "/memory": "Find and manage your knowledge.",
  "/decisions": "Get structured analysis and options.",
  "/analytics": "Turn your data into insights.",
  "/shield": "Detect scams, protect your privacy.",
  "/learning": "Help Encefalus learn and adapt to you.",
};

const journey = [
  { title: "Capture", text: "Bring in your notes, files, chats and data." },
  { title: "Remember", text: "Build a personal knowledge base." },
  { title: "Connect", text: "Find relationships across your information." },
  { title: "Reason", text: "Get deeper insights and analysis." },
  { title: "Decide", text: "Explore options and take action." },
  { title: "Learn", text: "Your Brain improves with your feedback." },
];

function greeting(hour: number): string {
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

function useToday() {
  const [today, setToday] = useState<{ date: string; greeting: string } | null>(null);
  useEffect(() => {
    const now = new Date();
    const firstName = readAccount()?.name.trim().split(/\s+/)[0];
    setToday({
      date: now.toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric", year: "numeric" }),
      greeting: firstName ? `${greeting(now.getHours())}, ${firstName}.` : `${greeting(now.getHours())}.`,
    });
  }, []);
  return today;
}

export function HomePage() {
  const today = useToday();
  return (
    <main className="mx-auto w-full max-w-6xl px-5 py-6 sm:px-7 lg:py-8">
      <header className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-start">
        <div className="min-w-0">
          <h1 className="text-2xl font-bold text-foreground sm:text-[1.75rem]">Welcome to Encefalus</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Your AI-augmented brain for clearer thinking, better decisions, and a more capable you.
          </p>
        </div>
        {today && (
          <div className="sm:text-right">
            <p className="text-sm font-semibold text-foreground">{today.date}</p>
            <p className="mt-1 text-xs text-muted-foreground">{today.greeting}</p>
          </div>
        )}
      </header>

      <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {primaryItems.map((item) => (
          <Link
            key={item.to}
            to={item.to}
            className="group grid grid-cols-[auto_minmax(0,1fr)_auto] items-start gap-4 rounded-lg border border-border bg-card px-4 py-5 shadow-panel transition-colors hover:border-ring/40 hover:bg-card/70"
          >
            <span className="grid size-10 place-items-center rounded-md bg-secondary text-secondary-foreground">
              <item.icon className="size-5" strokeWidth={1.7} />
            </span>
            <span className="min-w-0">
              <span className="block text-sm font-semibold text-foreground">{item.label}</span>
              <span className="mt-1 block max-w-[11.5rem] text-xs leading-5 text-muted-foreground">{descriptions[item.to]}</span>
            </span>
            <span className="grid size-8 place-items-center self-center rounded-full border border-border bg-background text-muted-foreground transition-colors group-hover:border-ring/40 group-hover:text-foreground">
              <ArrowRight className="size-4" />
            </span>
          </Link>
        ))}
      </div>

      <section className="mt-4 rounded-lg border border-border bg-card p-5 shadow-panel">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-foreground">
          <Waypoints className="size-4 text-muted-foreground" strokeWidth={1.7} />
          Your journey with Encefalus
        </h2>
        <ol className="mt-5 grid gap-5 sm:grid-cols-3 lg:grid-cols-6 lg:gap-4">
          {journey.map((step, index) => (
            <li key={step.title} className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="grid size-7 shrink-0 place-items-center rounded-full bg-[#6e5242] text-xs font-semibold text-white">
                  {index + 1}
                </span>
                {index < journey.length - 1 && (
                  <span className="hidden flex-1 items-center text-muted-foreground/60 lg:flex">
                    <span className="h-px flex-1 bg-border" />
                    <ArrowRight className="-ml-1 size-3" />
                  </span>
                )}
              </div>
              <p className="mt-3 text-sm font-semibold text-foreground">{step.title}</p>
              <p className="mt-1 text-xs leading-5 text-muted-foreground">{step.text}</p>
            </li>
          ))}
        </ol>
      </section>
    </main>
  );
}
