type GuideMeRequirementIndicator = {
  label: string;
  state: "met" | "partial" | "missing";
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
  onAnswerChange,
  onCancel,
  onClose,
  onLaunch,
  onRestart,
  onSubmit,
  onUsePrompt,
}: GuideMePanelProps) {
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
            {session.guidanceText ? <div className="guide-me-guidance">{session.guidanceText}</div> : null}

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
                    if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
                      event.preventDefault();
                      onSubmit();
                    }
                  }}
                />
              </label>
            )}

            {error ? <div className="error-banner">{error}</div> : null}

            <div className="guide-me-actions">
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
            <p>Start a guided session to build a structured prompt with personalized coaching.</p>
            <button className="send-button" disabled={busy} type="button" onClick={onLaunch}>
              Launch Guide Me
            </button>
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
    .map((key) => requirements?.[key] ?? { label: key[0].toUpperCase() + key.slice(1), state: "missing" as const });

  return (
    <div className="coaching-indicator-row" aria-label="Guide Me prompt element status">
      {items.map((item) => (
        <div key={item.label} className="coaching-indicator">
          <span aria-hidden="true" className={`coaching-indicator-dot coaching-indicator-${item.state}`} />
          <span>{item.label}</span>
        </div>
      ))}
    </div>
  );
}
