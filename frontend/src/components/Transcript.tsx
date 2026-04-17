import { useEffect, useRef } from "react";

type GeneratedImage = {
  mediaType: string;
  base64Data: string;
};

export type TranscriptTurn = {
  id: string;
  userText: string;
  transformedText: string;
  assistantText: string;
  assistantImages: GeneratedImage[];
  transformationApplied: boolean;
  assistantKind: "assistant" | "coaching" | "blocked";
  feedbackStatus: "idle" | "submitting" | "submitted";
};

type TranscriptProps = {
  turns: TranscriptTurn[];
  showDetails: boolean;
  loading: boolean;
  onOpenFeedback: (turnId: string, feedbackType: "up" | "down") => void;
};

export function Transcript({ turns, showDetails, loading, onOpenFeedback }: TranscriptProps) {
  const containerRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) {
      return;
    }

    container.scrollTo({
      top: container.scrollHeight,
      behavior: "smooth",
    });
  }, [turns, loading, showDetails]);

  if (turns.length === 0 && !loading) {
    return (
      <section ref={containerRef} className="transcript transcript-empty">
        <p>Enter a prompt to test how HermanPrompt reshapes it before the LLM responds.</p>
      </section>
    );
  }

  return (
    <section ref={containerRef} className="transcript" aria-live="polite">
      {turns.map((turn) => (
        <div key={turn.id} className="turn-group">
          <article className="message-row message-user">
            <div className="message-label">You</div>
            <div className="message-body">{turn.userText}</div>
          </article>

          {showDetails && turn.transformationApplied && turn.transformedText.trim() ? (
            <article className="message-row message-transform">
              <div className="message-label">Transformed Prompt</div>
              <div className="message-body">{turn.transformedText}</div>
            </article>
          ) : null}

          <article
            className={`message-row ${
              turn.assistantKind === "coaching"
                ? "message-coaching"
                : turn.assistantKind === "blocked"
                  ? "message-blocked"
                  : "message-assistant"
            }`}
          >
            <div className="message-label">
              {turn.assistantKind === "coaching"
                ? "Coaching"
                : turn.assistantKind === "blocked"
                  ? "Safety Check"
                  : "Assistant"}
            </div>
            <div className="message-body">{turn.assistantText}</div>
            {turn.assistantImages.length > 0 ? (
              <div className="assistant-image-grid">
                {turn.assistantImages.map((image, index) => (
                  <img
                    key={`${turn.id}-image-${index}`}
                    alt="Assistant generated output"
                    className="assistant-image"
                    src={`data:${image.mediaType};base64,${image.base64Data}`}
                  />
                ))}
              </div>
            ) : null}
            {turn.assistantKind === "assistant" ? (
              <>
                <div className="feedback-row">
                  <button
                    aria-label="Send positive feedback"
                    className="feedback-icon-button"
                    disabled={turn.feedbackStatus !== "idle"}
                    type="button"
                    onClick={() => onOpenFeedback(turn.id, "up")}
                  >
                    <svg aria-hidden="true" className="feedback-icon" viewBox="0 0 24 24">
                      <path
                        d="M10 21H6.8c-1 0-1.8-.8-1.8-1.8V10c0-1 .8-1.8 1.8-1.8H10V21Zm2-12.6 2.4-5.1c.3-.8 1.1-1.3 1.9-1.3h.2c.9 0 1.6.7 1.6 1.6v2.7h2.6c1.4 0 2.4 1.3 2.1 2.6l-1.5 7.1c-.2 1-1.1 1.8-2.2 1.8H12V8.4Z"
                        fill="none"
                        stroke="currentColor"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth="1.8"
                      />
                    </svg>
                  </button>
                  <button
                    aria-label="Send negative feedback"
                    className="feedback-icon-button"
                    disabled={turn.feedbackStatus !== "idle"}
                    type="button"
                    onClick={() => onOpenFeedback(turn.id, "down")}
                  >
                    <svg aria-hidden="true" className="feedback-icon" viewBox="0 0 24 24">
                      <path
                        d="M14 3h3.2c1 0 1.8.8 1.8 1.8V14c0 1-.8 1.8-1.8 1.8H14V3Zm-2 12.6-2.4 5.1c-.3.8-1.1 1.3-1.9 1.3h-.2c-.9 0-1.6-.7-1.6-1.6v-2.7H3.3c-1.4 0-2.4-1.3-2.1-2.6l1.5-7.1C2.9 7 3.8 6.2 4.9 6.2H12v9.4Z"
                        fill="none"
                        stroke="currentColor"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth="1.8"
                      />
                    </svg>
                  </button>
                </div>
                {turn.feedbackStatus === "submitted" ? <div className="feedback-note">Feedback saved.</div> : null}
              </>
            ) : null}
          </article>
        </div>
      ))}

      {loading ? (
        <article className="message-row message-processing" aria-live="polite">
          <div className="processing-indicator" aria-hidden="true">
            <svg className="processing-icon" viewBox="0 0 24 24">
              <circle cx="12" cy="12" r="8.5" fill="none" stroke="currentColor" strokeWidth="1.8" />
              <path
                d="M12 7.8v4.7l3 1.8"
                fill="none"
                stroke="currentColor"
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="1.8"
              />
            </svg>
            <span className="processing-dot" />
            <span className="processing-dot" />
            <span className="processing-dot" />
          </div>
        </article>
      ) : null}
    </section>
  );
}
