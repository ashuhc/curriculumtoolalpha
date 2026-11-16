// Keeps a crash inside one page from blanking the whole app: the shell, navigation and
// assistant stay usable and the page offers a retry.
import { Component, type ErrorInfo, type ReactNode } from "react";
import { Alert, Button } from "./ui";

interface Props { children: ReactNode; /** Changing this (e.g. the route) clears the error. */ resetKey?: string }
interface State { error: Error | null }

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Page render failed:", error, info.componentStack);
  }

  componentDidUpdate(prev: Props) {
    if (this.state.error && prev.resetKey !== this.props.resetKey) this.setState({ error: null });
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <Alert tone="error" title="This Page Couldn't Be Displayed"
        action={<div className="flex gap-2">
          <Button size="sm" onClick={() => this.setState({ error: null })}>Try Again</Button>
          <Button size="sm" variant="ghost" onClick={() => window.location.reload()}>Reload App</Button>
        </div>}>
        {this.state.error.message || "An unexpected error occurred."} Other pages are still available from the sidebar.
      </Alert>
    );
  }
}
