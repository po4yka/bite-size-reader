import { Component } from "react";
import type { ErrorInfo, ReactNode } from "react";
import { Button, InlineNotification } from "@carbon/react";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

export default class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("[ErrorBoundary] Uncaught error:", error, info.componentStack);
  }

  private handleReset = (): void => {
    this.setState({ error: null });
  };

  render(): ReactNode {
    const { error } = this.state;

    if (error === null) {
      return this.props.children;
    }

    return (
      <div style={{ padding: "1rem" }}>
        <InlineNotification
          kind="error"
          title="Something went wrong"
          subtitle={error.message || "An unexpected error occurred in this section."}
          hideCloseButton
        />
        <div style={{ display: "flex", gap: "0.5rem", marginTop: "1rem" }}>
          <Button kind="primary" size="sm" onClick={this.handleReset}>
            Try again
          </Button>
          <Button kind="secondary" size="sm" onClick={() => window.location.reload()}>
            Reload page
          </Button>
        </div>
      </div>
    );
  }
}
