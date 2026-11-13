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
      {/* A column the height of the screen: the page fills whatever the
          Navbar leaves, so a short page (one account, a few users) still
          reaches the bottom and nothing blank shows below it. "Powered by
          BridgeAI" sits in the Navbar, always on screen (client, 12 Nov),
          rather than in a footer below the content. */}
      <body className="antialiased text-gray-900 bg-gray-50 min-h-screen flex flex-col">
        {/* Registers the window error and unhandled-rejection handlers.
            Renders nothing. */}
        <ClientLogging />
        <AuthProvider>
          <Navbar />
          {/* Wraps the page only, not the Navbar: a crash inside a feature
              should still leave the user a way to navigate out of it. */}
          {/* The page's own root stretches to fill (flex-1), and its own
              screen-height minimum is lifted (min-h-0) so the page does not
              run a Navbar's height past the first screen. */}
          <main className="flex-1 flex flex-col [&>*]:flex-1 [&>*]:min-h-0">
            <ErrorBoundary name="Page">{children}</ErrorBoundary>
          </main>
        </AuthProvider>
      </body>
    </html>
  );
}
