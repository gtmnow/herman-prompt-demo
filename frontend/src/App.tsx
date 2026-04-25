import { useEffect, useState } from "react";
import { Composer, type UploadedAttachment } from "./components/Composer";
import { ConversationSidebar, type ConversationSummary } from "./components/ConversationSidebar";
import { FeedbackModal } from "./components/FeedbackModal";
import { GuideMePanel, type GuideMeSession } from "./components/GuideMePanel";
import { Header } from "./components/Header";
import { Transcript, type TranscriptTurn } from "./components/Transcript";
import { getLaunchParams, type ThemeMode } from "./lib/queryParams";

const DEMO_RESPONSE =
  "This is a starter scaffold response. The real app will replace this with the configured LLM output.";

type TransformerConversation = {
  conversation_id: string;
  requirements: Record<string, { value?: string | null; status: string }>;
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
  deterministic_score?: number | null;
  ai_score?: number | null;
  max_score?: number;
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
  };
};

function createConversationId() {
  return Math.random().toString(36).slice(2, 10);
}

export function App() {
  const launchParams = getLaunchParams(window.location.search);
  const [isMobile, setIsMobile] = useState(() => window.matchMedia("(max-width: 860px)").matches);
  const [session, setSession] = useState<SessionBootstrap | null>(null);
  const [sessionLoading, setSessionLoading] = useState(true);
  const [sessionError, setSessionError] = useState<string | null>(null);
  const [showDetails, setShowDetails] = useState(launchParams.showDetails);
  const [transformEnabled, setTransformEnabled] = useState(launchParams.transformEnabled);
  const [summaryType, setSummaryType] = useState<number | null>(launchParams.summaryType);
  const [enforcementLevel, setEnforcementLevel] = useState<EnforcementLevel>("none");
  const [theme, setTheme] = useState<ThemeMode>(launchParams.theme);
  const [draft, setDraft] = useState("");
  const [attachments, setAttachments] = useState<UploadedAttachment[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [conversationNotice, setConversationNotice] = useState<string | null>(null);
  const [turns, setTurns] = useState<TranscriptTurn[]>([]);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => window.matchMedia("(max-width: 860px)").matches);
  const [loadingConversations, setLoadingConversations] = useState(false);
  const [conversationListError, setConversationListError] = useState<string | null>(null);
  const [conversationActionBusy, setConversationActionBusy] = useState(false);
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
  const [guideMeSession, setGuideMeSession] = useState<GuideMeSession | null>(null);
  const [guideMeOpen, setGuideMeOpen] = useState(false);
  const [guideMeBusy, setGuideMeBusy] = useState(false);
  const [guideMeAnswer, setGuideMeAnswer] = useState("");
  const [guideMeError, setGuideMeError] = useState<string | null>(null);

  const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8002";

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
    const mediaQuery = window.matchMedia("(max-width: 860px)");
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
    if (!session?.access_token) {
      return;
    }

    void loadConversationSummaries();
  }, [session?.access_token]);

  useEffect(() => {
    if (!session?.access_token) {
      return;
    }

    void loadGuideMeSession(`conv_${conversationId}`);
  }, [conversationId, session?.access_token]);

  const inheritedEnforcementLevel = getInheritedEnforcementLevel(session?.user_id_hash ?? null);

  useEffect(() => {
    setEnforcementLevel(inheritedEnforcementLevel);
  }, [inheritedEnforcementLevel]);

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

  async function startGuideMe(forceRestart = false, sourcePrompt?: string) {
    if (!session || guideMeBusy) {
      return;
    }

    if (!forceRestart && guideMeSession && guideMeSession.status !== "cancelled") {
      setGuideMeOpen((value) => !value);
      return;
    }

    setGuideMeBusy(true);
    setGuideMeError(null);

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
      setConversationNotice("Guide Me is ready.");
    } catch (guideError) {
      setGuideMeError(guideError instanceof Error ? guideError.message : "Unable to start Guide Me.");
      setGuideMeOpen(true);
    } finally {
      setGuideMeBusy(false);
    }
  }

  function openGuideMe(sourcePrompt?: string) {
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

    setGuideMeBusy(true);
    setGuideMeError(null);

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
      if (payload.session?.ready_to_insert) {
        setConversationNotice("Guide Me built a formatted prompt. Review it and insert it when ready.");
      }
    } catch (guideError) {
      setGuideMeError(guideError instanceof Error ? guideError.message : "Unable to continue Guide Me.");
    } finally {
      setGuideMeBusy(false);
    }
  }

  async function cancelGuideMe() {
    if (!session || !guideMeSession || guideMeBusy) {
      setGuideMeOpen(false);
      return;
    }

    setGuideMeBusy(true);
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
      setConversationNotice("Guide Me cancelled.");
    } catch (guideError) {
      setGuideMeError(guideError instanceof Error ? guideError.message : "Unable to cancel Guide Me.");
    } finally {
      setGuideMeBusy(false);
    }
  }

  function useGuideMePrompt() {
    if (!guideMeSession?.finalPrompt) {
      return;
    }

    setDraft(guideMeSession.finalPrompt);
    setGuideMeOpen(false);
    setGuideMeError(null);
    setConversationNotice("Guide Me moved the formatted prompt into the composer.");
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
      if (payload.metadata.transformer.result_type === "coaching") {
        setConversationNotice(null);
      } else if (payload.metadata.transformer.result_type === "blocked") {
        setConversationNotice(null);
      } else {
        setConversationNotice(null);
      }
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
    setConversationNotice(
      nextTransformEnabled
        ? "Conversation reset. Prompt Transformer is now on."
        : "Conversation reset. Prompt Transformer is now off.",
    );
  }

  function applySummaryType(nextSummaryType: number | null) {
    setSummaryType(nextSummaryType);
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
    setConversationNotice(
      nextSummaryType === null
        ? "Conversation reset. Using the selected user's default profile."
        : `Conversation reset. Using demo profile type ${nextSummaryType}.`,
    );
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
    setConversationNotice(`Conversation reset. Using ${nextEnforcementLevel} enforcement.`);
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
        conversations: { id: string; title: string; created_at: string; updated_at: string }[];
      };

      setConversations(
        payload.conversations.map((conversation) => ({
          id: conversation.id,
          title: conversation.title,
          createdAt: conversation.created_at,
          updatedAt: conversation.updated_at,
        })),
      );
    } catch (loadError) {
      setConversations([]);
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
      setConversationNotice("Loaded saved conversation.");
      setDraft("");
      setAttachments([]);
      setUploadError(null);
      setGuideMeAnswer("");
      setGuideMeError(null);
      setGuideMeOpen(false);
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
    if (isMobile) {
      setSidebarCollapsed(true);
    }
    setConversationNotice("Started a new conversation.");
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
      setConversationNotice("Conversation deleted.");
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : "Unable to delete conversation.");
    } finally {
      setConversationActionBusy(false);
    }
  }

  async function deleteAllConversations() {
    if (!session || conversations.length === 0) {
      return;
    }
    if (
      !window.confirm(
        "Delete all saved conversations from HermanPrompt? Prompt score history will remain in the scoring database.",
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

      setConversations([]);
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
      if (isMobile) {
        setSidebarCollapsed(true);
      }
      setConversationNotice("All saved conversations were deleted. Prompt score history was preserved.");
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : "Unable to delete conversations.");
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
          showDetails={showDetails}
          transformEnabled={transformEnabled}
          summaryType={summaryType}
          enforcementLevel={enforcementLevel}
          scoring={transformerScoring ? {
            initialLlmScore: transformerScoring.initial_llm_score,
            initialScore: transformerScoring.initial_score,
            finalLlmScore: transformerScoring.final_llm_score,
            finalScore: transformerScoring.final_score,
          } : null}
          theme={theme}
          onToggleDetails={() => setShowDetails((value) => !value)}
          onToggleTransform={() => resetConversation(!transformEnabled)}
          onChangeSummaryType={applySummaryType}
          onChangeEnforcementLevel={applyEnforcementLevel}
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
          showDetails={showDetails}
          transformEnabled={transformEnabled}
          summaryType={summaryType}
          enforcementLevel={enforcementLevel}
          scoring={transformerScoring ? {
            initialLlmScore: transformerScoring.initial_llm_score,
            initialScore: transformerScoring.initial_score,
            finalLlmScore: transformerScoring.final_llm_score,
            finalScore: transformerScoring.final_score,
          } : null}
          theme={theme}
          onToggleDetails={() => setShowDetails((value) => !value)}
          onToggleTransform={() => resetConversation(!transformEnabled)}
          onChangeSummaryType={applySummaryType}
          onChangeEnforcementLevel={applyEnforcementLevel}
        />
        <section className="blocking-state">
          <h1>Authentication required</h1>
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
        showDetails={showDetails}
        transformEnabled={transformEnabled}
        summaryType={summaryType}
        enforcementLevel={enforcementLevel}
        scoring={transformerScoring ? {
          initialLlmScore: transformerScoring.initial_llm_score,
          initialScore: transformerScoring.initial_score,
          finalLlmScore: transformerScoring.final_llm_score,
          finalScore: transformerScoring.final_score,
        } : null}
        theme={theme}
        onToggleDetails={() => setShowDetails((value) => !value)}
        onToggleTransform={() => resetConversation(!transformEnabled)}
        onChangeSummaryType={applySummaryType}
        onChangeEnforcementLevel={applyEnforcementLevel}
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
          conversations={conversations}
          error={conversationListError}
          loading={loadingConversations}
          onDeleteAllConversations={deleteAllConversations}
          onDeleteConversation={deleteConversation}
          onExportConversation={exportConversation}
          onSelectConversation={loadConversation}
          onStartConversation={startNewConversation}
          onToggleCollapsed={() => setSidebarCollapsed((value) => !value)}
        />
        <div className="chat-main">
          {conversationNotice ? <div className="status-banner">{conversationNotice}</div> : null}
          <Transcript
            turns={turns}
            showDetails={showDetails}
            loading={loading}
            onOpenFeedback={openFeedback}
            onOpenGuideMe={openGuideMe}
          />
          {error ? <div className="error-banner">{error}</div> : null}
          <Composer
            attachments={attachments}
            disabled={loading}
            dragActive={dragActive}
            guideMeActive={guideMeOpen}
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
          <div className="app-disclaimer">
            HermanScience is not responsible for the accuracy or confidentiality of information provided by the AI.
            This platform is not designed to offer professional, legal, medical or other advice. Please consult
            with the appropriate experts for this type of advice.
          </div>
        </div>
      </div>
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
      <GuideMePanel
        answer={guideMeAnswer}
        busy={guideMeBusy}
        error={guideMeError}
        open={guideMeOpen}
        session={guideMeSession}
        onAnswerChange={setGuideMeAnswer}
        onCancel={cancelGuideMe}
        onClose={() => setGuideMeOpen(false)}
        onLaunch={startGuideMe}
        onRestart={restartGuideMe}
        onSubmit={submitGuideMeAnswer}
        onUsePrompt={useGuideMePrompt}
      />
    </main>
  );
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
        deterministicScore: requirement.deterministic_score ?? null,
        aiScore: requirement.ai_score ?? null,
        maxScore: requirement.max_score ?? 25,
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

function getInheritedEnforcementLevel(userIdHash: string | null): EnforcementLevel {
  switch (userIdHash) {
    case "user_1":
      return "full";
    default:
      return "none";
  }
}
