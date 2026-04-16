type HeaderProps = {
  showDetails: boolean;
  transformEnabled: boolean;
  summaryType: number | null;
  theme: "dark" | "light";
  onToggleDetails: () => void;
  onToggleTransform: () => void;
  onChangeSummaryType: (summaryType: number | null) => void;
};

export function Header({
  showDetails,
  transformEnabled,
  summaryType,
  theme,
  onToggleDetails,
  onToggleTransform,
  onChangeSummaryType,
}: HeaderProps) {
  return (
    <header className="topbar">
      <div className="brand-lockup" aria-label="HermanPrompt">
        <span className="brand-herman">HERMAN</span>
        <span className="brand-prompt">PROMPT</span>
      </div>

      <div className="topbar-controls">
        <span className="theme-badge">{theme}</span>
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
            <option value="">User Default</option>
            {Array.from({ length: 9 }, (_, index) => index + 1).map((value) => (
              <option key={value} value={value}>
                Type {value}
              </option>
            ))}
          </select>
        </label>
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
      </div>
    </header>
  );
}
