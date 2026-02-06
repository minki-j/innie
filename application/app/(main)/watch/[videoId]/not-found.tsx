import Link from 'next/link';

export default function NotFound() {
  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
      <div className="flex flex-col items-center justify-center gap-4">
        <div className="text-center">
          <h2 className="text-2xl font-bold text-gray-900 mb-2">
            Video Not Found
          </h2>
          <p className="text-gray-600 mb-4">
            The video you're looking for doesn't exist or has been removed.
          </p>
        </div>
        <Link
          href="/"
          className="px-6 py-2 bg-blue-600 text-white rounded-full hover:bg-blue-700 transition-colors font-medium"
        >
          Go Home
        </Link>
      </div>
    </div>
  );
}
