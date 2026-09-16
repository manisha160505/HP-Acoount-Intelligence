import type { Metadata } from 'next';
import './globals.css';
import { AuthProvider } from '@/providers/AuthProvider';
import { Navbar } from '@/components/navigation/Navbar';
import { ClientLogging } from '@/components/common/ClientLogging';
import { ErrorBoundary } from '@/components/common/ErrorBoundary';

export const metadata: Metadata = {
  title: 'HP Account Intelligence Platform',
  description: 'AI-Powered Enterprise Sales Intelligence System for HP',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="antialiased text-gray-900 bg-gray-50 min-h-screen">
        {/* Registers the window error and unhandled-rejection handlers.
            Renders nothing. */}
        <ClientLogging />
        <AuthProvider>
          <Navbar />
          {/* Wraps the page only, not the Navbar: a crash inside a feature
              should still leave the user a way to navigate out of it. */}
          <main>
            <ErrorBoundary name="Page">{children}</ErrorBoundary>
          </main>
        </AuthProvider>
      </body>
    </html>
  );
}
