'use client';

import { useState, useRef, useCallback, useEffect } from 'react';
import { useSession } from 'next-auth/react';
import { cn } from '@/lib/utils';
import { VideoTopic } from '@/types/youtube';

// ─── Types ───────────────────────────────────────────────────

interface VideoReviewPanelProps {
  videoId: string;
  topics: VideoTopic[];
}

type Rating = 'dislike' | 'neutral' | 'like' | null;
type LikeAspect = 'topic' | 'style' | 'quality';
type Signal = 'include' | 'exclude' | 'unclear';

interface CriterionResultItem {
  id: string;
  condition: string;
  include: boolean;
  level: string;
  result: 'PASS' | 'FAIL' | 'CANNOT_TELL';
  explanation: string | null;
}

interface CriterionEdit {
  result: 'PASS' | 'FAIL' | 'CANNOT_TELL';
  explanation: string | null;
}

interface TopicCriteriaGroup {
  topicId: string;
  topicName: string;
  results: CriterionResultItem[];
}

interface TopicReviewState {
  rating: Rating;
  likeAspects: Set<LikeAspect>;
  feedback: string;
  includeInTestSet: boolean;
  submitted: boolean;
  loaded: boolean;
}

const LIKE_ASPECTS: { value: LikeAspect; label: string; description: string }[] = [
  { value: 'topic', label: 'Topic', description: 'The subject was interesting' },
  { value: 'style', label: 'Style', description: 'Great presentation & delivery' },
  { value: 'quality', label: 'Quality', description: 'Well-produced content' },
];

// ─── Signal Helpers ──────────────────────────────────────────

/** Convert a raw PASS/FAIL/CANNOT_TELL + include flag → intuitive signal */
function toSignal(include: boolean, result: string): Signal {
  if (result === 'CANNOT_TELL') return 'unclear';
  if (include) return result === 'PASS' ? 'include' : 'exclude';
  return result === 'PASS' ? 'exclude' : 'include';
}

/** Convert an intuitive signal back to a raw result value */
function fromSignal(include: boolean, signal: 'include' | 'exclude'): 'PASS' | 'FAIL' {
  if (include) return signal === 'include' ? 'PASS' : 'FAIL';
  return signal === 'include' ? 'FAIL' : 'PASS';
}

// ─── Signal Badge (clickable toggle) ─────────────────────────

function SignalBadge({
  signal,
  onToggle,
}: {
  signal: Signal;
  onToggle: () => void;
}) {
  if (signal === 'include') {
    return (
      <button
        type="button"
        onClick={(e) => { e.stopPropagation(); onToggle(); }}
        title="Click to change to Exclude"
        className="inline-flex items-center justify-center rounded-full bg-green-100 text-green-700 p-1 hover:bg-green-200 transition-colors cursor-pointer shrink-0"
      >
        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" />
        </svg>
      </button>
    );
  }
  if (signal === 'exclude') {
    return (
      <button
        type="button"
        onClick={(e) => { e.stopPropagation(); onToggle(); }}
        title="Click to change to Include"
        className="inline-flex items-center justify-center rounded-full bg-red-100 text-red-700 p-1 hover:bg-red-200 transition-colors cursor-pointer shrink-0"
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
      title="Click to set to Include"
      className="inline-flex items-center justify-center rounded-full bg-amber-100 text-amber-700 p-1 hover:bg-amber-200 transition-colors cursor-pointer shrink-0"
    >
      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9.879 7.519c1.171-1.025 3.071-1.025 4.242 0 1.172 1.025 1.172 2.687 0 3.712-.203.179-.43.326-.67.442-.745.361-1.45.999-1.45 1.827v.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 5.25h.008v.008H12v-.008Z" />
      </svg>
    </button>
  );
}

// ─── Criteria Results Section (editable) ─────────────────────

function CriteriaResults({
  results,
  edits,
  onEditResult,
  onEditExplanation,
}: {
  results: CriterionResultItem[];
  edits: Map<string, CriterionEdit>;
  onEditResult: (id: string, include: boolean, newResult: 'PASS' | 'FAIL' | 'CANNOT_TELL') => void;
  onEditExplanation: (id: string, explanation: string) => void;
}) {
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());

  const toggleExpanded = (id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  if (results.length === 0) {
    return (
      <div className="text-sm text-gray-400 italic py-2">
        No evaluation results yet.
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {results.map((cr) => {
        const isExpanded = expandedIds.has(cr.id);
        const edit = edits.get(cr.id);
        const currentResult = edit?.result ?? cr.result;
        const verdictChanged = edit !== undefined && edit.result !== cr.result;
        const currentExplanation = verdictChanged
          ? (edit.explanation ?? '')
          : (edit?.explanation ?? cr.explanation ?? '');
        const signal = toSignal(cr.include, currentResult);

        const handleToggleSignal = () => {
          let newSignal: 'include' | 'exclude';
          if (signal === 'include') {
            newSignal = 'exclude';
          } else {
            newSignal = 'include';
          }
          const newResult = fromSignal(cr.include, newSignal);
          onEditResult(cr.id, cr.include, newResult);
        };

        return (
          <div
            key={cr.id}
            className="rounded-lg border border-gray-200 bg-gray-50 overflow-hidden"
          >
            <div
              role="button"
              tabIndex={0}
              onClick={() => toggleExpanded(cr.id)}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleExpanded(cr.id); } }}
              className="w-full flex items-start gap-2.5 px-3 py-2.5 text-left cursor-pointer hover:bg-gray-100 transition-colors"
            >
              <div className="shrink-0 mt-0.5">
                <SignalBadge signal={signal} onToggle={handleToggleSignal} />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm text-gray-800 leading-snug">
                  {cr.include ? '' : <span className="text-red-600 font-medium">(Not) </span>}
                  {cr.condition}
                </p>
                {cr.level === 'NICE_TO_HAVE' && (
                  <span className="text-xs text-gray-400 mt-0.5">Nice to have</span>
                )}
              </div>
              <svg
                className={cn(
                  'w-4 h-4 text-gray-400 shrink-0 mt-0.5 transition-transform duration-200',
                  isExpanded && 'rotate-180'
                )}
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
                strokeWidth={2}
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
                      onEditExplanation(cr.id, e.target.value);
                      e.target.style.height = 'auto';
                      e.target.style.height = `${e.target.scrollHeight}px`;
                    }}
                    ref={(el) => {
                      if (el) {
                        el.style.height = 'auto';
                        el.style.height = `${el.scrollHeight}px`;
                      }
                    }}
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

export function VideoReviewPanel({ videoId, topics }: VideoReviewPanelProps) {
  const { status } = useSession();
  const isLoggedIn = status === 'authenticated';

  // Selected topic
  const [selectedTopicId, setSelectedTopicId] = useState<string | null>(
    topics.length > 0 ? topics[0].id : null
  );

  // Criteria results (loaded once for all topics)
  const [criteriaGroups, setCriteriaGroups] = useState<TopicCriteriaGroup[]>([]);
  const [criteriaLoading, setCriteriaLoading] = useState(false);

  // Edits to criteria results: Map<criterionResultId, edit>
  const [criteriaEdits, setCriteriaEdits] = useState<Map<string, CriterionEdit>>(new Map());

  // Per-topic review state: Map<topicId, ReviewState>
  const [reviewStates, setReviewStates] = useState<Map<string, TopicReviewState>>(new Map());
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [isTranscribing, setIsTranscribing] = useState(false);

  // Innie generation state
  const [isGenerating, setIsGenerating] = useState(false);
  const [generateError, setGenerateError] = useState<string | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const baseTextRef = useRef('');

  // Helpers to get/set current topic review state
  const currentTopicId = selectedTopicId;
  const currentReview = currentTopicId ? reviewStates.get(currentTopicId) : null;
  const currentCriteria = criteriaGroups.find((g) => g.topicId === currentTopicId);

  const getDefaultReviewState = (): TopicReviewState => ({
    rating: null,
    likeAspects: new Set(),
    feedback: '',
    includeInTestSet: false,
    submitted: false,
    loaded: false,
  });

  const updateCurrentReview = (update: Partial<TopicReviewState>) => {
    if (!currentTopicId) return;
    setReviewStates((prev) => {
      const next = new Map(prev);
      const current = next.get(currentTopicId) ?? getDefaultReviewState();
      next.set(currentTopicId, { ...current, ...update });
      return next;
    });
  };

  // ─── Criteria edit handlers ──────────────────────────────────

  const handleEditCriterionResult = (id: string, _include: boolean, newResult: 'PASS' | 'FAIL' | 'CANNOT_TELL') => {
    setCriteriaEdits((prev) => {
      const next = new Map(prev);
      const original = criteriaGroups.flatMap((g) => g.results).find((r) => r.id === id);
      // If reverting back to the original result, remove the edit entirely
      if (original && newResult === original.result) {
        next.delete(id);
      } else {
        // Verdict changed — clear explanation so user can provide a new reason
        next.set(id, {
          result: newResult,
          explanation: null,
        });
      }
      return next;
    });
    updateCurrentReview({ submitted: false });
  };

  const handleEditCriterionExplanation = (id: string, explanation: string) => {
    setCriteriaEdits((prev) => {
      const next = new Map(prev);
      const existing = next.get(id);
      const original = criteriaGroups.flatMap((g) => g.results).find((r) => r.id === id);
      next.set(id, {
        result: existing?.result ?? original?.result ?? 'CANNOT_TELL',
        explanation: explanation || null,
      });
      return next;
    });
    updateCurrentReview({ submitted: false });
  };

  // Clean up speech recognition on unmount
  useEffect(() => {
    return () => {
      recognitionRef.current?.stop();
    };
  }, []);

  // Fetch criteria results once
  useEffect(() => {
    if (!isLoggedIn) return;

    const fetchCriteria = async () => {
      setCriteriaLoading(true);
      try {
        const response = await fetch(`/api/videos/${encodeURIComponent(videoId)}/criteria-results`);
        if (response.ok) {
          const data: TopicCriteriaGroup[] = await response.json();
          setCriteriaGroups(data);
        }
      } catch {
        // silently fail
      } finally {
        setCriteriaLoading(false);
      }
    };

    fetchCriteria();
  }, [isLoggedIn, videoId]);

  // Fetch review for the selected topic (when topic changes)
  useEffect(() => {
    if (!isLoggedIn || !currentTopicId) return;

    // Skip if already loaded
    const existing = reviewStates.get(currentTopicId);
    if (existing?.loaded) return;

    const fetchReview = async () => {
      try {
        const params = new URLSearchParams({ videoId });
        if (currentTopicId) {
          params.set('topicId', currentTopicId);
        }
        const response = await fetch(`/api/reviews?${params.toString()}`);
        if (!response.ok) return;

        const data = await response.json();
        if (!data) {
          // No review yet, just mark as loaded
          setReviewStates((prev) => {
            const next = new Map(prev);
            next.set(currentTopicId, { ...getDefaultReviewState(), loaded: true });
            return next;
          });
          return;
        }

        setReviewStates((prev) => {
          const next = new Map(prev);
          next.set(currentTopicId, {
            rating: (data.rating as Rating) ?? null,
            likeAspects: new Set((data.likeAspects as LikeAspect[]) ?? []),
            feedback: data.feedback ?? '',
            includeInTestSet: data.includeInTestSet ?? false,
            submitted: !!data.rating,
            loaded: true,
          });
          return next;
        });
      } catch {
        // silently fail
      }
    };

    fetchReview();
  }, [isLoggedIn, videoId, currentTopicId, reviewStates]);

  const handleRatingChange = (newRating: Rating) => {
    updateCurrentReview({
      rating: newRating,
      likeAspects: newRating !== 'like' ? new Set() : currentReview?.likeAspects,
      submitted: false,
    });
  };

  const toggleAspect = (aspect: LikeAspect) => {
    if (!currentReview) return;
    const next = new Set(currentReview.likeAspects);
    if (next.has(aspect)) {
      next.delete(aspect);
    } else {
      next.add(aspect);
    }
    updateCurrentReview({ likeAspects: next });
  };

  const toggleTranscription = useCallback(() => {
    if (isTranscribing) {
      recognitionRef.current?.stop();
      setIsTranscribing(false);
      return;
    }

    const SpeechRecognitionAPI =
      window.SpeechRecognition || window.webkitSpeechRecognition;

    if (!SpeechRecognitionAPI) {
      alert('Speech recognition is not supported in your browser. Try Chrome or Edge.');
      return;
    }

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
        if (result.isFinal) {
          finalTranscript += result[0].transcript;
        } else {
          interimTranscript += result[0].transcript;
        }
      }

      if (finalTranscript) {
        const separator = baseTextRef.current ? ' ' : '';
        baseTextRef.current += separator + finalTranscript.trim();
      }

      const interimSuffix = interimTranscript
        ? (baseTextRef.current ? ' ' : '') + interimTranscript
        : '';
      updateCurrentReview({ feedback: baseTextRef.current + interimSuffix });
    };

    recognition.onerror = () => {
      setIsTranscribing(false);
    };

    recognition.onend = () => {
      setIsTranscribing(false);
    };

    recognitionRef.current = recognition;
    recognition.start();
    setIsTranscribing(true);
  }, [isTranscribing, currentReview?.feedback, updateCurrentReview]);

  const handleGenerateInnieReview = useCallback(async () => {
    if (!currentTopicId || isGenerating) return;

    // Stop any active transcription
    if (isTranscribing) {
      recognitionRef.current?.stop();
      setIsTranscribing(false);
    }

    setIsGenerating(true);
    setGenerateError(null);
    updateCurrentReview({ feedback: '', submitted: false });

    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      const response = await fetch(
        `/api/videos/${encodeURIComponent(videoId)}/innie-review`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ topicId: currentTopicId }),
          signal: controller.signal,
        }
      );

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
        setGenerateError(
          error instanceof Error ? error.message : 'Failed to generate review'
        );
      }
    } finally {
      setIsGenerating(false);
      abortControllerRef.current = null;
    }
  }, [currentTopicId, isGenerating, isTranscribing, videoId, updateCurrentReview]);

  // Clean up generation on unmount
  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
    };
  }, []);

  // Stop transcription when topic changes
  useEffect(() => {
    if (isTranscribing) {
      recognitionRef.current?.stop();
      setIsTranscribing(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedTopicId]);

  const handleSubmit = async () => {
    if (!isLoggedIn || !currentTopicId) return;

    setIsSubmitting(true);
    setSubmitError(null);

    try {
      // 1. Save review (only if there's a rating or feedback)
      if (currentReview?.rating || currentReview?.feedback?.trim()) {
        const reviewResponse = await fetch('/api/reviews', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            videoId,
            topicId: currentTopicId,
            rating: currentReview?.rating ?? null,
            likeAspects: currentReview?.rating === 'like' ? Array.from(currentReview.likeAspects) : [],
            feedback: currentReview?.feedback?.trim() ?? '',
            includeInTestSet: currentReview?.includeInTestSet ?? false,
          }),
        });

        if (!reviewResponse.ok) {
          const data = await reviewResponse.json();
          throw new Error(data.error || 'Failed to save review');
        }
      }

      // 2. Save criteria edits (only those belonging to the current topic)
      const submitTopicResultIds = new Set(
        (currentCriteria?.results ?? []).map((r) => r.id)
      );
      const editsForCurrentTopic = Array.from(criteriaEdits.entries())
        .filter(([id]) => submitTopicResultIds.has(id))
        .map(([id, edit]) => ({
          id,
          result: edit.result,
          explanation: edit.explanation,
        }));

      if (editsForCurrentTopic.length > 0) {
        const criteriaResponse = await fetch(
          `/api/videos/${encodeURIComponent(videoId)}/criteria-results`,
          {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ updates: editsForCurrentTopic }),
          }
        );

        if (!criteriaResponse.ok) {
          const data = await criteriaResponse.json();
          throw new Error(data.error || 'Failed to save criteria updates');
        }

        // Update local criteriaGroups state with saved edits
        setCriteriaGroups((prev) =>
          prev.map((group) => {
            if (group.topicId !== currentTopicId) return group;
            return {
              ...group,
              results: group.results.map((r) => {
                const edit = criteriaEdits.get(r.id);
                if (!edit) return r;
                return { ...r, result: edit.result, explanation: edit.explanation };
              }),
            };
          })
        );

        // Clear saved edits for these IDs
        setCriteriaEdits((prev) => {
          const next = new Map(prev);
          for (const id of submitTopicResultIds) {
            next.delete(id);
          }
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

  // Review state for current topic
  const rating = currentReview?.rating ?? null;
  const likeAspects = currentReview?.likeAspects ?? new Set<LikeAspect>();
  const feedback = currentReview?.feedback ?? '';
  const includeInTestSet = currentReview?.includeInTestSet ?? false;
  const submitted = currentReview?.submitted ?? false;
  const reviewLoaded = currentReview?.loaded ?? false;

  const currentTopicResultIds = new Set(
    (currentCriteria?.results ?? []).map((r) => r.id)
  );
  const hasCriteriaEdits = Array.from(criteriaEdits.keys()).some((id) => currentTopicResultIds.has(id));
  const hasAnyChange = !submitted && (rating !== null || feedback !== '' || hasCriteriaEdits || likeAspects.size > 0 || includeInTestSet);
  const canSubmit = isLoggedIn && !isSubmitting && hasAnyChange;

  // No topics state
  if (topics.length === 0) {
    return (
      <div className="bg-white border border-gray-200 rounded-xl p-5 sticky top-20">
        <div className="text-center py-8 text-gray-400">
          <svg className="w-10 h-10 mx-auto mb-2 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9.568 3H5.25A2.25 2.25 0 0 0 3 5.25v4.318c0 .597.237 1.17.659 1.591l9.581 9.581c.699.699 1.78.872 2.607.33a18.095 18.095 0 0 0 5.223-5.223c.542-.827.369-1.908-.33-2.607L11.16 3.66A2.25 2.25 0 0 0 9.568 3Z" />
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 6h.008v.008H6V6Z" />
          </svg>
          <p className="text-sm font-medium text-gray-500">No topics</p>
          <p className="text-xs text-gray-400 mt-1">
            This video hasn&apos;t been classified under any topic yet.
          </p>
        </div>
      </div>
    );
  }

  // Loading state (before review loads for current topic)
  const isLoadingReview = isLoggedIn && currentTopicId && !reviewLoaded;

  return (
    <div className="bg-white border border-gray-200 rounded-xl">
      {/* Topic Tabs */}
      <div className="border-b border-gray-200 bg-gray-50 px-4 pt-4 pb-0">
        <div className="flex gap-1 overflow-x-auto scrollbar-none -mb-px">
          {topics.map((topic) => {
            const isActive = topic.id === selectedTopicId;
            return (
              <button
                key={topic.id}
                type="button"
                onClick={() => setSelectedTopicId(topic.id)}
                className={cn(
                  'shrink-0 px-3.5 py-2 text-sm font-semibold rounded-t-lg border border-b-0 transition-colors cursor-pointer',
                  isActive
                    ? 'bg-white text-gray-900 border-gray-200'
                    : 'bg-transparent text-gray-500 border-transparent hover:text-gray-700 hover:bg-gray-100'
                )}
              >
                {topic.name}
              </button>
            );
          })}
        </div>
      </div>

      <div className="p-5 space-y-6">
        {/* Criteria Results */}
        <div>
          <h3 className="text-sm font-semibold text-gray-700 mb-2.5">
            Why this video is included in this topic?
          </h3>
          {criteriaLoading ? (
            <div className="space-y-2">
              {[1, 2, 3].map((i) => (
                <div key={i} className="animate-pulse rounded-lg bg-gray-100 h-12" />
              ))}
            </div>
          ) : (
            <CriteriaResults
              results={currentCriteria?.results ?? []}
              edits={criteriaEdits}
              onEditResult={handleEditCriterionResult}
              onEditExplanation={handleEditCriterionExplanation}
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
              {/* Rating Selection */}
              <div className="grid grid-cols-3 gap-2">
                {/* Not for me */}
                <button
                  type="button"
                  onClick={() => handleRatingChange('dislike')}
                  className={cn(
                    'flex flex-col items-center gap-1.5 rounded-xl border-2 px-3 py-3 transition-all duration-150',
                    'hover:shadow-sm cursor-pointer',
                    rating === 'dislike'
                      ? 'bg-red-50 border-red-300 text-red-700 shadow-sm'
                      : 'bg-white border-gray-200 text-gray-500 hover:border-gray-300 hover:text-gray-700'
                  )}
                >
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M7.498 15.25H4.372c-1.026 0-1.945-.694-2.054-1.715a12.137 12.137 0 0 1-.068-1.285c0-2.848.992-5.464 2.649-7.521C5.287 4.247 5.886 4 6.504 4h4.016a4.5 4.5 0 0 1 1.423.23l3.114 1.04a4.5 4.5 0 0 0 1.423.23h1.294M7.498 15.25c.618 0 .991.724.725 1.282A7.471 7.471 0 0 0 7.5 19.75 2.25 2.25 0 0 0 9.75 22a.75.75 0 0 0 .75-.75v-.633c0-.573.11-1.14.322-1.672.304-.76.93-1.33 1.653-1.715a9.04 9.04 0 0 0 2.86-2.4c.498-.634 1.226-1.08 2.032-1.08h.384" />
                  </svg>
                  <span className="text-xs font-medium leading-tight text-center">Not for me</span>
                </button>

                {/* It was okay */}
                <button
                  type="button"
                  onClick={() => handleRatingChange('neutral')}
                  className={cn(
                    'flex flex-col items-center gap-1.5 rounded-xl border-2 px-3 py-3 transition-all duration-150',
                    'hover:shadow-sm cursor-pointer',
                    rating === 'neutral'
                      ? 'bg-amber-50 border-amber-300 text-amber-700 shadow-sm'
                      : 'bg-white border-gray-200 text-gray-500 hover:border-gray-300 hover:text-gray-700'
                  )}
                >
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M15.182 15.182a4.5 4.5 0 0 1-6.364 0M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0ZM9.75 9.75c0 .414-.168.75-.375.75S9 10.164 9 9.75 9.168 9 9.375 9s.375.336.375.75Zm-.375 0h.008v.015h-.008V9.75Zm5.625 0c0 .414-.168.75-.375.75s-.375-.336-.375-.75.168-.75.375-.75.375.336.375.75Zm-.375 0h.008v.015h-.008V9.75Z" />
                  </svg>
                  <span className="text-xs font-medium leading-tight text-center">It was okay</span>
                </button>

                {/* Enjoyed this */}
                <button
                  type="button"
                  onClick={() => handleRatingChange('like')}
                  className={cn(
                    'flex flex-col items-center gap-1.5 rounded-xl border-2 px-3 py-3 transition-all duration-150',
                    'hover:shadow-sm cursor-pointer',
                    rating === 'like'
                      ? 'bg-green-50 border-green-300 text-green-700 shadow-sm'
                      : 'bg-white border-gray-200 text-gray-500 hover:border-gray-300 hover:text-gray-700'
                  )}
                >
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6.633 10.25c.806 0 1.533-.446 2.031-1.08a9.041 9.041 0 0 1 2.861-2.4c.723-.384 1.35-.956 1.653-1.715a4.498 4.498 0 0 0 .322-1.672V2.75a.75.75 0 0 1 .75-.75 2.25 2.25 0 0 1 2.25 2.25c0 1.152-.26 2.243-.723 3.218-.266.558.107 1.282.725 1.282h3.126c1.026 0 1.945.694 2.054 1.715.045.422.068.85.068 1.285a11.95 11.95 0 0 1-2.649 7.521c-.388.482-.987.729-1.605.729H13.48a4.5 4.5 0 0 1-1.423-.23l-3.114-1.04a4.5 4.5 0 0 0-1.423-.23H6.332" />
                  </svg>
                  <span className="text-xs font-medium leading-tight text-center">Enjoyed this!</span>
                </button>
              </div>

              {/* Like Aspects */}
              {/* {rating === 'like' && (
                <div className="space-y-2.5 animate-in fade-in slide-in-from-top-2 duration-200">
                  <label className="text-sm font-medium text-gray-700">
                    What did you enjoy most?
                  </label>
                  <div className="flex flex-wrap gap-2">
                    {LIKE_ASPECTS.map((aspect) => {
                      const selected = likeAspects.has(aspect.value);
                      return (
                        <button
                          key={aspect.value}
                          type="button"
                          onClick={() => toggleAspect(aspect.value)}
                          className={cn(
                            'inline-flex items-center gap-1.5 rounded-full border px-3.5 py-1.5 text-sm transition-all duration-150 cursor-pointer',
                            selected
                              ? 'bg-green-100 border-green-300 text-green-800 font-medium'
                              : 'bg-gray-50 border-gray-200 text-gray-600 hover:bg-gray-100 hover:border-gray-300'
                          )}
                        >
                          {selected && (
                            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2.5}>
                              <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" />
                            </svg>
                          )}
                          {aspect.label}
                        </button>
                      );
                    })}
                  </div>
                  <p className="text-xs text-gray-400">Select all that apply</p>
                </div>
              )} */}

              {/* Feedback Textarea */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <label
                    htmlFor={`feedback-${videoId}-${currentTopicId}`}
                    className="text-sm font-semibold text-gray-700"
                  >
                    {rating === 'like'
                      ? 'What made this video great?'
                      : rating === 'dislike'
                        ? 'What could be better?'
                        : 'Any thoughts on this video?'}
                  </label>
                  <button
                    type="button"
                    onClick={handleGenerateInnieReview}
                    disabled={isGenerating}
                    className={cn(
                      'inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium transition-all duration-150',
                      isGenerating
                        ? 'bg-purple-100 text-purple-500 cursor-wait'
                        : 'bg-purple-50 text-purple-600 hover:bg-purple-100 hover:text-purple-700 cursor-pointer border border-purple-200 hover:border-purple-300'
                    )}
                  >
                    {isGenerating ? (
                      <>
                        <svg className="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                        </svg>
                        Thinking...
                      </>
                    ) : (
                      <>
                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09ZM18.259 8.715 18 9.75l-.259-1.035a3.375 3.375 0 0 0-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 0 0 2.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 0 0 2.455 2.456L21.75 6l-1.036.259a3.375 3.375 0 0 0-2.455 2.456Z" />
                        </svg>
                        Ask your innie
                      </>
                    )}
                  </button>
                </div>
                {generateError && (
                  <p className="text-xs text-red-500">{generateError}</p>
                )}
                <div className="relative">
                  <textarea
                    id={`feedback-${videoId}-${currentTopicId}`}
                    value={feedback}
                    onChange={(e) => {
                      updateCurrentReview({ feedback: e.target.value, submitted: false });
                      baseTextRef.current = e.target.value;
                    }}
                    placeholder={
                      rating === 'like'
                        ? 'e.g. I loved how they explained the concept...'
                        : rating === 'dislike'
                          ? 'e.g. The pacing felt too slow for me...'
                          : 'Share your thoughts... (optional)'
                    }
                    rows={3}
                    className={cn(
                      'w-full rounded-lg border border-gray-300 bg-white px-3 py-2.5 text-sm text-gray-900',
                      'placeholder:text-gray-400 resize-none',
                      'focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500',
                      'transition-colors duration-150',
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
                    {isTranscribing ? (
                      <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                        <rect x="6" y="6" width="12" height="12" rx="1" />
                      </svg>
                    ) : (
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.5}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M12 18.75a6 6 0 0 0 6-6v-1.5m-6 7.5a6 6 0 0 1-6-6v-1.5m6 7.5v3.75m-3.75 0h7.5M12 15.75a3 3 0 0 1-3-3V4.5a3 3 0 1 1 6 0v8.25a3 3 0 0 1-3 3Z" />
                      </svg>
                    )}
                  </button>
                </div>
                {isTranscribing && (
                  <p className="text-xs text-red-500 flex items-center gap-1">
                    <span className="inline-block w-1.5 h-1.5 bg-red-500 rounded-full animate-pulse" />
                    Listening... speak now
                  </p>
                )}
              </div>

              {/* Add to Gold Standard Toggle */}
              <div className="flex items-center justify-between py-2 px-1">
                <div className="space-y-0.5">
                  <label
                    htmlFor={`test-set-${videoId}-${currentTopicId}`}
                    className="text-sm font-semibold text-gray-700 cursor-pointer"
                  >
                    Add to gold standard
                  </label>
                  <p className="text-xs text-gray-400">
                    use this video to optimize the criteria prompt
                  </p>
                </div>
                <button
                  id={`test-set-${videoId}-${currentTopicId}`}
                  type="button"
                  role="switch"
                  aria-checked={includeInTestSet}
                  onClick={() => {
                    updateCurrentReview({ includeInTestSet: !includeInTestSet, submitted: false });
                  }}
                  className={cn(
                    'relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent',
                    'transition-colors duration-200 ease-in-out',
                    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2',
                    includeInTestSet ? 'bg-blue-600' : 'bg-gray-200'
                  )}
                >
                  <span
                    aria-hidden="true"
                    className={cn(
                      'pointer-events-none inline-block h-5 w-5 rounded-full bg-white shadow-sm ring-0',
                      'transition-transform duration-200 ease-in-out',
                      includeInTestSet ? 'translate-x-5' : 'translate-x-0'
                    )}
                  />
                </button>
              </div>

              {/* Submit Button */}
              {submitError && (
                <p className="text-xs text-red-500">{submitError}</p>
              )}
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
                {!isLoggedIn ? (
                  'Please login to submit'
                ) : isSubmitting ? (
                  <span className="inline-flex items-center gap-1.5">
                    <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                    Saving...
                  </span>
                ) : submitted ? (
                  <span className="inline-flex items-center gap-1.5">
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" />
                    </svg>
                    Saved
                  </span>
                ) : (
                  'Save review'
                )}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
