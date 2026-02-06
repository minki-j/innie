import Link from 'next/link';
import { auth } from '@/lib/auth';
import { SearchBar } from './SearchBar';
import { UserMenu } from '../auth/UserMenu';
import { SignInButton } from '../auth/SignInButton';

export async function Navbar() {
  let session = null;
  try {
    session = await auth();
  } catch {
    // Gracefully fall back to unauthenticated if auth fails
  }

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

          {/* <SearchBar /> */}

          <div className="flex items-center gap-3 flex-shrink-0">
            {session ? (
              <>
                <Link
                  href="/settings/topics"
                  className="px-4 py-2 rounded-md hover:bg-gray-100 transition-colors text-sm font-semibold text-gray-600 hover:text-gray-900"
                >
                  Topics
                </Link>
                <UserMenu />
              </>
            ) : (
              <SignInButton />
            )}
          </div>
        </div>
      </div>
    </nav>
  );
}
