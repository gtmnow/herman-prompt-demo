export type ThemeMode = "dark" | "light";

export type AppBootstrap = {
  userIdHash: string | null;
  showDetails: boolean;
  transformEnabled: boolean;
  theme: ThemeMode;
};

export function getBootstrapState(search: string): AppBootstrap {
  const params = new URLSearchParams(search);
  const userIdHash = params.get("user_id_hash");
  const showDetails = params.get("show_details") === "true";
  const transformEnabled = params.get("transform_enabled") !== "false";
  const theme = params.get("theme") === "light" ? "light" : "dark";

  return {
    userIdHash,
    showDetails,
    transformEnabled,
    theme,
  };
}
