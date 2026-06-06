export interface TraceEvent {
  step: string;
  status: "started" | "completed" | "failed" | "skipped";
  duration_ms?: number;
  message?: string;
  metadata?: Record<string, unknown>;
}

export interface ProvenanceItem {
  source_name: string;
  source_url: string;
  freshness: string; // ISO datetime
  series_id?: string;
  row_count?: number;
}

export interface ChartResponse {
  vega_spec: Record<string, unknown>;
  provenance: ProvenanceItem[];
  warnings: string[];
  pipeline_trace: TraceEvent[];
  codegen_used: boolean;
}

export interface ClarificationPayload {
  session_id: string;
  question: string;
}

export interface ErrorPayload {
  type: "irrelevant" | "injection" | "pipeline_error" | "no_data" | "render_failed";
  message: string;
}

export type StreamEvent =
  | { kind: "trace"; data: TraceEvent }
  | { kind: "clarification"; data: ClarificationPayload }
  | { kind: "error"; data: ErrorPayload }
  | { kind: "result"; data: ChartResponse };

export type AppState =
  | { phase: "idle" }
  | { phase: "loading"; trace: TraceEvent[] }
  | { phase: "clarification"; trace: TraceEvent[]; clarification: ClarificationPayload }
  | { phase: "result"; trace: TraceEvent[]; chart: ChartResponse }
  | { phase: "error"; trace: TraceEvent[]; error: ErrorPayload };
