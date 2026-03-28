import Link from 'next/link';
import { AuthSection } from '../auth/AuthSection';

export function Navbar() {
  return (
    <nav className="sticky top-0 z-50 bg-white/95 shadow-[0_0px_9px_rgba(148,163,184,0.22)] backdrop-blur">
      <div className="max-w-[1920px] mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16 gap-4">
          <Link
            href="/"
            className="flex items-center gap-2 flex-shrink-0"
          >
            <span className="text-xl font-semibold hidden sm:inline text-black">Innie</span>
          </Link>

          <div className="flex items-center gap-3 flex-shrink-0">
            <AuthSection />
          </div>
        </div>
      </div>
    </nav>
  );
}
