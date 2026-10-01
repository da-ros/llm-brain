import { createFileRoute } from "@tanstack/react-router";
import { DecisionsPage } from "@/components/encefalus/decisions-page";

export const Route = createFileRoute("/decisions")({
  head: () => ({
    meta: [
      { title: "Decisions — Encefalus" },
      { name: "description", content: "Explore decisions with explicit premises, personal evidence, and comparable scenarios." },
      { property: "og:title", content: "Decisions — Encefalus" },
      { property: "og:description", content: "An explainable decision cockpit grounded in your personal context." },
    ],
  }),
  component: DecisionsPage,
});
