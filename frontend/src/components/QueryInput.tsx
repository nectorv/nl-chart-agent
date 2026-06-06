import { useState, useRef, useEffect, KeyboardEvent } from "react";
import type { ClarificationPayload } from "../types";

interface Props {
  onSubmit: (query: string) => void;
  onClarify: (sessionId: string, answer: string) => void;
  clarification: ClarificationPayload | null;
  loading: boolean;
  onReset: () => void;
}

export function QueryInput({ onSubmit, onClarify, clarification, loading, onReset }: Props) {
  const [query, setQuery] = useState("");
  const [answer, setAnswer] = useState("");
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const answerRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (clarification) answerRef.current?.focus();
    else inputRef.current?.focus();
  }, [clarification]);

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (query.trim()) onSubmit(query.trim());
    }
  }

  function handleAnswerKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" && clarification) {
      e.preventDefault();
      if (answer.trim()) {
        onClarify(clarification.session_id, answer.trim());
        setAnswer("");
      }
    }
  }

  return (
    <div className="w-full space-y-3">
      <div className="relative">
        <textarea
          ref={inputRef}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={loading}
          placeholder="Ask a data question — e.g. 'show me GDP growth for France and Germany since 2000'"
          rows={2}
          className="
            w-full resize-none rounded-lg border border-border bg-surface
            px-4 py-3 font-mono text-sm text-text placeholder-muted
            focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent
            disabled:opacity-50 transition-colors
          "
        />
        <div className="absolute bottom-3 right-3 flex gap-2">
          {(query || loading) && (
            <button
              onClick={() => {
                setQuery("");
                onReset();
              }}
              className="text-xs text-muted hover:text-text transition-colors"
            >
              clear
            </button>
          )}
          <button
            onClick={() => query.trim() && onSubmit(query.trim())}
            disabled={loading || !query.trim()}
            className="
              rounded bg-accent px-3 py-1 text-xs font-sans font-medium text-bg
              hover:bg-yellow-400 disabled:opacity-40 disabled:cursor-not-allowed
              transition-colors
            "
          >
            {loading ? "running…" : "run →"}
          </button>
        </div>
      </div>

      {clarification && (
        <div className="rounded-lg border border-accent/30 bg-surface p-4 space-y-3">
          <p className="text-sm font-sans text-accent">
            {clarification.question}
          </p>
          <div className="flex gap-2">
            <input
              ref={answerRef}
              value={answer}
              onChange={(e) => setAnswer(e.target.value)}
              onKeyDown={handleAnswerKeyDown}
              placeholder="Your answer…"
              className="
                flex-1 rounded border border-border bg-bg px-3 py-2 font-mono
                text-sm text-text placeholder-muted focus:border-accent
                focus:outline-none transition-colors
              "
            />
            <button
              onClick={() => {
                if (answer.trim()) {
                  onClarify(clarification.session_id, answer.trim());
                  setAnswer("");
                }
              }}
              disabled={!answer.trim()}
              className="
                rounded bg-accent px-4 py-2 text-sm font-sans font-medium text-bg
                hover:bg-yellow-400 disabled:opacity-40 transition-colors
              "
            >
              answer →
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
