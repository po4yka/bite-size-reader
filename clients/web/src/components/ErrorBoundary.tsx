import { Component } from "react";
import type { ErrorInfo, ReactNode } from "react";
import * as Sentry from "@sentry/react";
import { Button, InlineNotification } from "../design";

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
    Sentry.captureException(error, {
      contexts: { react: { componentStack: info.componentStack } },
    });
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
      <section className="page-section">
        <InlineNotification
          kind="error"
          title="Something went wrong"
          subtitle={error.message || "An unexpected error occurred in this section."}
          hideCloseButton
        />
        <div className="form-actions">
          <Button kind="primary" size="sm" onClick={this.handleReset}>
            Try again
          </Button>
          <Button kind="secondary" size="sm" onClick={() => window.location.reload()}>
            Reload page
          </Button>
        </div>
      </section>
    );
  }
}
