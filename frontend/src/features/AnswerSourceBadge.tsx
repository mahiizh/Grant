import { Badge } from "../components/ui/badge";

export type AnswerSourceKind = "docs" | "web" | "unverified";

export interface AnswerWebSource {
  url?: string | null;
  title?: string | null;
}

const SOURCE_META: Record<AnswerSourceKind, { label: string; className: string }> = {
  docs: {
    label: "Docs",
    className: "border-sky-500/30 bg-sky-500/10 text-sky-300",
  },
  web: {
    label: "Web",
    className: "border-violet-500/30 bg-violet-500/10 text-violet-300",
  },
  unverified: {
    label: "Unverified",
    className: "border-amber-500/30 bg-amber-500/10 text-amber-300",
  },
};

export function AnswerSourceBadge({
  sourceKind,
  webSources = [],
}: {
  sourceKind?: string | null;
  webSources?: AnswerWebSource[];
}) {
  const kind: AnswerSourceKind =
    sourceKind === "web" || sourceKind === "unverified" ? sourceKind : "docs";
  const meta = SOURCE_META[kind];
  const visibleSources = webSources.filter((source) => Boolean(source.url)).slice(0, 3);

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <Badge variant="outline" className={`text-[10px] font-mono uppercase ${meta.className}`}>
        {meta.label}
      </Badge>
      {kind === "web" &&
        visibleSources.map((source, idx) => (
          <a
            key={`${source.url}-${idx}`}
            href={source.url ?? undefined}
            target="_blank"
            rel="noreferrer"
            className="max-w-[180px] truncate text-[10px] font-mono text-violet-300 hover:text-violet-200 underline decoration-violet-500/40"
            title={source.url ?? undefined}
            onClick={(event) => event.stopPropagation()}
          >
            {source.title || source.url}
          </a>
        ))}
    </div>
  );
}
