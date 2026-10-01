import { createFileRoute } from "@tanstack/react-router";
import { BrainPage } from "@/components/encefalus/brain-page";

export const Route = createFileRoute("/brain")({
  head: () => ({
    meta: [
      { title: "Brain — Encefalus" },
      { name: "description", content: "Think with your personal AI Brain using explainable, memory-grounded context." },
      { property: "og:title", content: "Brain — Encefalus" },
      { property: "og:description", content: "A personal cognitive workspace grounded in your memories." },
    ],
  }),
  component: BrainPage,
});
