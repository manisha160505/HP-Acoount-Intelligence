'use client';

/**
 * Catches a render-time crash, logs it, and shows a recoverable fallback.
 *
 * Without a boundary, a thrown error in any component unmounts the whole React
 * tree and leaves a blank white page with the cause visible only to whoever
 * happens to have devtools open - which is the same symptom as a feature
 * legitimately having no data, and impossible to tell apart from a bug report.
 */

import React from 'react';
import logger, { toErrorField } from '@/lib/logger';

interface Props {
  children: React.ReactNode;
  /** Names the area that failed, so the log says which one. */
  name?: string;
  fallback?: React.ReactNode;
}

interface State {
  hasError: boolean;
  message: string;
}

export class ErrorBoundary extends React.Component<Props, State> {
  state: State = { hasError: false, message: '' };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, message: error.message };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    logger.error(`Render failed in ${this.props.name || 'component'}`, {
      component: this.props.name,
      error: toErrorField(error),
      // Which component threw, which the stack alone does not say once the
      // build is minified.
      component_stack: info.componentStack,
    });
  }

  private reset = () => this.setState({ hasError: false, message: '' });

  render() {
    if (!this.state.hasError) return this.props.children;
    if (this.props.fallback) return <>{this.props.fallback}</>;

    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm">
        <p className="font-semibold text-red-800">
          {this.props.name ? `${this.props.name} could not be displayed.` : 'Something went wrong.'}
        </p>
        <p className="mt-1 text-red-700">{this.state.message}</p>
        <button
          onClick={this.reset}
          className="mt-3 rounded-md bg-red-600 px-3 py-1.5 text-white hover:bg-red-700"
        >
          Try again
        </button>
      </div>
    );
  }
}

export default ErrorBoundary;
