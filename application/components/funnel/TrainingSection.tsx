'use client';

import { useState, useEffect, useCallback, useRef } from 'react';

type TrainingMethod = 'SFT' | 'RLVR';

interface TrainingInfo {
  feedbackCount: number;
  estimatedTokens: { sft: number; rlvr: number };
  latestRun: {
    id: string;
    status: 'PENDING' | 'TRAINING' | 'COMPLETED' | 'FAILED' | 'CANCELLED';
    method: TrainingMethod;
    modelName: string;
    version: number;
    datasetSize: number | null;
    isActive: boolean;
    error: string | null;
    createdAt: string;
    completedAt: string | null;
  } | null;
  minFeedbackRequired: number;
}

interface TrainingSectionProps {
  funnelId: string;
}

const METHOD_INFO: Record<TrainingMethod, { label: string; description: string }> = {
  SFT: {
    label: 'SFT',
    description: 'Supervised fine-tuning. Directly trains the model to reproduce your feedback.',
  },
  RLVR: {
    label: 'RLVR',
    description: 'Reinforcement learning with verifiable rewards. Trains via sampling + reward signals.',
  },
};

function StatusBadge({ status }: { status: 'PENDING' | 'TRAINING' | 'COMPLETED' | 'FAILED' | 'CANCELLED' }) {
  const config = {
    PENDING: { label: 'Pending', bg: 'bg-yellow-100', text: 'text-yellow-700' },
    TRAINING: { label: 'Training', bg: 'bg-blue-100', text: 'text-blue-700' },
    COMPLETED: { label: 'Completed', bg: 'bg-green-100', text: 'text-green-700' },
    FAILED: { label: 'Failed', bg: 'bg-red-100', text: 'text-red-700' },
    CANCELLED: { label: 'Cancelled', bg: 'bg-gray-100', text: 'text-gray-600' },
  };
  const { label, bg, text } = config[status];
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${bg} ${text}`}>
      {label}
    </span>
  );
}

function Spinner({ className = '', size = 'md' }: { className?: string; size?: 'sm' | 'md' }) {
  const sizeClass = size === 'sm' ? 'h-4 w-4' : 'h-5 w-5';
  return (
    <svg className={`animate-spin ${sizeClass} ${className}`} xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
    </svg>
  );
}

export function TrainingSection({ funnelId }: TrainingSectionProps) {
  const [info, setInfo] = useState<TrainingInfo | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [selectedMethod, setSelectedMethod] = useState<TrainingMethod>('RLVR');
  const [isStarting, setIsStarting] = useState(false);
  const [isCancelling, setIsCancelling] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [actionResult, setActionResult] = useState<{ type: 'success' | 'error'; message: string } | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchTrainingInfo = useCallback(async () => {
    try {
      const res = await fetch(`/api/funnels/${funnelId}/training`);
      if (res.ok) {
        const data: TrainingInfo = await res.json();
        setInfo(data);
        return data;
      }
    } catch (error) {
      console.error('Failed to fetch training info:', error);
    }
    return null;
  }, [funnelId]);

  useEffect(() => {
    fetchTrainingInfo().finally(() => setIsLoading(false));
  }, [fetchTrainingInfo]);

  useEffect(() => {
    const isActive = info?.latestRun?.status === 'PENDING' || info?.latestRun?.status === 'TRAINING';
    if (isActive) {
      pollRef.current = setInterval(async () => {
        const data = await fetchTrainingInfo();
        if (data?.latestRun?.status !== 'PENDING' && data?.latestRun?.status !== 'TRAINING') {
          if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
        }
      }, 5000);
    }
    return () => { if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; } };
  }, [info?.latestRun?.status, fetchTrainingInfo]);

  const handleStartTraining = async () => {
    setShowConfirm(false);
    setIsStarting(true);
    setActionResult(null);

    try {
      const res = await fetch('/api/training', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ funnelId, method: selectedMethod }),
      });

      if (res.ok) {
        setActionResult({ type: 'success', message: `${selectedMethod} training started! This may take a while.` });
        await fetchTrainingInfo();
      } else {
        const data = await res.json().catch(() => ({}));
        setActionResult({ type: 'error', message: data.error || 'Failed to start training.' });
      }
    } catch (error) {
      console.error('Failed to start training:', error);
      setActionResult({ type: 'error', message: 'Failed to connect to the training server.' });
    } finally {
      setIsStarting(false);
    }
  };

  const handleCancelTraining = async () => {
    if (!info?.latestRun?.id) return;
    if (!window.confirm('Are you sure you want to cancel the current training run?')) return;

    setIsCancelling(true);
    setActionResult(null);

    try {
      const res = await fetch(`/api/training/${info.latestRun.id}/cancel`, { method: 'POST' });
      if (res.ok) {
        setActionResult({ type: 'success', message: 'Training cancelled.' });
        await fetchTrainingInfo();
      } else {
        const data = await res.json().catch(() => ({}));
        setActionResult({ type: 'error', message: data.error || 'Failed to cancel training.' });
      }
    } catch (error) {
      console.error('Failed to cancel training:', error);
      setActionResult({ type: 'error', message: 'Failed to connect to the training server.' });
    } finally {
      setIsCancelling(false);
    }
  };

  const formatTokens = (tokens: number): string => {
    if (tokens >= 1_000_000) return `~${(tokens / 1_000_000).toFixed(1)}M`;
    if (tokens >= 1_000) return `~${(tokens / 1_000).toFixed(0)}K`;
    return `~${tokens}`;
  };

  const formatDate = (dateStr: string): string => {
    return new Date(dateStr).toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  };

  const isTrainingActive = info?.latestRun?.status === 'PENDING' || info?.latestRun?.status === 'TRAINING';
  const canStartTraining = info !== null && info.feedbackCount >= info.minFeedbackRequired && !isTrainingActive && !isStarting;
  const selectedTokens = info?.estimatedTokens[selectedMethod.toLowerCase() as 'sft' | 'rlvr'] ?? 0;

  if (isLoading) {
    return <div className="flex items-center gap-2 text-sm text-gray-400 py-4"><Spinner />Loading training info...</div>;
  }

  if (!info) {
    return <div className="text-sm text-gray-500 py-4">Failed to load training info.</div>;
  }

  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-2xl font-bold text-gray-900">{info.feedbackCount}</span>
            <span className="text-sm text-gray-500">feedback{info.feedbackCount !== 1 ? 's' : ''} available</span>
          </div>
          {info.feedbackCount < info.minFeedbackRequired && (
            <p className="text-xs text-amber-600 mt-1">
              At least {info.minFeedbackRequired} feedbacks with transcripts are required to start training.
            </p>
          )}
        </div>
      </div>

      <div className="space-y-3">
        <label className="block text-sm font-medium text-gray-700">Training method</label>
        <div className="flex flex-col sm:grid sm:grid-cols-2 gap-3">
          {(['SFT', 'RLVR'] as const).map((method) => {
            const tokens = info.estimatedTokens[method.toLowerCase() as 'sft' | 'rlvr'];
            const isSelected = selectedMethod === method;
            return (
              <button
                key={method}
                onClick={() => setSelectedMethod(method)}
                disabled={isTrainingActive}
                className={`text-left rounded-lg border-2 p-3 transition-colors ${isSelected ? 'border-gray-900 bg-gray-50' : 'border-gray-200 hover:border-gray-300 bg-white'} ${isTrainingActive ? 'opacity-60 cursor-not-allowed' : 'cursor-pointer'}`}
              >
                <div className="flex items-center justify-between">
                  <span className="text-sm font-semibold text-gray-900">{METHOD_INFO[method].label}</span>
                  <span className="text-xs text-gray-500">{formatTokens(tokens)} tokens</span>
                </div>
                <p className="text-xs text-gray-500 mt-1">{METHOD_INFO[method].description}</p>
              </button>
            );
          })}
        </div>
      </div>

      {info.latestRun && (
        <div className="border-t border-gray-100 pt-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <StatusBadge status={info.latestRun.status} />
              <span className="text-sm text-gray-700">{info.latestRun.modelName}</span>
              <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-500">{info.latestRun.method}</span>
              {info.latestRun.isActive && <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-700">Active</span>}
            </div>
            <span className="text-xs text-gray-400">{formatDate(info.latestRun.createdAt)}</span>
          </div>
          {info.latestRun.datasetSize && <p className="text-xs text-gray-500 mt-1">Trained on {info.latestRun.datasetSize} datapoints</p>}
          {info.latestRun.status === 'COMPLETED' && info.latestRun.completedAt && <p className="text-xs text-green-600 mt-1">Completed on {formatDate(info.latestRun.completedAt)}</p>}
          {info.latestRun.status === 'FAILED' && info.latestRun.error && <p className="text-xs text-red-600 mt-1">Error: {info.latestRun.error}</p>}
        </div>
      )}

      {isTrainingActive && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg px-4 py-3">
          <div className="flex items-center gap-3">
            <Spinner className="text-blue-600 flex-shrink-0" />
            <div className="flex-1">
              <p className="text-sm font-medium text-blue-800">{info.latestRun?.method} training is in progress...</p>
              <p className="text-xs text-blue-600 mt-0.5">This may take several minutes. You can leave this page and come back later.</p>
            </div>
          </div>
        </div>
      )}

      <div className="flex items-center gap-3 pt-2 border-t border-gray-100">
        {isTrainingActive ? (
          <button
            onClick={handleCancelTraining}
            disabled={isCancelling}
            className="px-4 py-2 bg-white text-red-600 text-sm font-medium rounded-lg border border-red-300 hover:bg-red-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
          >
            {isCancelling ? <><Spinner size="sm" />Cancelling...</> : 'Cancel Training'}
          </button>
        ) : (
          <button
            onClick={() => setShowConfirm(true)}
            disabled={!canStartTraining}
            className="px-4 py-2 bg-gray-900 text-white text-sm font-medium rounded-lg hover:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
          >
            {isStarting ? <><Spinner size="sm" />Starting...</> : `Train with ${selectedMethod}`}
          </button>
        )}
      </div>

      {actionResult && (
        <div className={`text-sm px-3 py-2 rounded-lg ${actionResult.type === 'success' ? 'bg-green-50 text-green-700 border border-green-200' : 'bg-red-50 text-red-700 border border-red-200'}`}>
          {actionResult.message}
        </div>
      )}

      {showConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white rounded-xl shadow-xl max-w-md w-full mx-4 p-6">
            <h3 className="text-lg font-semibold text-gray-900">Start {selectedMethod} Training?</h3>
            <div className="mt-3 space-y-2">
              <p className="text-sm text-gray-600">
                This will start <span className="font-medium">{METHOD_INFO[selectedMethod].label}</span> training using your{' '}
                <span className="font-medium">{info.feedbackCount} feedbacks</span>.
              </p>
              <div className="bg-gray-50 rounded-lg px-3 py-2 text-sm">
                <div className="flex justify-between text-gray-600">
                  <span>Estimated token usage</span>
                  <span className="font-medium text-gray-900">{formatTokens(selectedTokens)} tokens</span>
                </div>
              </div>
              <p className="text-xs text-gray-500">Training may take several minutes. You can cancel it at any time.</p>
            </div>
            <div className="mt-5 flex items-center justify-end gap-3">
              <button onClick={() => setShowConfirm(false)} className="px-4 py-2 text-sm text-gray-700 hover:text-gray-900">Cancel</button>
              <button onClick={handleStartTraining} className="px-4 py-2 bg-gray-900 text-white text-sm font-medium rounded-lg hover:bg-gray-800">Start {selectedMethod} Training</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
