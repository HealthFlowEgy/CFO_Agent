"use client";
import React from "react";

interface State { hasError: boolean; message?: string }

export class ErrorBoundary extends React.Component<
  { children: React.ReactNode; fallback?: React.ReactNode },
  State
> {
  state: State = { hasError: false };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, message: error?.message ?? "Unknown error" };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    // eslint-disable-next-line no-console
    console.error("[ErrorBoundary]", error, info);
  }

  reset = () => this.setState({ hasError: false, message: undefined });

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;
      return (
        <div className="glass-strong p-4 text-sm space-y-2 border border-danger/40 bg-danger/10">
          <div className="font-medium text-danger">A panel failed to render.</div>
          <div className="text-xs text-slate-400">{this.state.message}</div>
          <button
            onClick={this.reset}
            className="px-3 py-1.5 rounded bg-white/10 hover:bg-white/20 text-xs"
          >
            Try again
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
