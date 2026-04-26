import logoImage from "../../assets/logo.png";

type HeaderProps = {
  isMobile: boolean;
  onOpenSidebar: () => void;
  showFullDemo: boolean;
  showDetails: boolean;
  transformEnabled: boolean;
  summaryType: number | null;
  defaultProfileLabel: string;
  enforcementLevel: "none" | "low" | "moderate" | "full";
  scoring: {
    initialLlmScore?: number | null;
    initialScore: number;
    finalLlmScore?: number | null;
    finalScore: number;
  } | null;
  theme: "dark" | "light";
  onToggleDetails: () => void;
  onToggleTransform: () => void;
  onChangeSummaryType: (summaryType: number | null) => void;
  onChangeEnforcementLevel: (enforcementLevel: "none" | "low" | "moderate" | "full") => void;
};

export function Header({
  isMobile,
  onOpenSidebar,
  showFullDemo,
  showDetails,
  transformEnabled,
  summaryType,
  defaultProfileLabel,
  enforcementLevel,
  scoring,
  theme,
  onToggleDetails,
  onToggleTransform,
  onChangeSummaryType,
  onChangeEnforcementLevel,
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
        {scoring ? (
          <div className="score-chip" aria-label="Prompt score">
            <span className="score-chip-label">Score</span>
            <span className="score-chip-value">
              {formatScorePair(scoring.initialScore, scoring.initialLlmScore)} {"->"} {formatScorePair(scoring.finalScore, scoring.finalLlmScore)}
            </span>
          </div>
        ) : null}
        <label className="profile-picker">
          <span className="profile-picker-label">Profile</span>
          <select
            aria-label="Select demo profile type"
            className="profile-picker-select"
            value={summaryType ?? ""}
            onChange={(event) => {
              const nextValue = event.target.value;
              onChangeSummaryType(nextValue ? Number(nextValue) : null);
            }}
          >
            <option value="">{defaultProfileLabel}</option>
            {Array.from({ length: 9 }, (_, index) => index + 1).map((value) => (
              <option key={value} value={value}>
                Type {value}
              </option>
            ))}
          </select>
        </label>
        <label className="profile-picker">
          <span className="profile-picker-label">Enforcement</span>
          <select
            aria-label="Select prompt enforcement level"
            className="profile-picker-select"
            value={enforcementLevel}
            onChange={(event) =>
              onChangeEnforcementLevel(event.target.value as "none" | "low" | "moderate" | "full")
            }
          >
            <option value="none">None</option>
            <option value="low">Low</option>
            <option value="moderate">Moderate</option>
            <option value="full">Full</option>
          </select>
        </label>
        {showFullDemo ? (
          <>
            <label className="toggle">
              <span className="toggle-label">Use Transformer</span>
              <button
                aria-pressed={transformEnabled}
                className={`toggle-switch ${transformEnabled ? "is-on" : ""}`}
                type="button"
                onClick={onToggleTransform}
              >
                <span className="toggle-thumb" />
              </button>
            </label>
            <label className="toggle">
              <span className="toggle-label">Show Details</span>
              <button
                aria-pressed={showDetails}
                className={`toggle-switch ${showDetails ? "is-on" : ""}`}
                type="button"
                onClick={onToggleDetails}
              >
                <span className="toggle-thumb" />
              </button>
            </label>
          </>
        ) : null}
      </div>
    </header>
  );
}

function formatScorePair(combined: number, llmScore?: number | null) {
  return llmScore === null || llmScore === undefined ? `${combined}` : `${combined}/${llmScore}`;
}
