import type { ProvenanceItem } from "../types";

interface Props {
  provenance: ProvenanceItem[];
  warnings: string[];
  codegenUsed: boolean;
}

function timeAgo(isoDate: string): string {
  const diff = Date.now() - new Date(isoDate).getTime();
  const minutes = Math.floor(diff / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export function ProvenancePanel({ provenance, warnings, codegenUsed }: Props) {
  if (!provenance.length && !warnings.length) return null;

  return (
    <div className="mt-6 space-y-4">
      {provenance.length > 0 && (
        <div className="border-t border-border pt-4">
          <p className="text-xs font-sans text-muted mb-2 uppercase tracking-wider">Sources</p>
          <div className="space-y-2">
            {provenance.map((item, i) => (
              <div key={i} className="flex items-center justify-between gap-4">
                <div className="flex items-center gap-2 min-w-0">
                  <span className="w-1.5 h-1.5 rounded-full bg-accent flex-shrink-0" />
                  {item.source_url && item.source_url !== "local" ? (
                    <a
                      href={item.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-sm font-sans text-text hover:text-accent transition-colors truncate"
                    >
                      {item.source_name}
                      {item.series_id && (
                        <span className="ml-1 font-mono text-xs text-muted">
                          [{item.series_id}]
                        </span>
                      )}
                    </a>
                  ) : (
                    <span className="text-sm font-sans text-text truncate">
                      {item.source_name}
                    </span>
                  )}
                  {item.row_count != null && (
                    <span className="font-mono text-xs text-muted flex-shrink-0">
                      {item.row_count.toLocaleString()} rows
                    </span>
                  )}
                </div>
                <span className="text-xs font-mono text-muted flex-shrink-0">
                  {timeAgo(item.freshness)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {(warnings.length > 0 || codegenUsed) && (
        <div className="space-y-1.5">
          {codegenUsed && (
            <div className="flex items-start gap-2">
              <span className="text-xs text-yellow-500 font-mono mt-0.5">⚠</span>
              <p className="text-xs font-sans text-yellow-500">
                Chart generated via code generation — no matching template found.
              </p>
            </div>
          )}
          {warnings.map((w, i) => (
            <div key={i} className="flex items-start gap-2">
              <span className="text-xs text-muted font-mono mt-0.5">·</span>
              <p className="text-xs font-sans text-muted">{w}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
