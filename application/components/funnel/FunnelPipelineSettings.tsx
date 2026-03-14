'use client';

import { useState } from 'react';

interface FunnelPipelineSettingsProps {
  funnelId: string;
  initialActive: boolean;
  initialIntervalHours: number;
  lastPipelineRunAt: string | null;
}

const INTERVAL_OPTIONS = [
  { value: 1, label: 'Every 1 hour' },
  { value: 3, label: 'Every 3 hours' },
  { value: 6, label: 'Every 6 hours' },
  { value: 12, label: 'Every 12 hours' },
  { value: 24, label: 'Every 24 hours' },
  { value: 48, label: 'Every 2 days' },
  { value: 72, label: 'Every 3 days' },
  { value: 168, label: 'Every 7 days' },
];

export function FunnelPipelineSettings({
  funnelId,
  initialActive,
  initialIntervalHours,
  lastPipelineRunAt,
}: FunnelPipelineSettingsProps) {
  const [active, setActive] = useState(initialActive);
  const [intervalHours, setIntervalHours] = useState(initialIntervalHours);
  const [isTogglingActive, setIsTogglingActive] = useState(false);
  const [isSavingInterval, setIsSavingInterval] = useState(false);
  const [isTriggering, setIsTriggering] = useState(false);
  const [triggerResult, setTriggerResult] = useState<{ type: 'success' | 'error'; message: string } | null>(null);
  const [savedInterval, setSavedInterval] = useState(false);

  const handleToggleActive = async () => {
    if (isTogglingActive) return;
    setIsTogglingActive(true);
    const newActive = !active;
    try {
      const res = await fetch(`/api/funnels/${funnelId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ active: newActive }),
      });
      if (res.ok) {
        setActive(newActive);
      }
    } catch (error) {
      console.error('Failed to toggle active:', error);
    } finally {
      setIsTogglingActive(false);
    }
  };

  const handleIntervalChange = async (newInterval: number) => {
    if (isSavingInterval) return;
    setIntervalHours(newInterval);
    setIsSavingInterval(true);
    setSavedInterval(false);
    try {
      const res = await fetch(`/api/funnels/${funnelId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pipelineIntervalHours: newInterval }),
      });
      if (res.ok) {
        setSavedInterval(true);
        setTimeout(() => setSavedInterval(false), 2000);
      }
    } catch (error) {
      console.error('Failed to save interval:', error);
    } finally {
      setIsSavingInterval(false);
    }
  };

  const handleTrigger = async () => {
    if (isTriggering) return;
    setIsTriggering(true);
    setTriggerResult(null);
    try {
      const res = await fetch(`/api/funnels/${funnelId}/trigger`, {
        method: 'POST',
      });
      if (res.ok) {
        setTriggerResult({ type: 'success', message: 'Pipeline triggered successfully. It will run in the background.' });
      } else {
        const data = await res.json().catch(() => ({}));
        setTriggerResult({ type: 'error', message: data.error || 'Failed to trigger pipeline.' });
      }
    } catch (error) {
      console.error('Failed to trigger pipeline:', error);
      setTriggerResult({ type: 'error', message: 'Failed to connect to the orchestrator.' });
    } finally {
      setIsTriggering(false);
      setTimeout(() => setTriggerResult(null), 5000);
    }
  };

  const formatLastRun = (dateStr: string | null) => {
    if (!dateStr) return 'Never';
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins} minute${diffMins === 1 ? '' : 's'} ago`;
    if (diffHours < 24) return `${diffHours} hour${diffHours === 1 ? '' : 's'} ago`;
    return `${diffDays} day${diffDays === 1 ? '' : 's'} ago`;
  };

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <label className="text-sm font-medium text-gray-700">Status</label>
          <p className="text-xs text-gray-500 mt-0.5">
            {active ? 'Pipeline is active and will run on schedule.' : 'Pipeline is paused. No scheduled runs.'}
          </p>
        </div>
        <button
          onClick={handleToggleActive}
          disabled={isTogglingActive}
          className={`relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 ${
            active ? 'bg-blue-600' : 'bg-gray-200'
          }`}
          role="switch"
          aria-checked={active}
        >
          <span
            className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
              active ? 'translate-x-5' : 'translate-x-0'
            }`}
          />
        </button>
      </div>

      <div>
        <label htmlFor="pipeline-interval" className="block text-sm font-medium text-gray-700 mb-1">
          Run Frequency
        </label>
        <div className="flex items-center gap-3">
          <select
            id="pipeline-interval"
            value={intervalHours}
            onChange={(e) => handleIntervalChange(Number(e.target.value))}
            disabled={isSavingInterval}
            className="px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white disabled:opacity-50"
          >
            {INTERVAL_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
          {savedInterval && <span className="text-sm text-green-600">Saved</span>}
          {isSavingInterval && <span className="text-sm text-gray-400">Saving...</span>}
        </div>
      </div>

      <div className="flex items-center justify-between pt-2 border-t border-gray-100">
        <div>
          <span className="text-sm text-gray-500">Last run: </span>
          <span className="text-sm font-medium text-gray-700">
            {formatLastRun(lastPipelineRunAt)}
          </span>
        </div>
        <button
          onClick={handleTrigger}
          disabled={isTriggering}
          className="px-4 py-2 bg-gray-900 text-white text-sm font-medium rounded-lg hover:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
        >
          {isTriggering ? (
            <>
              <svg className="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
              Running...
            </>
          ) : (
            <>
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              Run Now
            </>
          )}
        </button>
      </div>

      {triggerResult && (
        <div
          className={`text-sm px-3 py-2 rounded-lg ${
            triggerResult.type === 'success'
              ? 'bg-green-50 text-green-700 border border-green-200'
              : 'bg-red-50 text-red-700 border border-red-200'
          }`}
        >
          {triggerResult.message}
        </div>
      )}
    </div>
  );
}
