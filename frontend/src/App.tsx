import { useChart } from "./hooks/useChart";
import { QueryInput } from "./components/QueryInput";
import { ChartDisplay } from "./components/ChartDisplay";
import { LoadingChart } from "./components/LoadingChart";
import { ProvenancePanel } from "./components/ProvenancePanel";
import { PipelineTrace } from "./components/PipelineTrace";
import { ErrorDisplay } from "./components/ErrorDisplay";

export default function App() {
  const { state, submit, clarify, reset } = useChart();

  const trace = "trace" in state ? state.trace : [];
  const loading = state.phase === "loading";
  const clarification = state.phase === "clarification" ? state.clarification : null;

  return (
    <div className="min-h-screen bg-bg text-text font-sans">
      <div className="max-w-6xl mx-auto px-6 py-12">
        {/* Header */}
        <header className="mb-10">
          <h1 className="font-serif text-3xl font-semibold text-text tracking-tight">
            Chart Agent
          </h1>
          <p className="mt-1 text-sm text-muted">
            Ask a data question. Get a chart.
          </p>
        </header>

        {/* Main layout */}
        <div className="flex gap-8">
          {/* Left: sidebar trace */}
          <aside className="w-48 flex-shrink-0 hidden lg:block">
            <PipelineTrace events={trace} loading={loading} />
          </aside>

          {/* Right: main content */}
          <main className="flex-1 min-w-0 space-y-6">
            <QueryInput
              onSubmit={submit}
              onClarify={clarify}
              clarification={clarification}
              loading={loading}
              onReset={reset}
            />

            {state.phase === "loading" && (
              <LoadingChart trace={trace} />
            )}

            {state.phase === "error" && (
              <ErrorDisplay error={state.error} onReset={reset} />
            )}

            {state.phase === "result" && (
              <>
                <ChartDisplay spec={state.chart.vega_spec} />
                <ProvenancePanel
                  provenance={state.chart.provenance}
                  warnings={state.chart.warnings}
                  codegenUsed={state.chart.codegen_used}
                />
              </>
            )}

            {/* Mobile trace */}
            {(loading || trace.length > 0) && (
              <div className="lg:hidden border-t border-border pt-4">
                <PipelineTrace events={trace} loading={loading} />
              </div>
            )}
          </main>
        </div>
      </div>
    </div>
  );
}
