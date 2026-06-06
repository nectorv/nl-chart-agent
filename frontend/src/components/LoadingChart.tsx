import { useEffect, useState } from "react";
import type { TraceEvent } from "../types";

interface Props {
  trace: TraceEvent[];
}

const STEP_MESSAGES: Record<string, string> = {
  input_guard: "Validating query…",
  pipeline: "Starting pipeline…",
  query_planner: "Planning data sources…",
  data_fetcher: "Fetching data…",
  schema_reconciler: "Processing data…",
  chart_planner: "Choosing the best chart…",
  evaluator: "Evaluating chart quality…",
  renderer: "Rendering…",
};

function getActiveMessage(trace: TraceEvent[]): string {
  for (let i = trace.length - 1; i >= 0; i--) {
    if (trace[i].status === "started") {
      return STEP_MESSAGES[trace[i].step] ?? "Working…";
    }
  }
  if (trace.length > 0) {
    const last = trace[trace.length - 1];
    return STEP_MESSAGES[last.step] ?? "Working…";
  }
  return "Starting…";
}

export function LoadingChart({ trace }: Props) {
  const [dots, setDots] = useState(".");

  useEffect(() => {
    const id = setInterval(() => {
      setDots((d) => (d.length >= 3 ? "." : d + "."));
    }, 400);
    return () => clearInterval(id);
  }, []);

  const message = getActiveMessage(trace);
  const label = message.replace(/…$/, "");

  return (
    <div className="w-full rounded border border-border bg-surface flex flex-col items-center justify-center gap-4"
         style={{ height: 400 }}>

      {/* Animated bars — fake chart silhouette */}
      <div className="flex items-end gap-1.5 opacity-10">
        {[40, 65, 50, 80, 55, 70, 45, 90, 60, 75].map((h, i) => (
          <div
            key={i}
            className="w-4 bg-accent rounded-sm animate-pulse"
            style={{ height: h, animationDelay: `${i * 80}ms` }}
          />
        ))}
      </div>

      {/* Step label */}
      <div className="flex items-center gap-2 text-sm font-sans text-muted">
        <span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse flex-shrink-0" />
        <span>{label}<span className="font-mono">{dots}</span></span>
      </div>

      {/* Completed steps summary */}
      {trace.length > 0 && (
        <div className="flex items-center gap-3">
          {trace.filter((e) => e.status === "completed").map((e, i) => (
            <span key={i} className="text-xs font-mono text-muted/50">
              {e.step.replace("_", " ")}
              {e.duration_ms != null && ` ${e.duration_ms}ms`}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
