import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  resetKey?: string;
}

interface State {
  hasError: boolean;
  message: string;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = {
    hasError: false,
    message: "",
  };

  static getDerivedStateFromError(error: Error): State {
    return {
      hasError: true,
      message: error?.message ?? "Something went wrong.",
    };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("Unhandled UI error", error, errorInfo);
  }

  componentDidUpdate(prevProps: Props) {
    if (this.props.resetKey !== prevProps.resetKey && this.state.hasError) {
      this.setState({ hasError: false, message: "" });
    }
  }

  private reload = () => {
    window.location.reload();
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="mx-auto max-w-3xl px-32p py-80p">
          <div className="rounded-card border-2 border-rui-danger bg-rui-danger/10 p-6">
            <h2 className="font-display text-card font-medium text-rui-danger">
              Something went wrong
            </h2>
            <p className="mt-2 text-body text-fg">{this.state.message}</p>
            <button
              type="button"
              onClick={this.reload}
              className="mt-6 rounded-pill border-2 border-edge px-4 py-2 font-display text-body-em text-fg hover:opacity-85"
            >
              Reload page
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}