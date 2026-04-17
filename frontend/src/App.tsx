import { useEffect, useState } from "react";
import { Composer, type UploadedAttachment } from "./components/Composer";
import { ConversationSidebar, type ConversationSummary } from "./components/ConversationSidebar";
import { FeedbackModal } from "./components/FeedbackModal";
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
      if (payload.metadata.transformer.result_type === "coaching") {
        setConversationNotice(payload.metadata.transformer.coaching_tip ?? "Prompt guidance returned. Review the latest assistant message before retrying.");
      } else if (payload.metadata.transformer.result_type === "blocked") {
        setConversationNotice(payload.metadata.transformer.blocking_message ?? "Request blocked by transformer checks. Review the latest assistant message.");
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
    setTurns([]);
    setDraft("");
    setAttachments([]);
    setUploadError(null);
    setError(null);
    setFeedbackDraft(null);
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
    setTurns([]);
    setDraft("");
    setAttachments([]);
    setUploadError(null);
    setError(null);
    setFeedbackDraft(null);
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
    setTurns([]);
    setDraft("");
    setAttachments([]);
    setUploadError(null);
    setError(null);
    setFeedbackDraft(null);
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
        turns: {
          id: string;
          user_text: string;
          transformed_text: string;
          assistant_text: string;
          transformation_applied: boolean;
          assistant_images: { media_type: string; base64_data: string }[];
        }[];
      };

      setConversationId(payload.id.replace(/^conv_/, ""));
      setTransformerConversation(payload.transformer_conversation ?? null);
      setTurns(
        payload.turns.map((turn) => ({
          id: turn.id,
          userText: turn.user_text,
          transformedText: turn.transformed_text,
          assistantText: turn.assistant_text,
          transformationApplied: turn.transformation_applied,
          assistantKind: "assistant",
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
    setTurns([]);
    setDraft("");
    setAttachments([]);
    setUploadError(null);
    setError(null);
    setFeedbackDraft(null);
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
          onDeleteConversation={deleteConversation}
          onExportConversation={exportConversation}
          onSelectConversation={loadConversation}
          onStartConversation={startNewConversation}
          onToggleCollapsed={() => setSidebarCollapsed((value) => !value)}
        />
        <div className="chat-main">
          {conversationNotice ? <div className="status-banner">{conversationNotice}</div> : null}
          <Transcript turns={turns} showDetails={showDetails} loading={loading} onOpenFeedback={openFeedback} />
          {error ? <div className="error-banner">{error}</div> : null}
          <Composer
            attachments={attachments}
            disabled={loading}
            dragActive={dragActive}
            uploadError={uploadError}
            uploading={uploading}
            value={draft}
            onChange={setDraft}
            onDragStateChange={setDragActive}
            onFileSelect={uploadFiles}
            onRemoveAttachment={(attachmentId) =>
              setAttachments((current) => current.filter((attachment) => attachment.id !== attachmentId))
            }
            onSubmit={handleSubmit}
          />
        </div>
      </div>
      {feedbackDraft ? (
        <FeedbackModal
          comments={feedbackDraft.comments}
          error={feedbackDraft.error}
          feedbackType={feedbackDraft.feedbackType}
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
    </main>
  );
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
