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

type GuideMePanelProps = {
  answer: string;
  busy: boolean;
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
  onUsePrompt: () => void;
};

export function GuideMePanel({
  answer,
  busy,
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

  useEffect(() => {
    if (!open) {
      setShowPromptPreview(false);
    }
  }, [open]);

  useEffect(() => {
    if (!session?.finalPrompt) {
      setShowPromptPreview(false);
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

            {showPromptPreview && session.finalPrompt ? (
              <div className="guide-me-preview-modal" role="dialog" aria-modal="false" aria-label="Current prompt draft">
                <div className="guide-me-preview-header">
                  <div className="guide-me-meta-label">
                    {session.readyToInsert ? "Formatted prompt" : "Current prompt draft"}
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
                <button className="send-button" type="button" onClick={onUsePrompt}>
                  Use Prompt
                </button>
              ) : (
                <button className="send-button" disabled={busy || !answer.trim()} type="button" onClick={onSubmit}>
                  Continue
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
