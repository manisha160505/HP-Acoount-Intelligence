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
import { TryAgain } from '@/components/common/TryAgain';

interface Props {
  children: React.ReactNode;
  /** Names the area that failed, so the log says which one. */
  name?: string;
  fallback?: React.ReactNode;
}

interface State {
  hasError: boolean;
}

export class ErrorBoundary extends React.Component<Props, State> {
  state: State = { hasError: false };

  // The cause goes to the log only; the screen shows a neutral Try again
  // with no error text (client rule, approved).
  static getDerivedStateFromError(): State {
    return { hasError: true };
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

  private reset = () => this.setState({ hasError: false });

  render() {
    if (!this.state.hasError) return this.props.children;
    if (this.props.fallback) return <>{this.props.fallback}</>;

    return <TryAgain onRetry={this.reset} className="p-4" />;
  }
}

export default ErrorBoundary;
