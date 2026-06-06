import { useEffect, useRef, useState } from "react";
import embed, { VisualizationSpec } from "vega-embed";

interface Props {
  spec: Record<string, unknown>;
}

export function ChartDisplay({ spec }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [renderError, setRenderError] = useState<string | null>(null);

  useEffect(() => {
    if (!containerRef.current || !spec) return;
    setRenderError(null);

    const safeSpec: VisualizationSpec = {
      ...(spec as VisualizationSpec),
      width: "container" as unknown as number,
    };

    embed(containerRef.current, safeSpec, {
      actions: { export: true, source: false, compiled: false, editor: false },
      theme: "dark",
      renderer: "svg",
    })
      .then(() => {})
      .catch((err: unknown) => {
        console.error("Vega-Embed error:", err);
        setRenderError(String(err));
      });

    return () => {
      // vega-embed handles cleanup internally
    };
  }, [spec]);

  if (renderError) {
    return (
      <div className="flex items-center justify-center h-64 rounded-lg border border-border bg-surface">
        <div className="text-center space-y-2 px-6">
          <p className="text-sm font-sans text-muted">Chart render failed</p>
          <p className="text-xs font-mono text-red-400">{renderError}</p>
        </div>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="w-full rounded-lg overflow-hidden"
      style={{ minHeight: 420 }}
    />
  );
}
