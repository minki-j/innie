import Link from 'next/link';
import { AuthSection } from '../auth/AuthSection';

export function Navbar() {
  return (
    <nav className="sticky top-0 z-50 bg-white border-b border-gray-200">
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
