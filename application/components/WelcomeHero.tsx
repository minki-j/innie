'use client';

import { signIn } from 'next-auth/react';

const steps = [
  {
    number: "01",
    title: "Create your Funnels",
    description:
      "Define topics you care about. Add YouTube channels and keywords — your Innie will fetch and organize videos for each funnel.",
  },
  {
    number: "02",
    title: "Review to teach your Innie",
    description:
      "Rate videos as they come in. Every review becomes training data that teaches your Innie what content you actually want to see.",
  },
  {
    number: "03",
    title: "Your Innie scores your feed",
    description:
      "Once trained, your personal AI model scores incoming videos so the best content rises to the top — automatically.",
  },
];

export function WelcomeHero() {
  return (
    <div className="min-h-full flex flex-col items-center justify-center px-4 py-16">
      <div className="max-w-3xl w-full text-center">
        <div className="inline-flex items-center gap-2 bg-gray-100 text-gray-600 text-sm font-medium px-3 py-1 rounded-full mb-6">
          <span className="w-2 h-2 bg-red-500 rounded-full" />
          Personalized YouTube · Powered by your taste
        </div>

        <h1 className="text-4xl sm:text-5xl font-bold text-gray-900 tracking-tight mb-4">
          Train your personal
          <br />
          AI video curator
        </h1>

        <p className="text-lg text-gray-500 mb-10 max-w-xl mx-auto">
          Innie learns what you love and surfaces YouTube videos you&apos;ll
          actually watch — no algorithm games, no guessing.
        </p>

        <button
          onClick={() => signIn('google')}
          className="inline-flex items-center gap-2 bg-gray-900 text-white text-sm font-semibold px-6 py-3 rounded-full hover:bg-gray-700 transition-colors"
        >
          Get started with Google
          <svg
            className="w-4 h-4"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3"
            />
          </svg>
        </button>
      </div>

      <div className="max-w-3xl w-full mt-20 grid grid-cols-1 sm:grid-cols-3 gap-8">
        {steps.map((step) => (
          <div key={step.number} className="text-left">
            <span className="text-xs font-mono font-semibold text-gray-400 tracking-widest">
              {step.number}
            </span>
            <h3 className="mt-2 text-base font-semibold text-gray-900">
              {step.title}
            </h3>
            <p className="mt-1 text-sm text-gray-500 leading-relaxed">
              {step.description}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}
