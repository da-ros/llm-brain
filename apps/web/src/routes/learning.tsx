import { createFileRoute } from "@tanstack/react-router";
import { LearningPage } from "@/components/encefalus/learning-page";

export const Route = createFileRoute("/learning")({
  head: () => ({
    meta: [
      { title: "Learning — Encefalus" },
      {
        name: "description",
        content: "Batch readiness, on-device model tags, and earlier fine-tune runs.",
      },
      { property: "og:title", content: "Learning — Encefalus" },
      { property: "og:description", content: "A transparent symbiotic learning loop." },
    ],
  }),
  component: LearningPage,
});
