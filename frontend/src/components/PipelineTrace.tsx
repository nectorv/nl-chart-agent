import type { TraceEvent } from "../types";

interface Props {
  events: TraceEvent[];
  loading: boolean;
}

const STEP_LABELS: Record<string, string> = {
  input_guard: "Input Guard",
  query_planner: "Query Planner",
  data_fetcher: "Data Fetcher",
  schema_reconciler: "Schema Reconciler",
  chart_planner: "Chart Planner",
  evaluator: "Evaluator",
  renderer: "Renderer",
  pipeline: "Pipeline",
};

const STATUS_STYLES: Record<string, string> = {
  started: "text-accent animate-pulse",
  completed: "text-green-400",
  failed: "text-red-400",
  skipped: "text-muted",
};

const STATUS_ICONS: Record<string, string> = {
  started: "○",
  completed: "●",
  failed: "✕",
  skipped: "–",
};

export function PipelineTrace({ events, loading }: Props) {
  if (!events.length && !loading) return null;

  return (
    <div className="space-y-1">
      <p className="text-xs font-sans text-muted uppercase tracking-wider mb-3">
        Pipeline
      </p>
      <div className="space-y-2">
        {events.map((ev, i) => (
          <div key={i} className="flex items-start gap-3">
            <span className={`text-xs font-mono mt-0.5 w-3 flex-shrink-0 ${STATUS_STYLES[ev.status] ?? "text-muted"}`}>
              {STATUS_ICONS[ev.status] ?? "·"}
            </span>
            <div className="flex-1 min-w-0">
              <div className="flex items-baseline gap-2">
                <span className="text-xs font-sans text-text">
                  {STEP_LABELS[ev.step] ?? ev.step}
                </span>
                {ev.duration_ms != null && (
                  <span className="text-xs font-mono text-muted">
                    {ev.duration_ms}ms
                  </span>
                )}
              </div>
              {ev.message && (
                <p className="text-xs font-mono text-muted mt-0.5 truncate">
                  {ev.message}
                </p>
              )}
            </div>
          </div>
        ))}
        {loading && events.length === 0 && (
          <div className="flex items-center gap-3">
            <span className="text-xs font-mono text-accent animate-pulse">○</span>
            <span className="text-xs font-sans text-muted">Starting…</span>
          </div>
        )}
      </div>
    </div>
  );
}
