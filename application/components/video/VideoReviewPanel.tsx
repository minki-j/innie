'use client';

import { useState, useRef, useCallback, useEffect } from 'react';
import { useSession } from 'next-auth/react';
import { cn } from '@/lib/utils';
import { VideoFunnel } from '@/types/youtube';

// ─── Types ───────────────────────────────────────────────────

interface VideoReviewPanelProps {
  videoId: string;
  funnels: VideoFunnel[];
}

type Rating = 'dislike' | 'neutral' | 'like' | null;

interface ClassNodeResultItem {
  id: string;
  classNodeId: string;
  description: string;
  result: 'PASS' | 'FAIL' | 'CANNOT_TELL';
  explanation: string | null;
  confidence: number | null;
}

interface ClassNodeResultEdit {
  result: 'PASS' | 'FAIL' | 'CANNOT_TELL';
  explanation: string | null;
}

interface FunnelClassNodeGroup {
  funnelId: string;
  funnelName: string;
  results: ClassNodeResultItem[];
}

interface FunnelReviewState {
  rating: Rating;
  feedback: string;
  submitted: boolean;
  loaded: boolean;
}

// ─── Result Badge ─────────────────────────────────────────────

function ResultBadge({
  result,
  onToggle,
}: {
  result: 'PASS' | 'FAIL' | 'CANNOT_TELL';
  onToggle: () => void;
}) {
  if (result === 'PASS') {
    return (
      <button
        type="button"
        onClick={(e) => { e.stopPropagation(); onToggle(); }}
        className="inline-flex items-center justify-center rounded-full bg-green-100 text-green-700 p-1 hover:bg-green-200 transition-colors cursor-pointer shrink-0"
        title="PASS — click to toggle"
      >
        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" />
        </svg>
      </button>
    );
  }
  if (result === 'FAIL') {
    return (
      <button
        type="button"
        onClick={(e) => { e.stopPropagation(); onToggle(); }}
        className="inline-flex items-center justify-center rounded-full bg-red-100 text-red-700 p-1 hover:bg-red-200 transition-colors cursor-pointer shrink-0"
        title="FAIL — click to toggle"
      >
        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
        </svg>
      </button>
    );
  }
  return (
    <button
      type="button"
      onClick={(e) => { e.stopPropagation(); onToggle(); }}
      className="inline-flex items-center justify-center rounded-full bg-amber-100 text-amber-700 p-1 hover:bg-amber-200 transition-colors cursor-pointer shrink-0"
      title="CANNOT TELL — click to toggle"
    >
      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9.879 7.519c1.171-1.025 3.071-1.025 4.242 0 1.172 1.025 1.172 2.687 0 3.712-.203.179-.43.326-.67.442-.745.361-1.45.999-1.45 1.827v.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 5.25h.008v.008H12v-.008Z" />
      </svg>
    </button>
  );
}

// ─── Class Node Results Section ───────────────────────────────

function ClassNodeResults({
  results,
  edits,
  onEditResult,
  onEditExplanation,
}: {
  results: ClassNodeResultItem[];
  edits: Map<string, ClassNodeResultEdit>;
  onEditResult: (id: string, nextResult: 'PASS' | 'FAIL' | 'CANNOT_TELL') => void;
  onEditExplanation: (id: string, explanation: string) => void;
}) {
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());

  const toggleExpanded = (id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const cycleResult = (current: 'PASS' | 'FAIL' | 'CANNOT_TELL'): 'PASS' | 'FAIL' | 'CANNOT_TELL' => {
    if (current === 'PASS') return 'FAIL';
    if (current === 'FAIL') return 'CANNOT_TELL';
    return 'PASS';
  };

  if (results.length === 0) {
    return <div className="text-sm text-gray-400 italic py-2">No evaluation results yet.</div>;
  }

  return (
    <div className="space-y-2">
      {results.map((r) => {
        const isExpanded = expandedIds.has(r.id);
        const edit = edits.get(r.id);
        const currentResult = edit?.result ?? r.result;
        const verdictChanged = edit !== undefined && edit.result !== r.result;
        const currentExplanation = verdictChanged ? (edit.explanation ?? '') : (edit?.explanation ?? r.explanation ?? '');

        return (
          <div key={r.id} className="rounded-lg border border-gray-200 bg-gray-50 overflow-hidden">
            <div
              role="button"
              tabIndex={0}
              onClick={() => toggleExpanded(r.id)}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleExpanded(r.id); } }}
              className="w-full flex items-start gap-2.5 px-3 py-2.5 text-left cursor-pointer hover:bg-gray-100 transition-colors"
            >
              <div className="shrink-0 mt-0.5">
                <ResultBadge
                  result={currentResult}
                  onToggle={() => onEditResult(r.id, cycleResult(currentResult))}
                />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm text-gray-800 leading-snug">{r.description}</p>
                {r.confidence !== null && (
                  <span className="text-xs text-gray-400">Confidence: {r.confidence}%</span>
                )}
              </div>
              <svg
                className={cn('w-4 h-4 text-gray-400 shrink-0 mt-0.5 transition-transform duration-200', isExpanded && 'rotate-180')}
                fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="m19.5 8.25-7.5 7.5-7.5-7.5" />
              </svg>
            </div>
            {isExpanded && (
              <div className="px-3 pb-3 pt-0 border-t border-gray-200 bg-white">
                {verdictChanged ? (
                  <textarea
                    value={currentExplanation}
                    onChange={(e) => {
                      onEditExplanation(r.id, e.target.value);
                      e.target.style.height = 'auto';
                      e.target.style.height = `${e.target.scrollHeight}px`;
                    }}
                    ref={(el) => { if (el) { el.style.height = 'auto'; el.style.height = `${el.scrollHeight}px`; } }}
                    placeholder="Why do you disagree with the original verdict?"
                    rows={2}
                    className="w-full mt-2.5 rounded-md border border-gray-200 bg-gray-50 px-2.5 py-2 text-sm text-gray-700 placeholder:text-gray-400 resize-none overflow-hidden focus:outline-none focus:ring-1 focus:ring-blue-400 focus:border-blue-400 transition-colors"
                  />
                ) : (
                  <p className="mt-2.5 text-sm text-gray-600 leading-relaxed whitespace-pre-wrap">
                    {currentExplanation || <span className="italic text-gray-400">No explanation provided.</span>}
                  </p>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ─── Main Component ──────────────────────────────────────────

export function VideoReviewPanel({ videoId, funnels }: VideoReviewPanelProps) {
  const { status } = useSession();
  const isLoggedIn = status === 'authenticated';

  const [selectedFunnelId, setSelectedFunnelId] = useState<string | null>(
    funnels.length > 0 ? funnels[0].id : null
  );

  const [classNodeGroups, setClassNodeGroups] = useState<FunnelClassNodeGroup[]>([]);
  const [classNodeLoading, setClassNodeLoading] = useState(false);
  const [classNodeEdits, setClassNodeEdits] = useState<Map<string, ClassNodeResultEdit>>(new Map());

  const [reviewStates, setReviewStates] = useState<Map<string, FunnelReviewState>>(new Map());
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [generateError, setGenerateError] = useState<string | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const baseTextRef = useRef('');
  const feedbackRef = useRef<HTMLTextAreaElement | null>(null);

  const currentFunnelId = selectedFunnelId;
  const currentReview = currentFunnelId ? reviewStates.get(currentFunnelId) : null;
  const currentClassNodeGroup = classNodeGroups.find((g) => g.funnelId === currentFunnelId);

  const getDefaultReviewState = (): FunnelReviewState => ({
    rating: null,
    feedback: '',
    submitted: false,
    loaded: false,
  });

  const updateCurrentReview = (update: Partial<FunnelReviewState>) => {
    if (!currentFunnelId) return;
    setReviewStates((prev) => {
      const next = new Map(prev);
      const current = next.get(currentFunnelId) ?? getDefaultReviewState();
      next.set(currentFunnelId, { ...current, ...update });
      return next;
    });
  };

  const handleEditResult = (id: string, nextResult: 'PASS' | 'FAIL' | 'CANNOT_TELL') => {
    setClassNodeEdits((prev) => {
      const next = new Map(prev);
      const original = classNodeGroups.flatMap((g) => g.results).find((r) => r.id === id);
      if (original && nextResult === original.result) {
        next.delete(id);
      } else {
        next.set(id, { result: nextResult, explanation: null });
      }
      return next;
    });
    updateCurrentReview({ submitted: false });
  };

  const handleEditExplanation = (id: string, explanation: string) => {
    setClassNodeEdits((prev) => {
      const next = new Map(prev);
      const existing = next.get(id);
      const original = classNodeGroups.flatMap((g) => g.results).find((r) => r.id === id);
      next.set(id, {
        result: existing?.result ?? original?.result ?? 'CANNOT_TELL',
        explanation: explanation || null,
      });
      return next;
    });
    updateCurrentReview({ submitted: false });
  };

  const currentFeedback = currentReview?.feedback ?? '';
  useEffect(() => {
    const el = feedbackRef.current;
    if (el) { el.style.height = 'auto'; el.style.height = `${el.scrollHeight}px`; }
  }, [currentFeedback]);

  useEffect(() => { return () => { recognitionRef.current?.stop(); }; }, []);

  useEffect(() => {
    if (!isLoggedIn) return;
    const fetchResults = async () => {
      setClassNodeLoading(true);
      try {
        const response = await fetch(`/api/videos/${encodeURIComponent(videoId)}/class-node-results`);
        if (response.ok) {
          const data: FunnelClassNodeGroup[] = await response.json();
          setClassNodeGroups(data);
        }
      } catch { /* silently fail */ } finally {
        setClassNodeLoading(false);
      }
    };
    fetchResults();
  }, [isLoggedIn, videoId]);

  useEffect(() => {
    if (!isLoggedIn || !currentFunnelId) return;
    const existing = reviewStates.get(currentFunnelId);
    if (existing?.loaded) return;

    const fetchReview = async () => {
      try {
        const params = new URLSearchParams({ videoId, funnelId: currentFunnelId });
        const response = await fetch(`/api/reviews?${params.toString()}`);
        if (!response.ok) return;
        const data = await response.json();
        if (!data) {
          setReviewStates((prev) => { const next = new Map(prev); next.set(currentFunnelId, { ...getDefaultReviewState(), loaded: true }); return next; });
          return;
        }
        let parsedContent: { feedback?: string } = {};
        if (data.content) { try { parsedContent = JSON.parse(data.content); } catch { parsedContent = { feedback: data.content }; } }
        setReviewStates((prev) => {
          const next = new Map(prev);
          next.set(currentFunnelId, {
            rating: data.rating ?? null,
            feedback: parsedContent.feedback ?? '',
            submitted: !!data.rating,
            loaded: true,
          });
          return next;
        });
      } catch { /* silently fail */ }
    };
    fetchReview();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLoggedIn, videoId, currentFunnelId]);

  const toggleTranscription = useCallback(() => {
    if (isTranscribing) {
      recognitionRef.current?.stop();
      setIsTranscribing(false);
      return;
    }
    const SpeechRecognitionAPI = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognitionAPI) { alert('Speech recognition not supported.'); return; }
    baseTextRef.current = currentReview?.feedback ?? '';
    const recognition = new SpeechRecognitionAPI();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = 'en-US';
    recognition.onresult = (event: SpeechRecognitionEvent) => {
      let finalTranscript = '';
      let interimTranscript = '';
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        if (result.isFinal) finalTranscript += result[0].transcript;
        else interimTranscript += result[0].transcript;
      }
      if (finalTranscript) { const separator = baseTextRef.current ? ' ' : ''; baseTextRef.current += separator + finalTranscript.trim(); }
      const interimSuffix = interimTranscript ? (baseTextRef.current ? ' ' : '') + interimTranscript : '';
      updateCurrentReview({ feedback: baseTextRef.current + interimSuffix });
    };
    recognition.onerror = () => setIsTranscribing(false);
    recognition.onend = () => setIsTranscribing(false);
    recognitionRef.current = recognition;
    recognition.start();
    setIsTranscribing(true);
  }, [isTranscribing, currentReview?.feedback, updateCurrentReview]);

  const handleGenerateInnieReview = useCallback(async () => {
    if (!currentFunnelId || isGenerating) return;
    if (isTranscribing) { recognitionRef.current?.stop(); setIsTranscribing(false); }
    setIsGenerating(true);
    setGenerateError(null);
    updateCurrentReview({ feedback: '', submitted: false });
    const controller = new AbortController();
    abortControllerRef.current = controller;
    try {
      const response = await fetch(`/api/videos/${encodeURIComponent(videoId)}/innie-review`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ funnelId: currentFunnelId }),
        signal: controller.signal,
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({ error: 'Failed to generate review' }));
        throw new Error(data.error || 'Failed to generate review');
      }
      const reader = response.body?.getReader();
      if (!reader) throw new Error('No response stream');
      const decoder = new TextDecoder();
      let text = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        text += decoder.decode(value, { stream: true });
        updateCurrentReview({ feedback: text, submitted: false });
        baseTextRef.current = text;
      }
    } catch (error) {
      if ((error as Error).name !== 'AbortError') {
        setGenerateError(error instanceof Error ? error.message : 'Failed to generate review');
      }
    } finally {
      setIsGenerating(false);
      abortControllerRef.current = null;
    }
  }, [currentFunnelId, isGenerating, isTranscribing, videoId, updateCurrentReview]);

  useEffect(() => { return () => { abortControllerRef.current?.abort(); }; }, []);
  useEffect(() => {
    if (isTranscribing) { recognitionRef.current?.stop(); setIsTranscribing(false); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedFunnelId]);

  const handleSubmit = async () => {
    if (!isLoggedIn || !currentFunnelId) return;
    setIsSubmitting(true);
    setSubmitError(null);

    try {
      if (currentReview?.rating || currentReview?.feedback?.trim()) {
        const reviewResponse = await fetch('/api/reviews', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            videoId,
            funnelId: currentFunnelId,
            rating: currentReview?.rating ?? null,
            feedback: currentReview?.feedback?.trim() ?? '',
          }),
        });
        if (!reviewResponse.ok) {
          const data = await reviewResponse.json();
          throw new Error(data.error || 'Failed to save review');
        }
      }

      const currentNodeResultIds = new Set((currentClassNodeGroup?.results ?? []).map((r) => r.id));
      const editsForCurrentFunnel = Array.from(classNodeEdits.entries())
        .filter(([id]) => currentNodeResultIds.has(id))
        .map(([id, edit]) => ({ id, result: edit.result, explanation: edit.explanation }));

      if (editsForCurrentFunnel.length > 0) {
        const response = await fetch(`/api/videos/${encodeURIComponent(videoId)}/class-node-results`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ updates: editsForCurrentFunnel }),
        });
        if (!response.ok) {
          const data = await response.json();
          throw new Error(data.error || 'Failed to save class node updates');
        }
        setClassNodeGroups((prev) =>
          prev.map((group) => {
            if (group.funnelId !== currentFunnelId) return group;
            return {
              ...group,
              results: group.results.map((r) => {
                const edit = classNodeEdits.get(r.id);
                if (!edit) return r;
                return { ...r, result: edit.result, explanation: edit.explanation };
              }),
            };
          })
        );
        setClassNodeEdits((prev) => {
          const next = new Map(prev);
          for (const id of currentNodeResultIds) next.delete(id);
          return next;
        });
      }

      updateCurrentReview({ submitted: true });
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : 'Failed to save');
    } finally {
      setIsSubmitting(false);
    }
  };

  const rating = currentReview?.rating ?? null;
  const feedback = currentReview?.feedback ?? '';
  const submitted = currentReview?.submitted ?? false;
  const reviewLoaded = currentReview?.loaded ?? false;

  const currentNodeResultIds = new Set((currentClassNodeGroup?.results ?? []).map((r) => r.id));
  const hasEdits = Array.from(classNodeEdits.keys()).some((id) => currentNodeResultIds.has(id));
  const hasAnyChange = !submitted && (rating !== null || feedback !== '' || hasEdits);
  const canSubmit = isLoggedIn && !isSubmitting && hasAnyChange;

  if (funnels.length === 0) {
    return (
      <div className="bg-white border border-gray-200 rounded-xl p-5 sticky top-20">
        <div className="text-center py-8 text-gray-400">
          <p className="text-sm font-medium text-gray-500">No funnels</p>
          <p className="text-xs text-gray-400 mt-1">This video hasn&apos;t been classified under any funnel yet.</p>
        </div>
      </div>
    );
  }

  const isLoadingReview = isLoggedIn && currentFunnelId && !reviewLoaded;

  return (
    <div className="bg-white border border-gray-200 rounded-xl">
      {/* Funnel Tabs */}
      <div className="border-b border-gray-200 bg-gray-50 px-4 pt-4 pb-0">
        <div className="flex gap-1 overflow-x-auto scrollbar-none -mb-px">
          {funnels.map((funnel) => {
            const isActive = funnel.id === selectedFunnelId;
            return (
              <button
                key={funnel.id}
                type="button"
                onClick={() => setSelectedFunnelId(funnel.id)}
                className={cn(
                  'shrink-0 px-3.5 py-2 text-sm font-semibold rounded-t-lg border border-b-0 transition-colors cursor-pointer',
                  isActive
                    ? 'bg-white text-gray-900 border-gray-200'
                    : 'bg-transparent text-gray-500 border-transparent hover:text-gray-700 hover:bg-gray-100'
                )}
              >
                {funnel.name}
              </button>
            );
          })}
        </div>
      </div>

      <div className="p-5 space-y-6">
        {/* Class Node Results */}
        <div>
          <h3 className="text-sm font-semibold text-gray-700 mb-2.5">Classification Results</h3>
          {classNodeLoading ? (
            <div className="space-y-2">
              {[1, 2, 3].map((i) => <div key={i} className="animate-pulse rounded-lg bg-gray-100 h-12" />)}
            </div>
          ) : (
            <ClassNodeResults
              results={currentClassNodeGroup?.results ?? []}
              edits={classNodeEdits}
              onEditResult={handleEditResult}
              onEditExplanation={handleEditExplanation}
            />
          )}
        </div>

        {/* Review Form */}
        <div>
          <h3 className="text-sm font-semibold text-gray-700 mb-2.5">Did you enjoy this video?</h3>

          {isLoadingReview ? (
            <div className="flex items-center justify-center py-8">
              <div className="flex flex-col items-center gap-2 text-gray-400">
                <svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                <span className="text-sm">Loading review...</span>
              </div>
            </div>
          ) : (
            <div className="space-y-5">
              {/* Rating */}
              <div className="grid grid-cols-3 gap-2">
                {(['dislike', 'neutral', 'like'] as const).map((r) => (
                  <button
                    key={r}
                    type="button"
                    onClick={() => updateCurrentReview({ rating: r, submitted: false })}
                    className={cn(
                      'flex flex-col items-center gap-1.5 rounded-xl border-2 px-3 py-3 transition-all duration-150 hover:shadow-sm cursor-pointer',
                      rating === r
                        ? r === 'dislike' ? 'bg-red-50 border-red-300 text-red-700 shadow-sm'
                          : r === 'neutral' ? 'bg-amber-50 border-amber-300 text-amber-700 shadow-sm'
                          : 'bg-green-50 border-green-300 text-green-700 shadow-sm'
                        : 'bg-white border-gray-200 text-gray-500 hover:border-gray-300 hover:text-gray-700'
                    )}
                  >
                    <span className="text-xs font-medium">
                      {r === 'dislike' ? 'Not for me' : r === 'neutral' ? 'It was okay' : 'Enjoyed this!'}
                    </span>
                  </button>
                ))}
              </div>

              {/* Feedback */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <label htmlFor={`feedback-${videoId}-${currentFunnelId}`} className="text-sm font-semibold text-gray-700">
                    Any thoughts?
                  </label>
                  <button
                    type="button"
                    onClick={handleGenerateInnieReview}
                    disabled={isGenerating}
                    className={cn(
                      'inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium transition-all duration-150',
                      isGenerating
                        ? 'bg-purple-100 text-purple-500 cursor-wait'
                        : 'bg-purple-50 text-purple-600 hover:bg-purple-100 hover:text-purple-700 cursor-pointer border border-purple-200'
                    )}
                  >
                    {isGenerating ? 'Thinking...' : 'Ask your innie'}
                  </button>
                </div>
                {generateError && <p className="text-xs text-red-500">{generateError}</p>}
                <div className="relative">
                  <textarea
                    ref={feedbackRef}
                    id={`feedback-${videoId}-${currentFunnelId}`}
                    value={feedback}
                    onChange={(e) => {
                      updateCurrentReview({ feedback: e.target.value, submitted: false });
                      baseTextRef.current = e.target.value;
                      e.target.style.height = 'auto';
                      e.target.style.height = `${e.target.scrollHeight}px`;
                    }}
                    placeholder="Share your thoughts... (optional)"
                    rows={3}
                    className={cn(
                      'w-full rounded-lg border border-gray-300 bg-white px-3 py-2.5 text-sm text-gray-900',
                      'placeholder:text-gray-400 resize-none overflow-hidden',
                      'focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500',
                      isTranscribing && 'border-red-300 focus:ring-red-400 focus:border-red-400'
                    )}
                  />
                  <button
                    type="button"
                    onClick={toggleTranscription}
                    title={isTranscribing ? 'Stop recording' : 'Start voice input'}
                    className={cn(
                      'absolute bottom-2.5 right-2.5 p-1.5 rounded-full transition-all duration-150 cursor-pointer',
                      isTranscribing
                        ? 'bg-red-100 text-red-600 hover:bg-red-200 animate-pulse'
                        : 'bg-gray-100 text-gray-500 hover:bg-gray-200 hover:text-gray-700'
                    )}
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M12 18.75a6 6 0 0 0 6-6v-1.5m-6 7.5a6 6 0 0 1-6-6v-1.5m6 7.5v3.75m-3.75 0h7.5M12 15.75a3 3 0 0 1-3-3V4.5a3 3 0 1 1 6 0v8.25a3 3 0 0 1-3 3Z" />
                    </svg>
                  </button>
                </div>
              </div>

              {submitError && <p className="text-xs text-red-500">{submitError}</p>}
              <button
                type="button"
                onClick={handleSubmit}
                disabled={!canSubmit}
                className={cn(
                  'w-full rounded-lg py-2.5 px-4 text-sm font-medium transition-all duration-150',
                  !isLoggedIn
                    ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
                    : canSubmit && !submitted
                      ? 'bg-blue-600 text-white hover:bg-blue-700 active:bg-blue-800 cursor-pointer shadow-sm'
                      : submitted
                        ? 'bg-green-600 text-white cursor-default'
                        : 'bg-gray-100 text-gray-400 cursor-not-allowed'
                )}
              >
                {!isLoggedIn ? 'Please login to submit'
                  : isSubmitting ? 'Saving...'
                  : submitted ? 'Saved'
                  : 'Save review'}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
