'use client';

/**
 * Registers the window-level error handlers.
 *
 * The axios interceptor covers failed API calls and ErrorBoundary covers
 * render crashes. These two cover the rest: an error thrown outside React's
 * tree, and a rejected promise nobody caught - both of which otherwise vanish
 * with no record at all.
 *
 * Rendered once, near the root.
 */

import { useEffect } from 'react';
import logger, { toErrorField } from '@/lib/logger';

export function ClientLogging() {
  useEffect(() => {
    const onError = (event: ErrorEvent) => {
      logger.error('Uncaught error', {
        error: toErrorField(event.error ?? event.message),
        path: window.location.pathname,
        source: `${event.filename}:${event.lineno}:${event.colno}`,
      });
    };

    const onRejection = (event: PromiseRejectionEvent) => {
      logger.error('Unhandled promise rejection', {
        error: toErrorField(event.reason),
        path: window.location.pathname,
      });
    };

    window.addEventListener('error', onError);
    window.addEventListener('unhandledrejection', onRejection);

    // Removed on unmount: in dev, React's strict mode mounts twice, and
    // without this every error would be logged once per mount.
    return () => {
      window.removeEventListener('error', onError);
      window.removeEventListener('unhandledrejection', onRejection);
    };
  }, []);

  return null;
}

export default ClientLogging;
