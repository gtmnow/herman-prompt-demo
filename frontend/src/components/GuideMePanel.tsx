import { useEffect, useState } from "react";

type GuideMeRequirementIndicator = {
  label: string;
  state: "met" | "partial" | "missing";
  heuristicScore?: number | null;
  llmScore?: number | null;
  maxScore?: number | null;
  reason?: string | null;
  improvementHint?: string | null;
};

export type GuideMeSession = {
  sessionId: string;
  conversationId: string;
  status: "active" | "complete" | "cancelled";
  currentStep: "intro" | "describe_need" | "who" | "why" | "how" | "what" | "refine" | "complete" | "cancelled";
  questionTitle?: string | null;
  questionText?: string | null;
  answers: Record<string, string>;
  requirements: Record<string, GuideMeRequirementIndicator>;
  requirementDebug?: Record<string, Record<string, unknown>>;
  decisionTrace?: Record<string, unknown>;
  personalization: {
    firstName: string;
    typicalAiUsage: string;
    profileLabel: string;
    recentExamples: string[];
  };
  guidanceText?: string | null;
  followUpQuestions: string[];
  finalPrompt?: string | null;
  readyToInsert: boolean;
};

type GuideMeUsePromptMode = "final" | "as-is";
type GuideMePendingAction = "launch" | "submit" | "cancel" | null;

type GuideMePanelProps = {
  answer: string;
  busy: boolean;
  pendingAction: GuideMePendingAction;
  submitProgressPercent: number | null;
  error: string | null;
  open: boolean;
  session: GuideMeSession | null;
  showDetails: boolean;
  onAnswerChange: (value: string) => void;
  onCancel: () => void;
  onClose: () => void;
  onLaunch: () => void;
  onRestart: () => void;
  onSubmit: () => void;
  onUsePrompt: (mode: GuideMeUsePromptMode) => void;
};

export function GuideMePanel({
  answer,
  busy,
  pendingAction,
  submitProgressPercent,
  error,
  open,
  session,
  showDetails,
  onAnswerChange,
  onCancel,
  onClose,
  onLaunch,
  onRestart,
  onSubmit,
  onUsePrompt,
}: GuideMePanelProps) {
  const [showPromptPreview, setShowPromptPreview] = useState(false);
  const [confirmUseAsIs, setConfirmUseAsIs] = useState(false);

  const scoreSummary = getGuideMeScoreSummary(session?.decisionTrace);
  const progressState = getGuideMeSubmitProgressState(session, submitProgressPercent);

  useEffect(() => {
    if (!open) {
      setShowPromptPreview(false);
      setConfirmUseAsIs(false);
    }
  }, [open]);

  useEffect(() => {
    if (!session?.finalPrompt) {
      setShowPromptPreview(false);
      setConfirmUseAsIs(false);
    }
  }, [session?.finalPrompt]);

  if (!open) {
    return null;
  }

  return (
    <div className="modal-backdrop" role="presentation">
      <section aria-modal="true" className="guide-me-panel" role="dialog">
        <div className="guide-me-panel-header">
          <div>
            <div className="guide-me-panel-label">Guide Me</div>
            <h3 className="guide-me-panel-title">
              {session?.questionTitle ?? "Start guided prompting"}
            </h3>
          </div>
          <div className="guide-me-panel-toolbar">
            {session ? (
              <button className="feedback-button" disabled={busy} type="button" onClick={onRestart}>
                Restart
              </button>
            ) : null}
            <button className="modal-close" type="button" onClick={onClose}>
              Close
            </button>
          </div>
        </div>

        {session ? (
          <>
            <GuideIndicators requirements={session.requirements} />
            {pendingAction === "submit" ? <GuideMeBusyStatus progressState={progressState} /> : null}

            {session.questionText ? <div className="guide-me-question">{session.questionText}</div> : null}
            {session.currentStep === "refine" && session.guidanceText ? (
              <div className="guide-me-guidance">{session.guidanceText}</div>
            ) : null}
            {session.currentStep === "refine" && session.followUpQuestions.length > 0 ? (
              <div className="guide-me-options">
                {session.followUpQuestions.map((option, index) => (
                  <div key={`${index + 1}-${option}`} className="guide-me-option">
                    <span className="guide-me-option-number">{index + 1}.</span>
                    <span>{option}</span>
                  </div>
                ))}
              </div>
            ) : null}

            {showDetails && session.requirementDebug && Object.keys(session.requirementDebug).length > 0 ? (
              <details className="guide-me-debug">
                <summary>Requirement Debug</summary>
                <pre className="guide-me-debug-pre">
                  {JSON.stringify(session.requirementDebug, null, 2)}
                </pre>
              </details>
            ) : null}

            {showDetails && session.decisionTrace && Object.keys(session.decisionTrace).length > 0 ? (
              <details className="guide-me-debug">
                <summary>Decision Trace</summary>
                <pre className="guide-me-debug-pre">
                  {JSON.stringify(session.decisionTrace, null, 2)}
                </pre>
              </details>
            ) : null}

            {showPromptPreview && session.finalPrompt ? (
              <div className="guide-me-preview-modal" role="dialog" aria-modal="false" aria-label="Current prompt draft">
                <div className="guide-me-preview-header">
                  <div className="guide-me-preview-title-row">
                    <div className="guide-me-meta-label">
                      {session.readyToInsert ? "Formatted prompt" : "Current prompt draft"}
                    </div>
                    {scoreSummary ? (
                      <div className="guide-me-score-chip" aria-label="Current prompt scores">
                        <span className="guide-me-score-chip-label">Score</span>
                        <span className="guide-me-score-chip-value">{scoreSummary.finalScore}/100</span>
                        {scoreSummary.finalLlmScore !== null ? (
                          <>
                            <span className="guide-me-score-chip-separator">•</span>
                            <span className="guide-me-score-chip-label">AI</span>
                            <span className="guide-me-score-chip-value">{scoreSummary.finalLlmScore}/100</span>
                          </>
                        ) : null}
                        {scoreSummary.structuralScore !== null ? (
                          <>
                            <span className="guide-me-score-chip-separator">•</span>
                            <span className="guide-me-score-chip-label">Structure</span>
                            <span className="guide-me-score-chip-value">{scoreSummary.structuralScore}/100</span>
                          </>
                        ) : null}
                      </div>
                    ) : null}
                    {!session.readyToInsert ? (
                      <button
                        className="feedback-button"
                        disabled={busy}
                        type="button"
                        onClick={() => setConfirmUseAsIs(true)}
                      >
                        Use AS-IS
                      </button>
                    ) : null}
                  </div>
                  <button
                    className="feedback-button"
                    disabled={busy}
                    type="button"
                    onClick={() => setShowPromptPreview(false)}
                  >
                    Hide
                  </button>
                </div>
                {confirmUseAsIs ? (
                  <div className="guide-me-confirm-panel">
                    <div className="guide-me-confirm-text">
                      Use the current draft as-is and move it into the main composer?
                    </div>
                    <div className="guide-me-confirm-actions">
                      <button
                        className="send-button"
                        disabled={busy}
                        type="button"
                        onClick={() => onUsePrompt("as-is")}
                      >
                        Yes, use this prompt
                      </button>
                      <button
                        className="feedback-button"
                        disabled={busy}
                        type="button"
                        onClick={() => setConfirmUseAsIs(false)}
                      >
                        Keep editing
                      </button>
                    </div>
                  </div>
                ) : null}
                <pre className="guide-me-final-prompt">{session.finalPrompt}</pre>
              </div>
            ) : null}

            {session.readyToInsert && session.finalPrompt ? (
              <div className="guide-me-final">
                <div className="guide-me-meta-label">Formatted prompt</div>
                <pre className="guide-me-final-prompt">{session.finalPrompt}</pre>
              </div>
            ) : (
              <label className="guide-me-answer-field">
                <span className="guide-me-meta-label">Your answer</span>
                <textarea
                  className="guide-me-answer-input"
                  disabled={busy}
                  rows={5}
                  value={answer}
                  onChange={(event) => onAnswerChange(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && !event.shiftKey) {
                      event.preventDefault();
                      onSubmit();
                    }
                  }}
                />
              </label>
            )}

            {error ? <div className="error-banner">{error}</div> : null}

            <div className="guide-me-actions">
              {pendingAction === "submit" ? (
                <div className="guide-me-actions-status" aria-live="polite" aria-atomic="true">
                  <div className="guide-me-inline-spinner" aria-hidden="true" />
                  <span>
                    Updating
                    {progressState.percent !== null ? ` (${progressState.percent}%)` : "..."}
                  </span>
                  {progressState.percent !== null ? (
                    <div className="guide-me-actions-progress-track" aria-hidden="true">
                      <div className="guide-me-actions-progress-fill" style={{ width: `${progressState.percent}%` }} />
                    </div>
                  ) : null}
                </div>
              ) : null}
              {session.finalPrompt ? (
                <button
                  className="feedback-button"
                  disabled={busy}
                  type="button"
                  onClick={() => setShowPromptPreview((current) => !current)}
                >
                  {showPromptPreview ? "Hide Prompt" : "View Prompt"}
                </button>
              ) : null}
              {session.readyToInsert ? (
                <button className="send-button" type="button" onClick={() => onUsePrompt("final")}>
                  Use Prompt
                </button>
              ) : (
                <button className="send-button" disabled={busy || !answer.trim()} type="button" onClick={onSubmit}>
                  {pendingAction === "submit" ? "Updating..." : "Continue"}
                </button>
              )}
              <button className="feedback-button" disabled={busy} type="button" onClick={onCancel}>
                Cancel
              </button>
            </div>
          </>
        ) : (
          <div className="guide-me-empty">
            {busy ? (
              <>
                <div className="guide-me-loading-indicator" aria-hidden="true" />
                <p>Starting Guide Me and loading your current prompt context...</p>
              </>
            ) : (
              <>
                <p>Start a guided session to build a structured prompt with personalized coaching.</p>
                <button className="send-button" disabled={busy} type="button" onClick={onLaunch}>
                  Launch Guide Me
                </button>
              </>
            )}
          </div>
        )}
      </section>
    </div>
  );
}

function getGuideMeScoreSummary(decisionTrace?: Record<string, unknown>) {
  if (!decisionTrace) {
    return null;
  }

  const finalScore = asNumber(decisionTrace.final_score);
  const finalLlmScore = asNumber(decisionTrace.final_llm_score);
  const structuralScore = asNumber(decisionTrace.structural_score);

  if (finalScore === null && finalLlmScore === null && structuralScore === null) {
    return null;
  }

  return {
    finalScore,
    finalLlmScore,
    structuralScore,
  };
}

function asNumber(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function GuideMeBusyStatus({
  progressState,
}: {
  progressState: { percent: number | null; label: string };
}) {
  return (
    <div className="guide-me-busy-status" aria-live="polite" aria-atomic="true">
      <div className="guide-me-busy-status-row">
        <div className="guide-me-busy-status-copy">
          <div className="guide-me-meta-label">In progress</div>
          <div className="guide-me-busy-status-text">{progressState.label}</div>
        </div>
        <div className="guide-me-busy-status-spinner" aria-hidden="true" />
      </div>
      {progressState.percent !== null ? (
        <div
          className="guide-me-progress"
          role="progressbar"
          aria-label="Guide Me submit progress"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={clampPercent(progressState.percent) ?? undefined}
        >
          <div className="guide-me-progress-track">
            <div className="guide-me-progress-fill" style={{ width: `${clampPercent(progressState.percent)}%` }} />
          </div>
          <div className="guide-me-progress-value">{clampPercent(progressState.percent)}% complete</div>
        </div>
      ) : null}
    </div>
  );
}

function getGuideMeSubmitProgressState(session: GuideMeSession | null, submitProgressPercent: number | null) {
  const percent = clampPercent(submitProgressPercent);
  if (percent === null) {
    return {
      percent: null,
      label: session?.currentStep === "refine" ? "Applying your refinement..." : "Processing this step...",
    };
  }

  if (!session) {
    return { percent, label: "Saving your response..." };
  }

  if (percent < 25) {
    return { percent, label: "Saving your response..." };
  }
  if (percent < 60) {
    return {
      percent,
      label:
        session.currentStep === "refine" ? "Re-scoring your refinement..." : "Evaluating your step details...",
    };
  }
  if (percent < 90) {
    return {
      percent,
      label: session.currentStep === "refine" ? "Preparing your next refinement..." : "Preparing your next step...",
    };
  }
  return { percent, label: "Finalizing update..." };
}

function clampPercent(value: number | null) {
  if (value === null || !Number.isFinite(value)) {
    return null;
  }
  return Math.max(0, Math.min(100, Math.round(value)));
}

function GuideIndicators({
  requirements,
}: {
  requirements?: Record<string, GuideMeRequirementIndicator>;
}) {
  const orderedKeys = ["who", "task", "context", "output"];
  const items = orderedKeys
    .map((key) => requirements?.[key] ?? { label: key[0].toUpperCase() + key.slice(1), state: "missing" as const, heuristicScore: null, llmScore: null, maxScore: null });

  return (
    <div className="coaching-indicator-row" aria-label="Guide Me prompt element status">
      {items.map((item) => (
        <div key={item.label} className="coaching-indicator">
          <span aria-hidden="true" className={`coaching-indicator-dot coaching-indicator-${item.state}`} />
          <span>
            {item.label} {item.heuristicScore ?? "--"}/{item.llmScore ?? "--"}
          </span>
        </div>
      ))}
    </div>
  );
}
