'use client';

import { useSession } from 'next-auth/react';
import Link from 'next/link';
import { UserMenu } from './UserMenu';
import { SignInButton } from './SignInButton';

export function AuthSection() {
  const { data: session, status } = useSession();

  if (status === 'loading') {
    return (
      <div className="flex items-center gap-3">
        <div className="w-8 h-8 rounded-full bg-gray-100 animate-pulse" />
      </div>
    );
  }

  if (session?.user) {
    return (
      <>
        <Link
          href="/settings/funnels"
          className="px-4 py-2 rounded-md hover:bg-gray-100 transition-colors text-sm font-semibold text-gray-600 hover:text-gray-900"
        >
          Funnels
        </Link>
        <UserMenu />
      </>
    );
  }

  return <SignInButton />;
}
