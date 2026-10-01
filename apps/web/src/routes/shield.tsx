import { createFileRoute } from "@tanstack/react-router";
import { ShieldPage } from "@/components/encefalus/shield-page";

export const Route = createFileRoute("/shield")({
  head: () => ({
    meta: [
      { title: "Shield — Encefalus" },
      {
        name: "description",
        content: "Scan suspicious messages and files. Every scan is kept, and the analysis is the model inference.",
      },
      { property: "og:title", content: "Shield — Encefalus" },
      { property: "og:description", content: "Explainable protection for suspicious content." },
    ],
  }),
  component: ShieldPage,
});
