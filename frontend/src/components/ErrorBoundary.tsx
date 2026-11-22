import { Component, type ErrorInfo, type ReactNode } from "react";
import { ShieldCheck } from "lucide-react";

interface Props { children: ReactNode; }
interface State { hasError: boolean; error: Error | null; }

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("ErrorBoundary caught:", error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          display: "flex", alignItems: "center", justifyContent: "center",
          minHeight: "100vh", padding: 32,
          background: "var(--surface, #111)", color: "var(--text, #eee)",
        }}>
          <div style={{ maxWidth: 420, textAlign: "center" }}>
            <ShieldCheck size={40} style={{ color: "var(--danger, #e55)", marginBottom: 16 }} />
            <h1 style={{ fontSize: 20, marginBottom: 8 }}>Something went wrong</h1>
            <p style={{ color: "var(--dim, #888)", fontSize: 14, lineHeight: 1.6, marginBottom: 20 }}>
              An unexpected error occurred. Try refreshing the page.
            </p>
            <code style={{
              display: "block", padding: 12, borderRadius: 8,
              background: "var(--surface-raised, #1a1a1a)", fontSize: 12,
              color: "var(--danger, #e55)", wordBreak: "break-word", textAlign: "left",
              marginBottom: 20,
            }}>
              {this.state.error?.message || "Unknown error"}
            </code>
            <button
              onClick={() => window.location.reload()}
              style={{
                padding: "10px 24px", borderRadius: 8, border: "none",
                background: "var(--accent, #4f8ff7)", color: "#fff",
                fontSize: 14, cursor: "pointer", fontWeight: 500,
              }}
            >
              Refresh page
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
