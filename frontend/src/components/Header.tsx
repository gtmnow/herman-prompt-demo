import logoImage from "../../assets/logo.png";

type HeaderProps = {
  isMobile: boolean;
  onOpenSidebar: () => void;
  scoring: {
    initialLlmScore?: number | null;
    initialScore: number;
    finalLlmScore?: number | null;
    finalScore: number;
  } | null;
  showHeaderScores: boolean;
};

export function Header({
  isMobile,
  onOpenSidebar,
  scoring,
  showHeaderScores,
}: HeaderProps) {
  return (
    <header className="topbar">
      <div className="topbar-brand-group">
        {isMobile ? (
          <button aria-label="Open conversations" className="mobile-sidebar-button" type="button" onClick={onOpenSidebar}>
            <svg aria-hidden="true" className="mobile-sidebar-icon" viewBox="0 0 24 24">
              <path
                d="M4.5 7.5h15m-15 4.5h15m-15 4.5h15"
                fill="none"
                stroke="currentColor"
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="1.8"
              />
            </svg>
          </button>
        ) : null}
        <img alt="HermanPrompt" className="brand-logo" src={logoImage} />
      </div>

      <div className="topbar-controls">
        {showHeaderScores && scoring ? (
          <div className="score-chip" aria-label="Prompt score">
            <span className="score-chip-label">Score</span>
            <span className="score-chip-value">
              {formatScorePair(scoring.initialScore, scoring.initialLlmScore)} {"->"} {formatScorePair(scoring.finalScore, scoring.finalLlmScore)}
            </span>
          </div>
        ) : null}
      </div>
    </header>
  );
}

function formatScorePair(combined: number, llmScore?: number | null) {
  return llmScore === null || llmScore === undefined ? `${combined}` : `${combined}/${llmScore}`;
}
