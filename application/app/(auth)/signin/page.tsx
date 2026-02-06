import { SignInButton } from '@/components/auth/SignInButton';

export default function SignInPage() {
  return (
    <div className="bg-white p-8 rounded-lg shadow-lg max-w-md w-full">
      <div className="text-center mb-8">
        <svg
          className="w-16 h-16 text-red-600 mx-auto mb-4"
          fill="currentColor"
          viewBox="0 0 24 24"
        >
          <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z" />
        </svg>
        <h1 className="text-2xl font-bold text-gray-900">Sign in to YouTube</h1>
        <p className="text-gray-600 mt-2">Continue with your Google account</p>
      </div>

      <div className="flex justify-center">
        <SignInButton />
      </div>

      <p className="text-xs text-gray-500 text-center mt-8">
        This is a demo YouTube clone built with Next.js
      </p>
    </div>
  );
}
