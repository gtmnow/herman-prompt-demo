type HeaderProps = {
  showDetails: boolean;
  transformEnabled: boolean;
  theme: "dark" | "light";
  onToggleDetails: () => void;
  onToggleTransform: () => void;
};

export function Header({ showDetails, transformEnabled, theme, onToggleDetails, onToggleTransform }: HeaderProps) {
  return (
    <header className="topbar">
      <div className="brand-lockup" aria-label="HermanPrompt">
        <span className="brand-herman">HERMAN</span>
        <span className="brand-prompt">PROMPT</span>
      </div>

      <div className="topbar-controls">
        <span className="theme-badge">{theme}</span>
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
