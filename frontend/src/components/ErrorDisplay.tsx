import type { ErrorPayload } from "../types";

interface Props {
  error: ErrorPayload;
  onReset: () => void;
}

const ERROR_COPY: Record<string, { title: string; detail: (msg: string) => string }> = {
  irrelevant: {
    title: "Not a data query",
    detail: (msg) => msg,
  },
  injection: {
    title: "Query couldn't be processed",
    detail: () => "Please try a different query.",
  },
  pipeline_error: {
    title: "Something went wrong",
    detail: (msg) => msg,
  },
  no_data: {
    title: "No data found",
    detail: (msg) => msg,
  },
  render_failed: {
    title: "Chart render failed",
    detail: () => "The data was retrieved but the chart could not be rendered. Try rephrasing your query.",
  },
};

export function ErrorDisplay({ error, onReset }: Props) {
  const copy = ERROR_COPY[error.type] ?? ERROR_COPY.pipeline_error;

  return (
    <div className="rounded-lg border border-red-900/50 bg-surface p-6 space-y-3">
      <div className="flex items-start gap-3">
        <span className="text-red-400 text-lg leading-none">✕</span>
        <div className="space-y-1">
          <p className="text-sm font-sans font-medium text-text">{copy.title}</p>
          <p className="text-sm font-sans text-muted">{copy.detail(error.message)}</p>
        </div>
      </div>
      <button
        onClick={onReset}
        className="text-xs font-sans text-accent hover:text-yellow-400 transition-colors"
      >
        ← Try again
      </button>
    </div>
  );
}
