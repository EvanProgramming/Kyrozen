import { Navbar } from './Navbar';

interface LayoutProps {
  children: React.ReactNode;
}

export function Layout({ children }: LayoutProps) {
  return (
    <div className="min-h-screen bg-warm-50">
      <Navbar />
      <main className="max-w-7xl mx-auto px-6 py-8">{children}</main>
    </div>
  );
}
