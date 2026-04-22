const FEEDBACK_DIMENSIONS = [
  { value: "structure", label: "Structure" },
  { value: "answer_position", label: "Answer Position" },
  { value: "directness", label: "Directness" },
  { value: "level_of_detail", label: "Level of Detail" },
  { value: "ambiguity_reduction", label: "Ambiguity Reduction" },
  { value: "exploration_level", label: "Exploration Level" },
  { value: "supporting_context", label: "Supporting Context" },
] as const;

type FeedbackModalProps = {
  comments: string;
  feedbackType: "up" | "down";
  selectedDimensions: string[];
  submitting: boolean;
  error: string | null;
  onOpenGuideMe: () => void;
  onClose: () => void;
  onCommentsChange: (value: string) => void;
  onToggleDimension: (value: string) => void;
  onSubmit: () => void;
};

export function FeedbackModal({
  comments,
  feedbackType,
  selectedDimensions,
  submitting,
  error,
  onOpenGuideMe,
  onClose,
  onCommentsChange,
  onToggleDimension,
  onSubmit,
}: FeedbackModalProps) {
  return (
    <div className="modal-backdrop" role="presentation">
      <section aria-modal="true" className="feedback-modal" role="dialog">
        <div className="feedback-modal-header">
          <div>
            <div className="message-label">Response Feedback</div>
            <h2 className="feedback-modal-title">
              {feedbackType === "up" ? "What worked well?" : "What needs improvement?"}
            </h2>
          </div>
          <button className="modal-close" type="button" onClick={onClose}>
            Close
          </button>
        </div>

        <div className="feedback-grid">
          {FEEDBACK_DIMENSIONS.map((dimension) => {
            const checked = selectedDimensions.includes(dimension.value);
            return (
              <label key={dimension.value} className={`dimension-chip ${checked ? "is-selected" : ""}`}>
                <input
                  checked={checked}
                  className="dimension-input"
                  type="checkbox"
                  onChange={() => onToggleDimension(dimension.value)}
                />
                <span>{dimension.label}</span>
              </label>
            );
          })}
        </div>

        <label className="feedback-comment-field">
          <span className="message-label">Comments</span>
          <textarea
            className="feedback-comment-input"
            placeholder="Optional notes"
            rows={4}
            value={comments}
            onChange={(event) => onCommentsChange(event.target.value)}
          />
        </label>

        {error ? <div className="error-banner">{error}</div> : null}

        <div className="feedback-modal-actions">
          <button className="feedback-button" disabled={submitting} type="button" onClick={onOpenGuideMe}>
            Guide Me Instead
          </button>
          <button className="feedback-button" type="button" onClick={onClose}>
            Cancel
          </button>
          <button className="send-button" disabled={submitting} type="button" onClick={onSubmit}>
            {submitting ? "Saving..." : "Submit Feedback"}
          </button>
        </div>
      </section>
    </div>
  );
}
