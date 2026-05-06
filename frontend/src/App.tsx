import { useEffect, useState } from "react";
import { Composer, type UploadedAttachment } from "./components/Composer";
import {
  ConversationSidebar,
  type ConversationFolder,
  type ConversationSummary,
} from "./components/ConversationSidebar";
import { FeedbackModal } from "./components/FeedbackModal";
import { GuideMePanel, type GuideMeSession } from "./components/GuideMePanel";
import { Header } from "./components/Header";
import { Transcript, type TranscriptTurn } from "./components/Transcript";
import { getLaunchParams, type ThemeMode } from "./lib/queryParams";

const DEMO_RESPONSE =
  "This is a starter scaffold response. The real app will replace this with the configured LLM output.";

type TransformerConversation = {
  conversation_id: string;
  requirements: Record<
    string,
    {
      value?: string | null;
      status: string;
      heuristic_score?: number | null;
      llm_score?: number | null;
      max_score?: number | null;
      reason?: string | null;
      improvement_hint?: string | null;
    }
  >;
  enforcement: {
    level: string;
    status: string;
    missing_fields: string[];
    last_evaluated_at?: string | null;
  };
};

type EnforcementLevel = "none" | "low" | "moderate" | "full";
type TransformerScoring = {
  scoring_version: string;
  initial_score: number;
  final_score: number;
  initial_llm_score?: number | null;
  final_llm_score?: number | null;
  structural_score: number;
};

type CoachingRequirementIndicator = {
  label: string;
  state: "met" | "partial" | "missing";
};

type GuideMeRequirementApiIndicator = CoachingRequirementIndicator & {
  heuristic_score?: number | null;
  llm_score?: number | null;
  max_score?: number | null;
  reason?: string | null;
  improvement_hint?: string | null;
};

type GuideMeApiSession = {
  session_id: string;
  conversation_id: string;
  status: "active" | "complete" | "cancelled";
  current_step: "intro" | "describe_need" | "who" | "why" | "how" | "what" | "refine" | "complete" | "cancelled";
  question_title?: string | null;
  question_text?: string | null;
  answers: Record<string, string>;
  requirements: Record<string, GuideMeRequirementApiIndicator>;
  requirement_debug?: Record<string, Record<string, unknown>>;
  decision_trace?: Record<string, unknown>;
  personalization: {
    first_name: string;
    typical_ai_usage: string;
    profile_label: string;
    recent_examples: string[];
  };
  guidance_text?: string | null;
  follow_up_questions: string[];
  final_prompt?: string | null;
  ready_to_insert: boolean;
};

type SessionBootstrap = {
  access_token: string;
  expires_at: number;
  auth_mode: string;
  user_id_hash: string;
  display_name: string;
  tenant_id: string;
  profile_version?: string | null;
  profile_label?: string | null;
  prompt_enforcement_level?: EnforcementLevel | null;
  features: {
    show_details?: boolean;
    attachments?: boolean;
    transformer_toggle?: boolean;
  };
  branding: {
    app_name?: string;
    theme?: ThemeMode;
  };
  debug: {
    show_details?: boolean;
    transform_enabled?: boolean;
    summary_type?: number | null;
    enforcement_level?: EnforcementLevel | null;
  };
};

type TransformerProfileMetadata = {
  profileVersion: string | null;
  personaSource: string | null;
};

type UserContextState = {
  settings: {
    collection_id: string;
    retrieval_enabled: boolean;
    is_active: boolean;
    max_results?: number | null;
  };
  limits: {
    source: string;
    max_file_bytes: number;
    max_document_count: number;
    max_total_bytes: number;
    max_extracted_text_bytes: number;
    max_chunks_per_document: number;
    max_retrieved_chunks: number;
    max_retrieved_chunks_total: number;
  };
  usage: {
    document_count: number;
    total_bytes: number;
    ready_documents: number;
    processing_documents: number;
    failed_documents: number;
    disabled_documents: number;
  };
  documents: {
    id: string;
    filename: string;
    media_type: string;
    size_bytes: number;
    status: string;
    status_message?: string | null;
    uploaded_at: string;
    processed_at?: string | null;
  }[];
};

type RenameTarget =
  | { kind: "conversation"; item: ConversationSummary }
  | { kind: "folder"; item: ConversationFolder };

function createConversationId() {
  return Math.random().toString(36).slice(2, 10);
}

const GUIDE_ME_SUBMIT_MIN_BUSY_MS = 900;
const MOBILE_BREAKPOINT = "(max-width: 860px)";
const MOBILE_DISCLAIMER_ACK_KEY = "herman-prompt.mobile-disclaimer-acknowledged";

export function App() {
  const launchParams = getLaunchParams(window.location.search);
  const [isMobile, setIsMobile] = useState(() => window.matchMedia(MOBILE_BREAKPOINT).matches);
  const [session, setSession] = useState<SessionBootstrap | null>(null);
  const [sessionLoading, setSessionLoading] = useState(true);
  const [sessionError, setSessionError] = useState<string | null>(null);
  const [showDetails, setShowDetails] = useState(launchParams.showDetails);
  const [transformEnabled, setTransformEnabled] = useState(launchParams.transformEnabled);
  const [summaryType, setSummaryType] = useState<number | null>(launchParams.summaryType);
  const [enforcementLevel, setEnforcementLevel] = useState<EnforcementLevel>("none");
  const [theme, setTheme] = useState<ThemeMode>(launchParams.theme);
  const [showHeaderScores, setShowHeaderScores] = useState(() => {
    const storedValue = window.localStorage.getItem("herman-prompt.show-header-scores");
    return storedValue === null ? true : storedValue === "true";
  });
  const [draft, setDraft] = useState("");
  const [attachments, setAttachments] = useState<UploadedAttachment[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [turns, setTurns] = useState<TranscriptTurn[]>([]);
  const [unfiledConversations, setUnfiledConversations] = useState<ConversationSummary[]>([]);
  const [conversationFolders, setConversationFolders] = useState<ConversationFolder[]>([]);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => window.matchMedia(MOBILE_BREAKPOINT).matches);
  const [loadingConversations, setLoadingConversations] = useState(false);
  const [conversationListError, setConversationListError] = useState<string | null>(null);
  const [conversationActionBusy, setConversationActionBusy] = useState(false);
  const [renameTarget, setRenameTarget] = useState<RenameTarget | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [moveConversationTarget, setMoveConversationTarget] = useState<ConversationSummary | null>(null);
  const [moveTargetFolderId, setMoveTargetFolderId] = useState<string>("");
  const [newFolderName, setNewFolderName] = useState("");
  const [folderDeleteTarget, setFolderDeleteTarget] = useState<ConversationFolder | null>(null);
  const [feedbackDraft, setFeedbackDraft] = useState<{
    turnId: string;
    feedbackType: "up" | "down";
    selectedDimensions: string[];
    comments: string;
    submitting: boolean;
    error: string | null;
  } | null>(null);
  const [conversationId, setConversationId] = useState(createConversationId);
  const [transformerConversation, setTransformerConversation] = useState<TransformerConversation | null>(null);
  const [transformerScoring, setTransformerScoring] = useState<TransformerScoring | null>(null);
  const [transformerProfile, setTransformerProfile] = useState<TransformerProfileMetadata>({
    profileVersion: null,
    personaSource: null,
  });
  const [guideMeSession, setGuideMeSession] = useState<GuideMeSession | null>(null);
  const [guideMeOpen, setGuideMeOpen] = useState(false);
  const [guideMeBusy, setGuideMeBusy] = useState(false);
  const [guideMePendingAction, setGuideMePendingAction] = useState<"launch" | "submit" | "cancel" | null>(null);
  const [guideMeSubmitProgressPercent, setGuideMeSubmitProgressPercent] = useState<number | null>(null);
  const [guideMeAnswer, setGuideMeAnswer] = useState("");
  const [guideMeError, setGuideMeError] = useState<string | null>(null);
  const [personalContextOpen, setPersonalContextOpen] = useState(false);
  const [disclaimerAcknowledged, setDisclaimerAcknowledged] = useState(() => {
    return window.localStorage.getItem(MOBILE_DISCLAIMER_ACK_KEY) === "true";
  });
  const [showDisclaimerModal, setShowDisclaimerModal] = useState(false);
  const [userContext, setUserContext] = useState<UserContextState | null>(null);
  const [userContextLoading, setUserContextLoading] = useState(false);
  const [userContextBusy, setUserContextBusy] = useState(false);
  const [userContextError, setUserContextError] = useState<string | null>(null);

  const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8002";
  const emptyTranscriptMessage = buildWelcomeMessage(session, enforcementLevel, summaryType, transformerProfile);
  useEffect(() => {
    let cancelled = false;

    async function bootstrapSession() {
      setSessionLoading(true);
      setSessionError(null);

      try {
        const params = new URLSearchParams();
        params.set("show_details", String(launchParams.showDetails));
        params.set("transform_enabled", String(launchParams.transformEnabled));
        params.set("theme", launchParams.theme);
        if (launchParams.summaryType !== null) {
          params.set("summary_type", String(launchParams.summaryType));
        }
        if (launchParams.demoUserIdHash) {
          params.set("user_id_hash", launchParams.demoUserIdHash);
        }
        if (launchParams.launchToken) {
          params.set("launch_token", launchParams.launchToken);
        }

        const response = await fetch(`${apiBaseUrl}/api/session/bootstrap?${params.toString()}`);
        if (!response.ok) {
          const errorMessage = await extractErrorMessage(response, "Unable to initialize authenticated session.");
          throw new Error(errorMessage);
        }

        const payload = (await response.json()) as SessionBootstrap;
        if (cancelled) {
          return;
        }

        setSession(payload);
        setShowDetails(payload.debug.show_details ?? launchParams.showDetails);
        setTransformEnabled(payload.debug.transform_enabled ?? launchParams.transformEnabled);
        setSummaryType(payload.debug.summary_type ?? launchParams.summaryType);
        setTheme(payload.branding.theme ?? launchParams.theme);
        setEnforcementLevel(payload.prompt_enforcement_level ?? payload.debug.enforcement_level ?? "none");
        setTransformerProfile({
          profileVersion: payload.profile_version ?? null,
          personaSource: "bootstrap",
        });
      } catch (bootstrapError) {
        if (!cancelled) {
          setSession(null);
          setSessionError(
            bootstrapError instanceof Error ? bootstrapError.message : "Unable to initialize session.",
          );
        }
      } finally {
        if (!cancelled) {
          setSessionLoading(false);
        }
      }
    }

    void bootstrapSession();
    return () => {
      cancelled = true;
    };
  }, [
    apiBaseUrl,
    launchParams.demoUserIdHash,
    launchParams.launchToken,
    launchParams.showDetails,
    launchParams.summaryType,
    launchParams.theme,
    launchParams.transformEnabled,
  ]);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  useEffect(() => {
    window.localStorage.setItem("herman-prompt.show-header-scores", String(showHeaderScores));
  }, [showHeaderScores]);

  useEffect(() => {
    const mediaQuery = window.matchMedia(MOBILE_BREAKPOINT);
    const syncViewport = (matches: boolean) => {
      setIsMobile(matches);
      setSidebarCollapsed(matches);
    };

    syncViewport(mediaQuery.matches);

    const listener = (event: MediaQueryListEvent) => syncViewport(event.matches);
    mediaQuery.addEventListener("change", listener);
    return () => mediaQuery.removeEventListener("change", listener);
  }, []);

  useEffect(() => {
    if (isMobile && !disclaimerAcknowledged) {
      setShowDisclaimerModal(true);
      return;
    }

    if (!isMobile) {
      setShowDisclaimerModal(false);
    }
  }, [disclaimerAcknowledged, isMobile]);

  useEffect(() => {
    if (!session?.access_token) {
      return;
    }

    void loadConversationSummaries();
    void loadUserContext();
  }, [session?.access_token]);

  useEffect(() => {
    if (!session?.access_token) {
      return;
    }

    void loadGuideMeSession(`conv_${conversationId}`);
  }, [conversationId, session?.access_token]);

  function getAuthHeaders(): Record<string, string> {
    if (!session) {
      return {};
    }

    return {
      Authorization: `Bearer ${session.access_token}`,
    };
  }

  async function loadGuideMeSession(targetConversationId: string) {
    if (!session) {
      return;
    }

    try {
      const response = await fetch(`${apiBaseUrl}/api/guide-me/${targetConversationId}`, {
        headers: getAuthHeaders(),
      });

      if (!response.ok) {
        throw new Error("Unable to load Guide Me session.");
      }

      const payload = (await response.json()) as { session?: GuideMeApiSession | null };
      setGuideMeSession(payload.session ? mapGuideMeSession(payload.session) : null);
      setGuideMeError(null);
    } catch (loadError) {
      setGuideMeSession(null);
      setGuideMeError(loadError instanceof Error ? loadError.message : "Unable to load Guide Me session.");
    }
  }

  async function loadUserContext() {
    if (!session) {
      return;
    }
    setUserContextLoading(true);
    try {
      const response = await fetch(`${apiBaseUrl}/api/user-context`, {
        headers: getAuthHeaders(),
      });
      if (!response.ok) {
        const errorMessage = await extractErrorMessage(response, "Unable to load personal context.");
        throw new Error(errorMessage);
      }
      const payload = (await response.json()) as UserContextState;
      setUserContext(payload);
      setUserContextError(null);
    } catch (contextError) {
      setUserContextError(contextError instanceof Error ? contextError.message : "Unable to load personal context.");
      setUserContext(null);
    } finally {
      setUserContextLoading(false);
    }
  }

  async function uploadUserContextFiles(files: FileList | null) {
    if (!files || files.length === 0 || !session) {
      return;
    }
    setUserContextBusy(true);
    setUserContextError(null);
    try {
      for (const file of Array.from(files)) {
        const formData = new FormData();
        formData.append("file", file);
        const response = await fetch(`${apiBaseUrl}/api/user-context/documents`, {
          method: "POST",
          headers: getAuthHeaders(),
          body: formData,
        });
        if (!response.ok) {
          const errorMessage = await extractErrorMessage(response, "Unable to upload personal context document.");
          throw new Error(errorMessage);
        }
        const payload = (await response.json()) as UserContextState;
        setUserContext(payload);
      }
    } catch (contextError) {
      setUserContextError(contextError instanceof Error ? contextError.message : "Unable to upload document.");
    } finally {
      setUserContextBusy(false);
    }
  }

  async function deleteUserContextDocument(documentId: string) {
    if (!session) {
      return;
    }
    setUserContextBusy(true);
    setUserContextError(null);
    try {
      const response = await fetch(`${apiBaseUrl}/api/user-context/documents/${documentId}`, {
        method: "DELETE",
        headers: getAuthHeaders(),
      });
      if (!response.ok) {
        const errorMessage = await extractErrorMessage(response, "Unable to delete personal context document.");
        throw new Error(errorMessage);
      }
      const payload = (await response.json()) as UserContextState;
      setUserContext(payload);
    } catch (contextError) {
      setUserContextError(contextError instanceof Error ? contextError.message : "Unable to delete document.");
    } finally {
      setUserContextBusy(false);
    }
  }

  async function updateUserContextSettings(nextEnabled: boolean) {
    if (!session || !userContext) {
      return;
    }
    setUserContextBusy(true);
    setUserContextError(null);
    try {
      const response = await fetch(`${apiBaseUrl}/api/user-context/settings`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          ...getAuthHeaders(),
        },
        body: JSON.stringify({
          retrieval_enabled: nextEnabled,
          is_active: true,
        }),
      });
      if (!response.ok) {
        const errorMessage = await extractErrorMessage(response, "Unable to update personal context settings.");
        throw new Error(errorMessage);
      }
      const payload = (await response.json()) as UserContextState;
      setUserContext(payload);
    } catch (contextError) {
      setUserContextError(contextError instanceof Error ? contextError.message : "Unable to update settings.");
    } finally {
      setUserContextBusy(false);
    }
  }

  async function startGuideMe(forceRestart = false, sourcePrompt?: string) {
    if (!session || guideMeBusy) {
      return;
    }

    if (!forceRestart && guideMeSession && guideMeSession.status !== "cancelled") {
      setGuideMeOpen((value) => !value);
      return;
    }

    setGuideMeBusy(true);
    setGuideMePendingAction("launch");
    setGuideMeError(null);
    setGuideMeOpen(true);

    try {
      const response = await fetch(`${apiBaseUrl}/api/guide-me/start`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...getAuthHeaders(),
        },
        body: JSON.stringify({
          conversation_id: `conv_${conversationId}`,
          summary_type: summaryType,
          source_prompt: sourcePrompt?.trim() || undefined,
          enforcement_level: enforcementLevel,
        }),
      });

      if (!response.ok) {
        const errorMessage = await extractErrorMessage(response, "Unable to start Guide Me.");
        throw new Error(errorMessage);
      }

      const payload = (await response.json()) as { session?: GuideMeApiSession | null };
      setGuideMeSession(payload.session ? mapGuideMeSession(payload.session) : null);
      setGuideMeOpen(true);
      setGuideMeAnswer("");
      setGuideMeError(null);
    } catch (guideError) {
      setGuideMeError(guideError instanceof Error ? guideError.message : "Unable to start Guide Me.");
      setGuideMeOpen(true);
    } finally {
      setGuideMeBusy(false);
      setGuideMePendingAction(null);
    }
  }

  function openGuideMe(sourcePrompt?: string) {
    if (isMobile) {
      setSidebarCollapsed(true);
      setPersonalContextOpen(false);
    }

    if (feedbackDraft) {
      setTurns((current) =>
        current.map((turn) =>
          turn.id === feedbackDraft.turnId && turn.feedbackStatus === "submitting"
            ? { ...turn, feedbackStatus: "idle" }
            : turn,
        ),
      );
      setFeedbackDraft(null);
    }

    const fallbackPrompt =
      sourcePrompt?.trim() ||
      draft.trim() ||
      turns.slice().reverse().find((turn) => turn.assistantKind === "coaching")?.userText ||
      turns.slice().reverse()[0]?.userText ||
      "";

    if (guideMeSession && guideMeSession.status !== "cancelled") {
      if (fallbackPrompt) {
        void startGuideMe(true, fallbackPrompt);
        return;
      }
      setGuideMeOpen(true);
      return;
    }

    void startGuideMe(false, fallbackPrompt);
  }

  function restartGuideMe() {
    if (feedbackDraft) {
      setFeedbackDraft(null);
    }
    setGuideMeAnswer("");
    const sourcePrompt =
      guideMeSession?.answers.source_prompt ||
      guideMeSession?.answers._source_prompt ||
      draft.trim() ||
      "";
    void startGuideMe(true, sourcePrompt);
  }

  async function submitGuideMeAnswer() {
    if (!session || !guideMeSession || !guideMeAnswer.trim() || guideMeBusy) {
      return;
    }

    const submitStartedAt = Date.now();
    const progressTimerMs = 180;
    setGuideMeSubmitProgressPercent(6);
    setGuideMeBusy(true);
    setGuideMePendingAction("submit");
    setGuideMeError(null);
    const progressTimer = window.setInterval(() => {
      setGuideMeSubmitProgressPercent((current) => {
        const currentValue = typeof current === "number" && Number.isFinite(current) ? current : 6;
        const elapsedMs = Date.now() - submitStartedAt;

        if (elapsedMs < 600) {
          return Math.min(28, currentValue + 5);
        }
        if (elapsedMs < 1600) {
          return Math.min(52, currentValue + 4);
        }
        if (elapsedMs < 3000) {
          return Math.min(74, currentValue + 3);
        }
        return Math.min(90, currentValue + 2);
      });
    }, progressTimerMs);

    try {
      const response = await fetch(`${apiBaseUrl}/api/guide-me/respond`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...getAuthHeaders(),
        },
        body: JSON.stringify({
          conversation_id: guideMeSession.conversationId,
          answer: guideMeAnswer.trim(),
        }),
      });

      if (!response.ok) {
        const errorMessage = await extractErrorMessage(response, "Unable to continue Guide Me.");
        throw new Error(errorMessage);
      }

      const payload = (await response.json()) as { session?: GuideMeApiSession | null };
      setGuideMeSession(payload.session ? mapGuideMeSession(payload.session) : null);
      setGuideMeAnswer("");
    } catch (guideError) {
      setGuideMeError(guideError instanceof Error ? guideError.message : "Unable to continue Guide Me.");
    } finally {
      window.clearInterval(progressTimer);
      setGuideMeSubmitProgressPercent(100);
      const elapsedMs = Date.now() - submitStartedAt;
      const remainingMs = GUIDE_ME_SUBMIT_MIN_BUSY_MS - elapsedMs;
      if (remainingMs > 0) {
        await delay(remainingMs);
      }
      await delay(120);
      setGuideMeBusy(false);
      setGuideMePendingAction(null);
      setGuideMeSubmitProgressPercent(null);
    }
  }

  async function cancelGuideMe() {
    if (!session || !guideMeSession || guideMeBusy) {
      setGuideMeOpen(false);
      return;
    }

    setGuideMeBusy(true);
    setGuideMePendingAction("cancel");
    try {
      const response = await fetch(`${apiBaseUrl}/api/guide-me/${guideMeSession.conversationId}/cancel`, {
        method: "POST",
        headers: getAuthHeaders(),
      });

      if (!response.ok) {
        const errorMessage = await extractErrorMessage(response, "Unable to cancel Guide Me.");
        throw new Error(errorMessage);
      }

      setGuideMeSession(null);
      setGuideMeAnswer("");
      setGuideMeError(null);
      setGuideMeOpen(false);
    } catch (guideError) {
      setGuideMeError(guideError instanceof Error ? guideError.message : "Unable to cancel Guide Me.");
    } finally {
      setGuideMeBusy(false);
      setGuideMePendingAction(null);
    }
  }

  async function updateGuideMeDraft(nextDraft: string) {
    if (!session || !guideMeSession || guideMeBusy) {
      return;
    }

    setGuideMeBusy(true);
    setGuideMeError(null);
    try {
      const response = await fetch(`${apiBaseUrl}/api/guide-me/${guideMeSession.conversationId}/draft`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          ...getAuthHeaders(),
        },
        body: JSON.stringify({
          draft_text: nextDraft.trim(),
        }),
      });

      if (!response.ok) {
        const errorMessage = await extractErrorMessage(response, "Unable to update Guide Me draft.");
        throw new Error(errorMessage);
      }

      const payload = (await response.json()) as { session?: GuideMeApiSession | null };
      setGuideMeSession(payload.session ? mapGuideMeSession(payload.session) : null);
    } catch (draftError) {
      setGuideMeError(draftError instanceof Error ? draftError.message : "Unable to update Guide Me draft.");
      throw draftError;
    } finally {
      setGuideMeBusy(false);
    }
  }

  function useGuideMePrompt(mode: "final" | "as-is") {
    if (!guideMeSession?.finalPrompt) {
      return;
    }

    setDraft(guideMeSession.finalPrompt);
    setGuideMeOpen(false);
    setGuideMeError(null);
  }

  async function handleSubmit() {
    const message = draft.trim() || (attachments.length > 0 ? "Please analyze the attached content." : "");
    if (!session || !message || loading || uploading) {
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const response = await fetch(`${apiBaseUrl}/api/chat/send`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...getAuthHeaders(),
        },
        body: JSON.stringify({
          conversation_id: `conv_${conversationId}`,
          message_text: message,
          summary_type: summaryType,
          attachments: attachments.map((attachment) => ({
            id: attachment.id,
            kind: attachment.kind,
            name: attachment.name,
            media_type: attachment.mediaType,
            provider_file_id: attachment.providerFileId,
            size_bytes: attachment.sizeBytes,
          })),
          debug: {
            show_details: showDetails,
            transform_enabled: transformEnabled,
            enforcement_level: enforcementLevel,
          },
        }),
      });

      if (!response.ok) {
        const errorMessage = await extractErrorMessage(response, "Unable to send message.");
        throw new Error(errorMessage);
      }

      const payload = (await response.json()) as {
        turn_id: string;
        conversation_id: string;
        user_message: { text: string };
        transformed_message: { text: string };
        assistant_message: { text: string };
        assistant_images: { media_type: string; base64_data: string }[];
        metadata: {
          transformer: {
            transformation_applied: boolean;
            result_type: "transformed" | "coaching" | "blocked";
            conversation?: TransformerConversation | null;
            scoring?: TransformerScoring | null;
            coaching_tip?: string | null;
            blocking_message?: string | null;
            profile_version?: string | null;
            persona_source?: string | null;
          };
        };
      };

      setTurns((current) => [
        ...current,
        {
          id: payload.turn_id,
          userText: payload.user_message.text,
          transformedText: payload.transformed_message.text,
          assistantText: payload.assistant_message.text || DEMO_RESPONSE,
          coachingText:
            payload.metadata.transformer.result_type === "transformed"
              ? (payload.metadata.transformer.coaching_tip ?? "")
              : "",
          coachingRequirements: deriveCoachingRequirements(
            payload.user_message.text,
            payload.metadata.transformer.conversation ?? null,
            payload.metadata.transformer.result_type,
            payload.metadata.transformer.coaching_tip ?? null,
          ),
          assistantImages: payload.assistant_images.map((image) => ({
            mediaType: image.media_type,
            base64Data: image.base64_data,
          })),
          transformationApplied: payload.metadata.transformer.transformation_applied,
          assistantKind:
            payload.metadata.transformer.result_type === "transformed"
              ? "assistant"
              : payload.metadata.transformer.result_type,
          feedbackStatus: "idle",
        },
      ]);
      setConversationId(payload.conversation_id.replace(/^conv_/, ""));
      setTransformerConversation(payload.metadata.transformer.conversation ?? null);
      setTransformerScoring(payload.metadata.transformer.scoring ?? null);
      setTransformerProfile({
        profileVersion: payload.metadata.transformer.profile_version ?? null,
        personaSource: payload.metadata.transformer.persona_source ?? null,
      });
      setDraft("");
      setAttachments([]);
      setUploadError(null);
      void loadConversationSummaries();
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Something went wrong.");
    } finally {
      setLoading(false);
    }
  }

  async function uploadFiles(files: FileList | null) {
    if (!files || files.length === 0 || !session) {
      return;
    }

    setUploadError(null);
    setUploading(true);

    try {
      const uploadedAttachments: UploadedAttachment[] = [];

      for (const file of Array.from(files)) {
        const formData = new FormData();
        formData.append("file", file);

        const response = await fetch(`${apiBaseUrl}/api/attachments/upload`, {
          method: "POST",
          headers: getAuthHeaders(),
          body: formData,
        });

        if (!response.ok) {
          const errorMessage = await extractErrorMessage(response, "Unable to upload one or more files.");
          throw new Error(errorMessage);
        }

        const payload = (await response.json()) as {
          attachment: {
            id: string;
            kind: "document" | "image";
            name: string;
            media_type?: string | null;
            provider_file_id?: string | null;
            size_bytes?: number | null;
          };
        };

        uploadedAttachments.push({
          id: payload.attachment.id,
          kind: payload.attachment.kind,
          name: payload.attachment.name,
          mediaType: payload.attachment.media_type,
          providerFileId: payload.attachment.provider_file_id,
          sizeBytes: payload.attachment.size_bytes,
        });
      }

      setAttachments((current) => [...current, ...uploadedAttachments]);
    } catch (uploadFailure) {
      setUploadError(uploadFailure instanceof Error ? uploadFailure.message : "File upload failed.");
    } finally {
      setUploading(false);
    }
  }

  function openFeedback(turnId: string, feedbackType: "up" | "down") {
    setFeedbackDraft({
      turnId,
      feedbackType,
      selectedDimensions: [],
      comments: "",
      submitting: false,
      error: null,
    });
  }

  function toggleFeedbackDimension(value: string) {
    setFeedbackDraft((current) => {
      if (!current) {
        return current;
      }

      const selectedDimensions = current.selectedDimensions.includes(value)
        ? current.selectedDimensions.filter((item) => item !== value)
        : [...current.selectedDimensions, value];

      return {
        ...current,
        selectedDimensions,
      };
    });
  }

  async function submitFeedback() {
    if (!session || !feedbackDraft) {
      return;
    }

    setFeedbackDraft((current) => (current ? { ...current, submitting: true, error: null } : current));
    setTurns((current) =>
      current.map((turn) =>
        turn.id === feedbackDraft.turnId ? { ...turn, feedbackStatus: "submitting" } : turn,
      ),
    );

    try {
      const response = await fetch(`${apiBaseUrl}/api/feedback`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...getAuthHeaders(),
        },
        body: JSON.stringify({
          turn_id: feedbackDraft.turnId,
          conversation_id: `conv_${conversationId}`,
          feedback_type: feedbackDraft.feedbackType,
          selected_dimensions: feedbackDraft.selectedDimensions,
          comments: feedbackDraft.comments.trim() || null,
        }),
      });

      if (!response.ok) {
        throw new Error("Unable to save feedback.");
      }

      setTurns((current) =>
        current.map((turn) =>
          turn.id === feedbackDraft.turnId ? { ...turn, feedbackStatus: "submitted" } : turn,
        ),
      );
      setFeedbackDraft(null);
    } catch (submitError) {
      const message = submitError instanceof Error ? submitError.message : "Something went wrong.";
      setTurns((current) =>
        current.map((turn) => (turn.id === feedbackDraft.turnId ? { ...turn, feedbackStatus: "idle" } : turn)),
      );
      setFeedbackDraft((current) => (current ? { ...current, submitting: false, error: message } : current));
    }
  }

  function resetConversation(nextTransformEnabled: boolean) {
    setTransformEnabled(nextTransformEnabled);
    setConversationId(createConversationId());
    setTransformerConversation(null);
    setTransformerScoring(null);
    setTurns([]);
    setDraft("");
    setAttachments([]);
    setUploadError(null);
    setError(null);
    setFeedbackDraft(null);
    setGuideMeSession(null);
    setGuideMeOpen(false);
    setGuideMeAnswer("");
    setGuideMeError(null);
    setTransformerProfile((current) => ({
      profileVersion: session?.profile_version ?? current.profileVersion ?? null,
      personaSource: session?.profile_version ? "bootstrap" : null,
    }));
  }

  function applySummaryType(nextSummaryType: number | null) {
    setSummaryType(nextSummaryType);
    setEnforcementLevel(nextSummaryType === null ? session?.prompt_enforcement_level ?? "none" : "none");
    setConversationId(createConversationId());
    setTransformerConversation(null);
    setTransformerScoring(null);
    setTurns([]);
    setDraft("");
    setAttachments([]);
    setUploadError(null);
    setError(null);
    setFeedbackDraft(null);
    setGuideMeSession(null);
    setGuideMeOpen(false);
    setGuideMeAnswer("");
    setGuideMeError(null);
    setTransformerProfile((current) => ({
      profileVersion: nextSummaryType === null ? session?.profile_version ?? current.profileVersion ?? null : null,
      personaSource: nextSummaryType === null && session?.profile_version ? "bootstrap" : null,
    }));
  }

  function applyEnforcementLevel(nextEnforcementLevel: EnforcementLevel) {
    setEnforcementLevel(nextEnforcementLevel);
    setConversationId(createConversationId());
    setTransformerConversation(null);
    setTransformerScoring(null);
    setTurns([]);
    setDraft("");
    setAttachments([]);
    setUploadError(null);
    setError(null);
    setFeedbackDraft(null);
    setGuideMeSession(null);
    setGuideMeOpen(false);
    setGuideMeAnswer("");
    setGuideMeError(null);
    setTransformerProfile((current) => ({
      profileVersion: session?.profile_version ?? current.profileVersion ?? null,
      personaSource: session?.profile_version ? "bootstrap" : null,
    }));
  }

  function openPersonalSettings() {
    if (isMobile) {
      setSidebarCollapsed(true);
      setGuideMeOpen(false);
    }
    setPersonalContextOpen(true);
    void loadUserContext();
  }

  function acknowledgeDisclaimer() {
    window.localStorage.setItem(MOBILE_DISCLAIMER_ACK_KEY, "true");
    setDisclaimerAcknowledged(true);
    setShowDisclaimerModal(false);
  }

  async function loadConversationSummaries() {
    if (!session) {
      return;
    }

    setLoadingConversations(true);
    setConversationListError(null);
    try {
      const response = await fetch(`${apiBaseUrl}/api/conversations`, {
        headers: getAuthHeaders(),
      });

      if (!response.ok) {
        const errorMessage = await extractErrorMessage(response, "Unable to load conversations.");
        throw new Error(errorMessage);
      }

      const payload = (await response.json()) as {
        unfiled_conversations: {
          id: string;
          title: string;
          folder_id?: string | null;
          created_at: string;
          updated_at: string;
        }[];
        folders: {
          id: string;
          name: string;
          created_at: string;
          updated_at: string;
          conversations: {
            id: string;
            title: string;
            folder_id?: string | null;
            created_at: string;
            updated_at: string;
          }[];
        }[];
      };

      setUnfiledConversations(payload.unfiled_conversations.map(mapConversationSummary));
      setConversationFolders(
        payload.folders.map((folder) => ({
          id: folder.id,
          name: folder.name,
          createdAt: folder.created_at,
          updatedAt: folder.updated_at,
          conversations: folder.conversations.map(mapConversationSummary),
        })),
      );
    } catch (loadError) {
      setUnfiledConversations([]);
      setConversationFolders([]);
      setConversationListError(loadError instanceof Error ? loadError.message : "Unable to load conversations.");
    } finally {
      setLoadingConversations(false);
    }
  }

  async function loadConversation(targetConversationId: string) {
    if (!session) {
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const response = await fetch(`${apiBaseUrl}/api/conversations/${targetConversationId}`, {
        headers: getAuthHeaders(),
      });

      if (!response.ok) {
        const errorMessage = await extractErrorMessage(response, "Unable to load conversation.");
        throw new Error(errorMessage);
      }

      const payload = (await response.json()) as {
        id: string;
        title: string;
        folder_id?: string | null;
        transformer_conversation?: TransformerConversation | null;
        transformer_scoring?: TransformerScoring | null;
        turns: {
          id: string;
          user_text: string;
          transformed_text: string;
          assistant_text: string;
          coaching_text?: string;
          coaching_requirements?: Record<string, CoachingRequirementIndicator>;
          assistant_kind?: "assistant" | "coaching" | "blocked";
          transformation_applied: boolean;
          assistant_images: { media_type: string; base64_data: string }[];
        }[];
      };

      setConversationId(payload.id.replace(/^conv_/, ""));
      setTransformerConversation(payload.transformer_conversation ?? null);
      setTransformerScoring(payload.transformer_scoring ?? null);
      setTurns(
        payload.turns.map((turn) => ({
          id: turn.id,
          userText: turn.user_text,
          transformedText: turn.transformed_text,
          assistantText: turn.assistant_text,
          coachingText: turn.coaching_text ?? "",
          coachingRequirements: turn.coaching_requirements ?? {},
          transformationApplied: turn.transformation_applied,
          assistantKind: turn.assistant_kind ?? "assistant",
          assistantImages: turn.assistant_images.map((image) => ({
            mediaType: image.media_type,
            base64Data: image.base64_data,
          })),
          feedbackStatus: "idle",
        })),
      );
      setDraft("");
      setAttachments([]);
      setUploadError(null);
      setGuideMeAnswer("");
      setGuideMeError(null);
      setGuideMeOpen(false);
      setTransformerProfile((current) => ({
        profileVersion: session?.profile_version ?? current.profileVersion ?? null,
        personaSource: session?.profile_version ? "bootstrap" : null,
      }));
      if (isMobile) {
        setSidebarCollapsed(true);
      }
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Unable to load conversation.");
    } finally {
      setLoading(false);
    }
  }

  function startNewConversation() {
    setConversationId(createConversationId());
    setTransformerConversation(null);
    setTransformerScoring(null);
    setTurns([]);
    setDraft("");
    setAttachments([]);
    setUploadError(null);
    setError(null);
    setFeedbackDraft(null);
    setGuideMeSession(null);
    setGuideMeOpen(false);
    setGuideMeAnswer("");
    setGuideMeError(null);
    setRenameTarget(null);
    setRenameValue("");
    setMoveConversationTarget(null);
    setMoveTargetFolderId("");
    setNewFolderName("");
    setFolderDeleteTarget(null);
    if (isMobile) {
      setSidebarCollapsed(true);
    }
  }

  async function deleteConversation(targetConversationId: string) {
    if (!session || !window.confirm("Delete this conversation?")) {
      return;
    }

    setConversationActionBusy(true);
    try {
      const response = await fetch(`${apiBaseUrl}/api/conversations/${targetConversationId}`, {
        method: "DELETE",
        headers: getAuthHeaders(),
      });

      if (!response.ok) {
        const errorMessage = await extractErrorMessage(response, "Unable to delete conversation.");
        throw new Error(errorMessage);
      }

      if (`conv_${conversationId}` === targetConversationId) {
        startNewConversation();
      }
      await loadConversationSummaries();
      if (isMobile) {
        setSidebarCollapsed(true);
      }
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : "Unable to delete conversation.");
    } finally {
      setConversationActionBusy(false);
    }
  }

  async function deleteAllConversations() {
    if (!session || unfiledConversations.length === 0) {
      return;
    }
    if (
      !window.confirm(
        "Delete all unfiled saved conversations from HermanPrompt? Conversations inside folders will be preserved.",
      )
    ) {
      return;
    }

    setConversationActionBusy(true);
    try {
      const response = await fetch(`${apiBaseUrl}/api/conversations`, {
        method: "DELETE",
        headers: getAuthHeaders(),
      });

      if (!response.ok) {
        const errorMessage = await extractErrorMessage(response, "Unable to delete conversations.");
        throw new Error(errorMessage);
      }

      setUnfiledConversations([]);
      setConversationId(createConversationId());
      setTransformerConversation(null);
      setTransformerScoring(null);
      setTurns([]);
      setDraft("");
      setAttachments([]);
      setUploadError(null);
      setError(null);
      setFeedbackDraft(null);
      setGuideMeSession(null);
      setGuideMeOpen(false);
      setGuideMeAnswer("");
      setGuideMeError(null);
      setTransformerProfile({
        profileVersion: session?.profile_version ?? null,
        personaSource: session?.profile_version ? "bootstrap" : null,
      });
      if (isMobile) {
        setSidebarCollapsed(true);
      }
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : "Unable to delete conversations.");
    } finally {
      setConversationActionBusy(false);
    }
  }

  async function saveRename() {
    if (!session || !renameTarget || !renameValue.trim()) {
      return;
    }

    setConversationActionBusy(true);
    setError(null);
    try {
      const endpoint =
        renameTarget.kind === "conversation"
          ? `${apiBaseUrl}/api/conversations/${renameTarget.item.id}`
          : `${apiBaseUrl}/api/conversation-folders/${renameTarget.item.id}`;
      const body =
        renameTarget.kind === "conversation"
          ? { title: renameValue.trim() }
          : { name: renameValue.trim() };

      const response = await fetch(endpoint, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          ...getAuthHeaders(),
        },
        body: JSON.stringify(body),
      });

      if (!response.ok) {
        const errorMessage = await extractErrorMessage(response, "Unable to save name.");
        throw new Error(errorMessage);
      }

      await loadConversationSummaries();
      setRenameTarget(null);
      setRenameValue("");
    } catch (renameError) {
      setError(renameError instanceof Error ? renameError.message : "Unable to save name.");
    } finally {
      setConversationActionBusy(false);
    }
  }

  async function moveConversationToFolder() {
    if (!session || !moveConversationTarget) {
      return;
    }

    setConversationActionBusy(true);
    setError(null);
    try {
      let folderId: string | null = moveTargetFolderId || null;
      const trimmedFolderName = newFolderName.trim();
      if (trimmedFolderName) {
        const createResponse = await fetch(`${apiBaseUrl}/api/conversation-folders`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...getAuthHeaders(),
          },
          body: JSON.stringify({ name: trimmedFolderName }),
        });

        if (!createResponse.ok) {
          const errorMessage = await extractErrorMessage(createResponse, "Unable to create folder.");
          throw new Error(errorMessage);
        }

        const createdFolder = (await createResponse.json()) as { id: string };
        folderId = createdFolder.id;
      }

      const response = await fetch(`${apiBaseUrl}/api/conversations/${moveConversationTarget.id}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          ...getAuthHeaders(),
        },
        body: JSON.stringify({ folder_id: folderId }),
      });

      if (!response.ok) {
        const errorMessage = await extractErrorMessage(response, "Unable to file conversation.");
        throw new Error(errorMessage);
      }

      await loadConversationSummaries();
      setMoveConversationTarget(null);
      setMoveTargetFolderId("");
      setNewFolderName("");
    } catch (moveError) {
      setError(moveError instanceof Error ? moveError.message : "Unable to file conversation.");
    } finally {
      setConversationActionBusy(false);
    }
  }

  async function deleteFolder(mode: "unfile" | "delete_contents") {
    if (!session || !folderDeleteTarget) {
      return;
    }

    setConversationActionBusy(true);
    setError(null);
    try {
      const response = await fetch(
        `${apiBaseUrl}/api/conversation-folders/${folderDeleteTarget.id}?mode=${mode}`,
        {
          method: "DELETE",
          headers: getAuthHeaders(),
        },
      );

      if (!response.ok) {
        const errorMessage = await extractErrorMessage(response, "Unable to delete folder.");
        throw new Error(errorMessage);
      }

      await loadConversationSummaries();
      setFolderDeleteTarget(null);
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : "Unable to delete folder.");
    } finally {
      setConversationActionBusy(false);
    }
  }

  async function exportConversation(targetConversationId: string) {
    if (!session) {
      return;
    }

    setConversationActionBusy(true);
    try {
      const response = await fetch(`${apiBaseUrl}/api/conversations/${targetConversationId}/export`, {
        headers: getAuthHeaders(),
      });

      if (!response.ok) {
        const errorMessage = await extractErrorMessage(response, "Unable to export conversation.");
        throw new Error(errorMessage);
      }

      const blob = await response.blob();
      const objectUrl = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = objectUrl;
      anchor.download = `${targetConversationId}.txt`;
      document.body.append(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(objectUrl);
    } catch (exportError) {
      setError(exportError instanceof Error ? exportError.message : "Unable to export conversation.");
    } finally {
      setConversationActionBusy(false);
    }
  }

  if (sessionLoading) {
    return (
      <main className="app-shell">
        <Header
          isMobile={isMobile}
          onOpenSidebar={() => setSidebarCollapsed(false)}
          scoring={transformerScoring ? {
            initialLlmScore: transformerScoring.initial_llm_score,
            initialScore: transformerScoring.initial_score,
            finalLlmScore: transformerScoring.final_llm_score,
            finalScore: transformerScoring.final_score,
          } : null}
          showHeaderScores={showHeaderScores}
        />
        <section className="blocking-state">
          <h1>Initializing session</h1>
          <p>HermanPrompt is verifying your launch context and starting a secure app session.</p>
        </section>
      </main>
    );
  }

  if (!session) {
    return (
      <main className="app-shell">
        <Header
          isMobile={isMobile}
          onOpenSidebar={() => setSidebarCollapsed(false)}
          scoring={transformerScoring ? {
            initialLlmScore: transformerScoring.initial_llm_score,
            initialScore: transformerScoring.initial_score,
            finalLlmScore: transformerScoring.final_llm_score,
            finalScore: transformerScoring.final_score,
          } : null}
          showHeaderScores={showHeaderScores}
        />
        <section className="blocking-state">
          <h1>{getBlockingStateTitle(sessionError)}</h1>
          <p>{sessionError ?? "The app needs a signed launch token or explicit demo bootstrap to continue."}</p>
        </section>
      </main>
    );
  }

  return (
    <main className="app-shell">
      <Header
        isMobile={isMobile}
        onOpenSidebar={() => setSidebarCollapsed(false)}
        scoring={transformerScoring ? {
          initialLlmScore: transformerScoring.initial_llm_score,
          initialScore: transformerScoring.initial_score,
          finalLlmScore: transformerScoring.final_llm_score,
          finalScore: transformerScoring.final_score,
        } : null}
        showHeaderScores={showHeaderScores}
      />
      <div className="chat-layout">
        {isMobile && !sidebarCollapsed ? (
          <button
            aria-label="Close conversations"
            className="sidebar-backdrop"
            type="button"
            onClick={() => setSidebarCollapsed(true)}
          />
        ) : null}
        <ConversationSidebar
          actionBusy={conversationActionBusy}
          activeConversationId={`conv_${conversationId}`}
          collapsed={sidebarCollapsed}
          isMobile={isMobile}
          folders={conversationFolders}
          error={conversationListError}
          loading={loadingConversations}
          onDeleteAllConversations={deleteAllConversations}
          onDeleteConversation={deleteConversation}
          onExportConversation={exportConversation}
          onOpenSettings={openPersonalSettings}
          onOpenConversationRename={(conversation) => {
            setRenameTarget({ kind: "conversation", item: conversation });
            setRenameValue(conversation.title);
          }}
          onOpenDeleteFolder={(folder) => setFolderDeleteTarget(folder)}
          onOpenFolderRename={(folder) => {
            setRenameTarget({ kind: "folder", item: folder });
            setRenameValue(folder.name);
          }}
          onOpenMoveConversation={(conversation) => {
            setMoveConversationTarget(conversation);
            setMoveTargetFolderId(conversation.folderId ?? "");
            setNewFolderName("");
          }}
          onSelectConversation={loadConversation}
          onStartConversation={startNewConversation}
          onToggleCollapsed={() => setSidebarCollapsed((value) => !value)}
          unfiledConversations={unfiledConversations}
        />
        <div className="chat-main">
          <Transcript
            turns={turns}
            showDetails={showDetails}
            loading={loading}
            emptyStateMessage={emptyTranscriptMessage}
            onOpenFeedback={openFeedback}
            onOpenGuideMe={openGuideMe}
          />
          {error ? <div className="error-banner">{error}</div> : null}
          <Composer
            attachments={attachments}
            disabled={loading}
            dragActive={dragActive}
            guideMeActive={guideMeOpen}
            guideMeBusy={guideMeBusy}
            uploadError={uploadError}
            uploading={uploading}
            value={draft}
            onChange={setDraft}
            onDragStateChange={setDragActive}
            onFileSelect={uploadFiles}
            onGuideMe={openGuideMe}
            onRemoveAttachment={(attachmentId) =>
              setAttachments((current) => current.filter((attachment) => attachment.id !== attachmentId))
            }
            onSubmit={handleSubmit}
          />
          {isMobile ? (
            <div className="app-disclaimer app-disclaimer-compact">
              <button className="app-disclaimer-link" type="button" onClick={() => setShowDisclaimerModal(true)}>
                Important disclaimer
              </button>
            </div>
          ) : (
            <div className="app-disclaimer">
              HermanScience is not responsible for the accuracy or confidentiality of information provided by the AI.
              This platform is not designed to offer professional, legal, medical or other advice. Please consult
              with the appropriate experts for this type of advice.
            </div>
          )}
        </div>
      </div>
      {showDisclaimerModal ? (
        <div className="modal-backdrop modal-backdrop-elevated" role="presentation">
          <section aria-modal="true" className="feedback-modal legal-notice-modal" role="dialog">
            <div className="feedback-modal-header">
              <div>
                <div className="message-label">Important Notice</div>
                <h2 className="feedback-modal-title">Before you continue</h2>
              </div>
            </div>
            <p className="conversation-modal-copy">
              HermanScience is not responsible for the accuracy or confidentiality of information provided by the AI.
              This platform is not designed to offer professional, legal, medical or other advice. Please consult with
              the appropriate experts for this type of advice.
            </p>
            <div className="feedback-modal-actions">
              <button className="feedback-button" type="button" onClick={() => setShowDisclaimerModal(false)}>
                Dismiss
              </button>
              <button className="send-button" type="button" onClick={acknowledgeDisclaimer}>
                I understand
              </button>
            </div>
          </section>
        </div>
      ) : null}
      {personalContextOpen ? (
        <section className="settings-modal-backdrop" role="presentation" onClick={() => setPersonalContextOpen(false)}>
          <div className="settings-modal" role="dialog" aria-modal="true" onClick={(event) => event.stopPropagation()}>
            <div className="settings-modal-header">
              <div>
                <h2>Personal Settings</h2>
                <p>Manage your private context and the controls that shape the HermanPrompt workspace.</p>
              </div>
              <button className="modal-close" type="button" onClick={() => setPersonalContextOpen(false)}>
                Close
              </button>
            </div>
            {userContextLoading && !userContext ? <p className="muted-panel">Loading personal context…</p> : null}
            {userContext ? (
              <>
                <div className="settings-card">
                  <div className="settings-section-header">
                    <div>
                      <h3>Workspace Settings</h3>
                      <p>Choose your prompt profile, coaching behavior, display preferences, and header score visibility.</p>
                    </div>
                  </div>
                  <div className="settings-control-grid">
                    <label className="settings-field">
                      <span className="profile-picker-label">Type</span>
                      <select
                        aria-label="Select demo profile type"
                        className="profile-picker-select"
                        value={summaryType ?? ""}
                        onChange={(event) => {
                          const nextValue = event.target.value;
                          applySummaryType(nextValue ? Number(nextValue) : null);
                        }}
                      >
                        <option value="">{formatDefaultProfileLabel(transformerProfile, session, summaryType)}</option>
                        {Array.from({ length: 9 }, (_, index) => index + 1).map((value) => (
                          <option key={value} value={value}>
                            Type {value}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="settings-field">
                      <span className="profile-picker-label">Coaching level</span>
                      <select
                        aria-label="Select prompt enforcement level"
                        className="profile-picker-select"
                        value={enforcementLevel}
                        onChange={(event) =>
                          applyEnforcementLevel(event.target.value as "none" | "low" | "moderate" | "full")
                        }
                      >
                        <option value="none">None</option>
                        <option value="low">Low</option>
                        <option value="moderate">Moderate</option>
                        <option value="full">Full</option>
                      </select>
                    </label>
                    {launchParams.showFullDemo ? (
                      <>
                        <label className="toggle settings-toggle-row">
                          <span className="toggle-label">Show transformation</span>
                          <button
                            aria-pressed={showDetails}
                            className={`toggle-switch ${showDetails ? "is-on" : ""}`}
                            type="button"
                            onClick={() => setShowDetails((value) => !value)}
                          >
                            <span className="toggle-thumb" />
                          </button>
                        </label>
                        <label className="toggle settings-toggle-row">
                          <span className="toggle-label">Use transformer</span>
                          <button
                            aria-pressed={transformEnabled}
                            className={`toggle-switch ${transformEnabled ? "is-on" : ""}`}
                            type="button"
                            onClick={() => resetConversation(!transformEnabled)}
                          >
                            <span className="toggle-thumb" />
                          </button>
                        </label>
                      </>
                    ) : null}
                    <div className="settings-field">
                      <span className="profile-picker-label">Theme</span>
                      <div className="theme-selector" role="group" aria-label="Select theme">
                        <button
                          aria-pressed={theme === "light"}
                          className={`theme-selector-button ${theme === "light" ? "is-active" : ""}`}
                          type="button"
                          onClick={() => setTheme("light")}
                        >
                          Light
                        </button>
                        <button
                          aria-pressed={theme === "dark"}
                          className={`theme-selector-button ${theme === "dark" ? "is-active" : ""}`}
                          type="button"
                          onClick={() => setTheme("dark")}
                        >
                          Dark
                        </button>
                      </div>
                    </div>
                    <label className="toggle settings-toggle-row">
                      <span className="toggle-label">Show scores in header</span>
                      <button
                        aria-pressed={showHeaderScores}
                        className={`toggle-switch ${showHeaderScores ? "is-on" : ""}`}
                        type="button"
                        onClick={() => setShowHeaderScores((value) => !value)}
                      >
                        <span className="toggle-thumb" />
                      </button>
                    </label>
                  </div>
                </div>
                <label className="toggle personal-context-toggle">
                  <span className="toggle-label">Use my personal context</span>
                  <button
                    aria-pressed={userContext.settings.retrieval_enabled}
                    className={`toggle-switch ${userContext.settings.retrieval_enabled ? "is-on" : ""}`}
                    type="button"
                    onClick={() => void updateUserContextSettings(!userContext.settings.retrieval_enabled)}
                  >
                    <span className="toggle-thumb" />
                  </button>
                </label>
                <div className="settings-card-grid">
                  <div className="settings-card">
                    <h3>Effective Limits</h3>
                    <p>Source: {userContext.limits.source}</p>
                    <p>Max file: {formatBytes(userContext.limits.max_file_bytes)}</p>
                    <p>Max docs: {userContext.limits.max_document_count}</p>
                    <p>Max storage: {formatBytes(userContext.limits.max_total_bytes)}</p>
                    <p>Max extracted text: {formatBytes(userContext.limits.max_extracted_text_bytes)}</p>
                    <p>Max chunks/doc: {userContext.limits.max_chunks_per_document}</p>
                    <p>Retrieved per answer: {userContext.limits.max_retrieved_chunks}</p>
                  </div>
                  <div className="settings-card">
                    <h3>Usage</h3>
                    <p>{userContext.usage.document_count} / {userContext.limits.max_document_count} docs</p>
                    <p>{formatBytes(userContext.usage.total_bytes)} / {formatBytes(userContext.limits.max_total_bytes)}</p>
                    <p>Ready: {userContext.usage.ready_documents}</p>
                    <p>Processing: {userContext.usage.processing_documents}</p>
                    <p>Failed: {userContext.usage.failed_documents}</p>
                  </div>
                </div>
                <label className="settings-upload">
                  <span>Upload documents</span>
                  <input
                    type="file"
                    accept=".pdf,.docx,.txt,.md,.csv"
                    multiple
                    onChange={(event) => void uploadUserContextFiles(event.target.files)}
                  />
                </label>
                <div className="settings-document-list">
                  {userContext.documents.map((document) => (
                    <div className="settings-document-row" key={document.id}>
                      <div>
                        <strong>{document.filename}</strong>
                        <div className="muted-line">
                          {document.status} · {formatBytes(document.size_bytes)}
                          {document.status_message ? ` · ${document.status_message}` : ""}
                        </div>
                      </div>
                      <button
                        className="danger-text-button"
                        type="button"
                        disabled={userContextBusy}
                        onClick={() => void deleteUserContextDocument(document.id)}
                      >
                        Delete
                      </button>
                    </div>
                  ))}
                  {userContext.documents.length === 0 ? <p className="muted-panel">No personal documents uploaded yet.</p> : null}
                </div>
              </>
            ) : null}
            {userContextError ? <p className="error-banner">{userContextError}</p> : null}
          </div>
        </section>
      ) : null}
      {feedbackDraft ? (
        <FeedbackModal
          comments={feedbackDraft.comments}
          error={feedbackDraft.error}
          feedbackType={feedbackDraft.feedbackType}
          onOpenGuideMe={() => openGuideMe(turns.find((turn) => turn.id === feedbackDraft.turnId)?.userText)}
          selectedDimensions={feedbackDraft.selectedDimensions}
          submitting={feedbackDraft.submitting}
          onClose={() => {
            setTurns((current) =>
              current.map((turn) =>
                turn.id === feedbackDraft.turnId && turn.feedbackStatus === "submitting"
                  ? { ...turn, feedbackStatus: "idle" }
                  : turn,
              ),
            );
            setFeedbackDraft(null);
          }}
          onCommentsChange={(value) =>
            setFeedbackDraft((current) => (current ? { ...current, comments: value } : current))
          }
          onSubmit={submitFeedback}
          onToggleDimension={toggleFeedbackDimension}
        />
      ) : null}
      {renameTarget ? (
        <RenameDialog
          busy={conversationActionBusy}
          label={renameTarget.kind === "conversation" ? "Conversation name" : "Folder name"}
          title={renameTarget.kind === "conversation" ? "Rename conversation" : "Rename folder"}
          value={renameValue}
          onChange={setRenameValue}
          onClose={() => {
            setRenameTarget(null);
            setRenameValue("");
          }}
          onSave={saveRename}
        />
      ) : null}
      {moveConversationTarget ? (
        <MoveConversationDialog
          busy={conversationActionBusy}
          folders={conversationFolders}
          newFolderName={newFolderName}
          selectedFolderId={moveTargetFolderId}
          title={moveConversationTarget.title}
          onChangeNewFolderName={setNewFolderName}
          onChangeSelectedFolderId={setMoveTargetFolderId}
          onClose={() => {
            setMoveConversationTarget(null);
            setMoveTargetFolderId("");
            setNewFolderName("");
          }}
          onSave={moveConversationToFolder}
        />
      ) : null}
      {folderDeleteTarget ? (
        <DeleteFolderDialog
          busy={conversationActionBusy}
          conversationCount={folderDeleteTarget.conversations.length}
          folderName={folderDeleteTarget.name}
          onClose={() => setFolderDeleteTarget(null)}
          onDeleteFolderAndContents={() => void deleteFolder("delete_contents")}
          onDeleteFolderOnly={() => void deleteFolder("unfile")}
        />
      ) : null}
      <GuideMePanel
        answer={guideMeAnswer}
        busy={guideMeBusy}
        pendingAction={guideMePendingAction}
        submitProgressPercent={guideMeSubmitProgressPercent}
        error={guideMeError}
        open={guideMeOpen}
        session={guideMeSession}
        showDetails={showDetails}
        onAnswerChange={setGuideMeAnswer}
        onCancel={cancelGuideMe}
        onClose={() => setGuideMeOpen(false)}
        onLaunch={startGuideMe}
        onRestart={restartGuideMe}
        onSubmit={submitGuideMeAnswer}
        onUpdateDraft={updateGuideMeDraft}
        onUsePrompt={useGuideMePrompt}
      />
    </main>
  );
}

function formatBytes(value: number) {
  if (value >= 1024 * 1024) {
    return `${(value / (1024 * 1024)).toFixed(1)} MB`;
  }
  if (value >= 1024) {
    return `${Math.round(value / 1024)} KB`;
  }
  return `${value} B`;
}

type RenameDialogProps = {
  busy: boolean;
  label: string;
  title: string;
  value: string;
  onChange: (value: string) => void;
  onClose: () => void;
  onSave: () => void;
};

function RenameDialog({ busy, label, title, value, onChange, onClose, onSave }: RenameDialogProps) {
  return (
    <div className="modal-backdrop" role="presentation">
      <section aria-modal="true" className="feedback-modal conversation-modal" role="dialog">
        <div className="feedback-modal-header">
          <div>
            <div className="message-label">Rename</div>
            <h2 className="feedback-modal-title">{title}</h2>
          </div>
          <button className="modal-close" type="button" onClick={onClose}>
            Close
          </button>
        </div>
        <label className="feedback-comment-field">
          <span className="message-label">{label}</span>
          <input className="feedback-comment-input conversation-text-input" value={value} onChange={(event) => onChange(event.target.value)} />
        </label>
        <div className="feedback-modal-actions">
          <button className="feedback-button" type="button" onClick={onClose}>
            Cancel
          </button>
          <button className="send-button" disabled={busy || !value.trim()} type="button" onClick={onSave}>
            Save
          </button>
        </div>
      </section>
    </div>
  );
}

type MoveConversationDialogProps = {
  busy: boolean;
  folders: ConversationFolder[];
  newFolderName: string;
  selectedFolderId: string;
  title: string;
  onChangeNewFolderName: (value: string) => void;
  onChangeSelectedFolderId: (value: string) => void;
  onClose: () => void;
  onSave: () => void;
};

function MoveConversationDialog({
  busy,
  folders,
  newFolderName,
  selectedFolderId,
  title,
  onChangeNewFolderName,
  onChangeSelectedFolderId,
  onClose,
  onSave,
}: MoveConversationDialogProps) {
  return (
    <div className="modal-backdrop" role="presentation">
      <section aria-modal="true" className="feedback-modal conversation-modal" role="dialog">
        <div className="feedback-modal-header">
          <div>
            <div className="message-label">File Conversation</div>
            <h2 className="feedback-modal-title">{title}</h2>
          </div>
          <button className="modal-close" type="button" onClick={onClose}>
            Close
          </button>
        </div>
        <label className="feedback-comment-field">
          <span className="message-label">Existing folder</span>
          <select
            className="profile-picker-select conversation-select"
            value={selectedFolderId}
            onChange={(event) => onChangeSelectedFolderId(event.target.value)}
          >
            <option value="">Unfiled</option>
            {folders.map((folder) => (
              <option key={folder.id} value={folder.id}>
                {folder.name}
              </option>
            ))}
          </select>
        </label>
        <label className="feedback-comment-field">
          <span className="message-label">Or create a new folder</span>
          <input
            className="feedback-comment-input conversation-text-input"
            placeholder="New folder name"
            value={newFolderName}
            onChange={(event) => onChangeNewFolderName(event.target.value)}
          />
        </label>
        <div className="feedback-modal-actions">
          <button className="feedback-button" type="button" onClick={onClose}>
            Cancel
          </button>
          <button className="send-button" disabled={busy} type="button" onClick={onSave}>
            Save
          </button>
        </div>
      </section>
    </div>
  );
}

type DeleteFolderDialogProps = {
  busy: boolean;
  conversationCount: number;
  folderName: string;
  onClose: () => void;
  onDeleteFolderAndContents: () => void;
  onDeleteFolderOnly: () => void;
};

function DeleteFolderDialog({
  busy,
  conversationCount,
  folderName,
  onClose,
  onDeleteFolderAndContents,
  onDeleteFolderOnly,
}: DeleteFolderDialogProps) {
  return (
    <div className="modal-backdrop" role="presentation">
      <section aria-modal="true" className="feedback-modal conversation-modal" role="dialog">
        <div className="feedback-modal-header">
          <div>
            <div className="message-label">Delete Folder</div>
            <h2 className="feedback-modal-title">{folderName}</h2>
          </div>
          <button className="modal-close" type="button" onClick={onClose}>
            Close
          </button>
        </div>
        <p className="conversation-modal-copy">
          This folder contains {conversationCount} saved conversation{conversationCount === 1 ? "" : "s"}.
        </p>
        <div className="conversation-modal-actions">
          <button className="feedback-button" disabled={busy} type="button" onClick={onClose}>
            Cancel
          </button>
          <button className="feedback-button" disabled={busy} type="button" onClick={onDeleteFolderOnly}>
            Delete folder only
          </button>
          <button className="send-button danger-button" disabled={busy} type="button" onClick={onDeleteFolderAndContents}>
            Delete folder and conversations
          </button>
        </div>
      </section>
    </div>
  );
}

function mapConversationSummary(conversation: {
  id: string;
  title: string;
  folder_id?: string | null;
  created_at: string;
  updated_at: string;
}): ConversationSummary {
  return {
    id: conversation.id,
    title: conversation.title,
    folderId: conversation.folder_id ?? null,
    createdAt: conversation.created_at,
    updatedAt: conversation.updated_at,
  };
}

function deriveCoachingRequirements(
  userText: string,
  conversation: TransformerConversation | null,
  resultType: "transformed" | "coaching" | "blocked",
  coachingTip: string | null,
): Record<string, CoachingRequirementIndicator> | undefined {
  const shouldShowIndicators = resultType !== "transformed" || Boolean(coachingTip?.trim());
  if (!shouldShowIndicators || !conversation?.requirements) {
    return undefined;
  }

  const labels: Record<string, string> = {
    who: "Who",
    task: "Task",
    context: "Context",
    output: "Output",
  };

  const indicators: Record<string, CoachingRequirementIndicator> = {};
  for (const key of ["who", "task", "context", "output"]) {
    const requirement = conversation.requirements[key];
    const status = requirement?.status;
    indicators[key] = {
      label: labels[key],
      state: indicatorStateForRequirement(userText, key, status),
    };
  }
  return indicators;
}

function indicatorStateForRequirement(
  userText: string,
  key: string,
  status: string | undefined,
): "met" | "partial" | "missing" {
  if (!status || status === "missing") {
    return "missing";
  }
  if (status === "derived") {
    return "partial";
  }
  return hasExplicitLabel(userText, key) ? "met" : "partial";
}

function hasExplicitLabel(userText: string, key: string): boolean {
  const normalized = userText.toLowerCase();
  const labels: Record<string, string> = {
    who: "who:",
    task: "task:",
    context: "context:",
    output: "output:",
  };
  return normalized.includes(labels[key] ?? "");
}

function mapGuideMeSession(session: GuideMeApiSession): GuideMeSession {
  const requirements = Object.fromEntries(
    Object.entries(session.requirements ?? {}).map(([key, requirement]) => [
      key,
      {
        label: requirement.label,
        state: requirement.state,
        heuristicScore: requirement.heuristic_score ?? null,
        llmScore: requirement.llm_score ?? null,
        maxScore: requirement.max_score ?? null,
        reason: requirement.reason ?? null,
        improvementHint: requirement.improvement_hint ?? null,
      },
    ]),
  );

  return {
    sessionId: session.session_id,
    conversationId: session.conversation_id,
    status: session.status,
    currentStep: session.current_step,
    questionTitle: session.question_title ?? null,
    questionText: session.question_text ?? null,
    answers: session.answers ?? {},
    requirements,
    requirementDebug: session.requirement_debug ?? {},
    decisionTrace: session.decision_trace ?? {},
    personalization: {
      firstName: session.personalization.first_name,
      typicalAiUsage: session.personalization.typical_ai_usage,
      profileLabel: session.personalization.profile_label,
      recentExamples: session.personalization.recent_examples ?? [],
    },
    guidanceText: session.guidance_text ?? null,
    followUpQuestions: session.follow_up_questions ?? [],
    finalPrompt: session.final_prompt ?? null,
    readyToInsert: session.ready_to_insert,
  };
}

function delay(ms: number) {
  return new Promise<void>((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

function formatDefaultProfileLabel(
  transformerProfile: TransformerProfileMetadata,
  session: SessionBootstrap | null,
  summaryType: number | null,
) {
  if (summaryType !== null) {
    return `Type ${summaryType}`;
  }

  const sessionLabel = session?.profile_label?.trim();
  if (sessionLabel) {
    return sessionLabel;
  }

  const raw = (transformerProfile.profileVersion ?? session?.profile_version ?? "").trim();
  if (!raw) {
    return "Loaded Profile";
  }

  if (raw.startsWith("summary_type_")) {
    const suffix = raw.slice("summary_type_".length);
    return `Type ${suffix}`;
  }

  if (raw === "generic_default") {
    return "Generic Default";
  }

  return raw
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function buildWelcomeMessage(
  session: SessionBootstrap | null,
  enforcementLevel: EnforcementLevel,
  summaryType: number | null,
  transformerProfile: TransformerProfileMetadata,
) {
  const firstName = getFirstName(session?.display_name);
  const profileLabel = formatDefaultProfileLabel(transformerProfile, session, summaryType);
  const coachingLevel = formatEnforcementLabel(enforcementLevel);
  return `Welcome ${firstName} your ${profileLabel} profile is loaded. Your coaching level is ${coachingLevel}. Enter a prompt to begin.`;
}

function getFirstName(displayName: string | null | undefined) {
  const normalized = (displayName ?? "").trim();
  if (!normalized) {
    return "there";
  }

  const [firstName] = normalized.split(/\s+/);
  return firstName || "there";
}

function formatEnforcementLabel(enforcementLevel: EnforcementLevel) {
  return enforcementLevel.replace(/\b\w/g, (char) => char.toUpperCase());
}

function getBlockingStateTitle(sessionError: string | null) {
  if (sessionError?.toLowerCase().includes("profile not found")) {
    return "Profile unavailable";
  }
  return "Authentication required";
}

async function extractErrorMessage(response: Response, fallbackMessage: string) {
  try {
    const payload = (await response.json()) as { detail?: string };
    if (typeof payload.detail === "string" && payload.detail.trim()) {
      return payload.detail.trim();
    }
  } catch {
    return fallbackMessage;
  }

  return fallbackMessage;
}
