import { AppShellClient } from '@/components/layout/app-shell-client';
import { PageTransition } from '@/components/motion';

export default function AppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <AppShellClient>
      <PageTransition>{children}</PageTransition>
    </AppShellClient>
  );
}
