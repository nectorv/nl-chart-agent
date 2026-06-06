import { useState, useCallback, useRef } from "react";
import type { AppState, TraceEvent, StreamEvent } from "../types";

function parseSSEEvent(eventType: string, data: string): StreamEvent | null {
  try {
    const parsed = JSON.parse(data);
    switch (eventType) {
      case "trace":
        return { kind: "trace", data: parsed as TraceEvent };
      case "clarification":
        return { kind: "clarification", data: parsed };
      case "error":
        return { kind: "error", data: parsed };
      case "result":
        return { kind: "result", data: parsed };
      default:
        return null;
    }
  } catch {
    return null;
  }
}

const API_BASE = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");

async function* streamSSE(
  url: string,
  body: Record<string, unknown>,
  signal: AbortSignal
): AsyncGenerator<{ event: string; data: string }> {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });

  if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let currentEvent = "message";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      if (line.startsWith("event:")) {
        currentEvent = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        const data = line.slice(5).trim();
        yield { event: currentEvent, data };
        currentEvent = "message";
      }
    }
  }
}

export function useChart() {
  const [state, setState] = useState<AppState>({ phase: "idle" });
  const abortRef = useRef<AbortController | null>(null);

  const submit = useCallback(async (query: string) => {
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    setState({ phase: "loading", trace: [] });

    try {
      for await (const raw of streamSSE(`${API_BASE}/api/query`, { query }, ctrl.signal)) {
        const ev = parseSSEEvent(raw.event, raw.data);
        if (!ev) continue;

        setState((prev) => {
          const trace = "trace" in prev ? prev.trace : [];

          if (ev.kind === "trace") {
            const updated = [...trace];
            const idx = updated.findIndex((t) => t.step === ev.data.step);
            if (idx >= 0) updated[idx] = ev.data;
            else updated.push(ev.data);
            return { phase: "loading", trace: updated };
          }

          if (ev.kind === "clarification") {
            return { phase: "clarification", trace, clarification: ev.data };
          }

          if (ev.kind === "error") {
            return { phase: "error", trace, error: ev.data };
          }

          if (ev.kind === "result") {
            return { phase: "result", trace: ev.data.pipeline_trace, chart: ev.data };
          }

          return prev;
        });
      }
    } catch (err: unknown) {
      if ((err as { name?: string }).name === "AbortError") return;
      setState((prev) => ({
        phase: "error",
        trace: "trace" in prev ? prev.trace : [],
        error: { type: "pipeline_error", message: String(err) },
      }));
    }
  }, []);

  const clarify = useCallback(async (sessionId: string, answer: string) => {
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    setState((prev) => ({
      phase: "loading",
      trace: "trace" in prev ? prev.trace : [],
    }));

    try {
      for await (const raw of streamSSE(
        `${API_BASE}/api/clarify`,
        { session_id: sessionId, answer },
        ctrl.signal
      )) {
        const ev = parseSSEEvent(raw.event, raw.data);
        if (!ev) continue;

        setState((prev) => {
          const trace = "trace" in prev ? prev.trace : [];

          if (ev.kind === "trace") {
            const updated = [...trace];
            const idx = updated.findIndex((t) => t.step === ev.data.step);
            if (idx >= 0) updated[idx] = ev.data;
            else updated.push(ev.data);
            return { phase: "loading", trace: updated };
          }
          if (ev.kind === "result") {
            return { phase: "result", trace: ev.data.pipeline_trace, chart: ev.data };
          }
          if (ev.kind === "error") {
            return { phase: "error", trace, error: ev.data };
          }
          return prev;
        });
      }
    } catch (err: unknown) {
      if ((err as { name?: string }).name === "AbortError") return;
      setState((prev) => ({
        phase: "error",
        trace: "trace" in prev ? prev.trace : [],
        error: { type: "pipeline_error", message: String(err) },
      }));
    }
  }, []);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    setState({ phase: "idle" });
  }, []);

  return { state, submit, clarify, reset };
}
