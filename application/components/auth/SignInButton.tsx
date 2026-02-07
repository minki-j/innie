'use client';

import { signIn, signOut, useSession } from 'next-auth/react';

export function SignInButton() {
  const { data: session, status } = useSession();

  if (status === 'loading') {
    return (
      <button
        disabled
        className="px-4 py-2 text-sm font-medium text-gray-400 bg-gray-100 rounded-full cursor-not-allowed"
      >
        Loading...
      </button>
    );
  }

  if (session?.user) {
    return (
      <button
        onClick={() => signOut()}
        className="px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-full hover:bg-red-700 transition-colors"
      >
        Sign Out
      </button>
    );
  }

  return (
    <button
      onClick={() => signIn('google')}
      className="px-4 py-2 text-sm font-medium text-blue-600 bg-blue-50 rounded-full hover:bg-blue-100 transition-colors border border-blue-200"
    >
      Sign In
    </button>
  );
}
