export type ThemeMode = "dark" | "light";

export type AppBootstrap = {
  userIdHash: string | null;
  showDetails: boolean;
  transformEnabled: boolean;
  summaryType: number | null;
  theme: ThemeMode;
};

export function getBootstrapState(search: string): AppBootstrap {
  const params = new URLSearchParams(search);
  const userIdHash = params.get("user_id_hash");
  const showDetails = params.get("show_details") === "true";
  const transformEnabled = params.get("transform_enabled") !== "false";
  const theme = params.get("theme") === "light" ? "light" : "dark";
  const rawSummaryType = params.get("summary_type");
  const parsedSummaryType = rawSummaryType ? Number(rawSummaryType) : null;
  const summaryType =
    parsedSummaryType !== null && Number.isInteger(parsedSummaryType) && parsedSummaryType >= 1 && parsedSummaryType <= 9
      ? parsedSummaryType
      : null;

  return {
    userIdHash,
    showDetails,
    transformEnabled,
    summaryType,
    theme,
  };
}
