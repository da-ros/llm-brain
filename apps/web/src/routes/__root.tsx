import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Outlet, Link, createRootRouteWithContext, useRouter, HeadContent, Scripts } from "@tanstack/react-router";
import { useEffect, useState, type ReactNode } from "react";
import { AppShell } from "@/components/encefalus/app-shell";
import { WelcomePage } from "@/components/encefalus/welcome-page";
import { readAccount, type Account } from "@/lib/account";
import { Button } from "@/components/ui/button";
import appCss from "../styles.css?url";
import { reportLovableError } from "../lib/lovable-error-reporting";

function NotFoundComponent() {
  return <div className="grid min-h-screen place-items-center bg-background px-4"><div className="text-center"><p className="font-mono text-sm text-muted-foreground">404</p><h1 className="mt-3 text-3xl font-bold">Memory not found</h1><p className="mt-2 text-sm text-muted-foreground">This part of your Brain does not exist.</p><Button asChild className="mt-6"><Link to="/">Return home</Link></Button></div></div>;
}
function ErrorComponent({ error, reset }: { error: Error; reset: () => void }) {
  const router = useRouter();
  useEffect(() => { reportLovableError(error, { boundary: "tanstack_root_error_component" }); }, [error]);
  return <div className="grid min-h-screen place-items-center bg-background px-4"><div className="text-center"><h1 className="text-2xl font-bold">This page didn’t load</h1><p className="mt-2 text-sm text-muted-foreground">Try again or return to your Brain.</p><div className="mt-5 flex justify-center gap-2"><Button onClick={() => { router.invalidate(); reset(); }}>Try again</Button><Button asChild variant="outline"><Link to="/">Go home</Link></Button></div></div></div>;
}
export const Route = createRootRouteWithContext<{ queryClient: QueryClient }>()({
  head: () => ({
    meta: [
      { charSet: "utf-8" },
      { name: "viewport", content: "width=device-width, initial-scale=1" },
      { name: "theme-color", content: "#f5f2ec" },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
    links: [
      { rel: "stylesheet", href: appCss },
      { rel: "preconnect", href: "https://fonts.googleapis.com" },
      { rel: "preconnect", href: "https://fonts.gstatic.com", crossOrigin: "anonymous" },
      { rel: "stylesheet", href: "https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@500;600&family=Manrope:wght@400;500;600;700&display=swap" },
      { rel: "icon", href: "/favicon.ico", type: "image/x-icon" },
    ],
  }),
  shellComponent: RootShell,
  component: RootComponent,
  notFoundComponent: NotFoundComponent,
  errorComponent: ErrorComponent,
});
function RootShell({ children }: { children: ReactNode }) { return <html lang="en"><head><HeadContent /></head><body>{children}<Scripts /></body></html>; }
function RootComponent() {
  const { queryClient } = Route.useRouteContext();
  return (
    <QueryClientProvider client={queryClient}>
      <ProductGate />
    </QueryClientProvider>
  );
}

function ProductGate() {
  const [account, setAccount] = useState<Account | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const sync = () => {
      const token = sessionStorage.getItem("access_token");
      setAccount(token ? readAccount() : null);
      setReady(true);
    };
    sync();
    window.addEventListener("encefalus-auth", sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener("encefalus-auth", sync);
      window.removeEventListener("storage", sync);
    };
  }, []);

  if (!ready) return <div className="min-h-svh bg-background" />;
  if (!account) return <WelcomePage />;
  return (
    <AppShell>
      <Outlet />
    </AppShell>
  );
}
