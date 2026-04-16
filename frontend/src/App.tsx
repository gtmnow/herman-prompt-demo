import { useEffect, useState } from "react";
import { Composer, type UploadedAttachment } from "./components/Composer";
import { FeedbackModal } from "./components/FeedbackModal";
import { Header } from "./components/Header";
import { Transcript, type TranscriptTurn } from "./components/Transcript";
import { getBootstrapState, type ThemeMode } from "./lib/queryParams";

const DEMO_RESPONSE =
  "This is a starter scaffold response. The real app will replace this with the configured LLM output.";

function createConversationId() {
  return `conv_${Math.random().toString(36).slice(2, 10)}`;
}

export function App() {
  const bootstrap = getBootstrapState(window.location.search);
  const [showDetails, setShowDetails] = useState(bootstrap.showDetails);
  const [transformEnabled, setTransformEnabled] = useState(bootstrap.transformEnabled);
  const [summaryType, setSummaryType] = useState<number | null>(bootstrap.summaryType);
  const [theme] = useState<ThemeMode>(bootstrap.theme);
  const [draft, setDraft] = useState("");
  const [attachments, setAttachments] = useState<UploadedAttachment[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [conversationNotice, setConversationNotice] = useState<string | null>(null);
  const [turns, setTurns] = useState<TranscriptTurn[]>([]);
  const [feedbackDraft, setFeedbackDraft] = useState<{
    turnId: string;
    feedbackType: "up" | "down";
    selectedDimensions: string[];
    comments: string;
    submitting: boolean;
    error: string | null;
  } | null>(null);
  const [conversationId, setConversationId] = useState(createConversationId);

  const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8002";

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  async function handleSubmit() {
    const message = draft.trim() || (attachments.length > 0 ? "Please analyze the attached content." : "");
    if (!bootstrap.userIdHash || !message || loading || uploading) {
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const response = await fetch(`${apiBaseUrl}/api/chat/send`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          user_id_hash: bootstrap.userIdHash,
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
          },
        }),
      });

      if (!response.ok) {
        const errorMessage = await extractErrorMessage(response, "Unable to send message.");
        throw new Error(errorMessage);
      }

      const payload = (await response.json()) as {
        turn_id: string;
        user_message: { text: string };
        transformed_message: { text: string };
        assistant_message: { text: string };
        assistant_images: { media_type: string; base64_data: string }[];
        metadata: {
          transformer: {
            transformation_applied: boolean;
          };
        };
      };

      // Transcript rows are stored in the same shape the UI renders so future changes
      // to display logic stay localized to the frontend rather than leaking into the API.
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
          feedbackStatus: "idle",
        },
      ]);
      setDraft("");
      setAttachments([]);
      setUploadError(null);
      setConversationNotice(null);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Something went wrong.");
    } finally {
      setLoading(false);
    }
  }

  async function uploadFiles(files: FileList | null) {
    if (!files || files.length === 0) {
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
    if (!bootstrap.userIdHash || !feedbackDraft) {
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
        },
        body: JSON.stringify({
          turn_id: feedbackDraft.turnId,
          conversation_id: `conv_${conversationId}`,
          user_id_hash: bootstrap.userIdHash,
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
      return;
    }
  }

  function resetConversation(nextTransformEnabled: boolean) {
    // Transformer on/off is treated as a mode boundary. Resetting the conversation keeps
    // prior transformed context from influencing the raw LLM comparison mode and vice versa.
    setTransformEnabled(nextTransformEnabled);
    setConversationId(createConversationId());
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

  if (!bootstrap.userIdHash) {
    return (
      <main className="app-shell">
        <Header
          showDetails={showDetails}
          transformEnabled={transformEnabled}
          summaryType={summaryType}
          theme={theme}
          onToggleDetails={() => setShowDetails((value) => !value)}
          onToggleTransform={() => resetConversation(!transformEnabled)}
          onChangeSummaryType={applySummaryType}
        />
        <section className="blocking-state">
          <h1>Missing user_id_hash</h1>
          <p>The app needs a `user_id_hash` query string to initialize the Prompt Transformer demo.</p>
        </section>
      </main>
    );
  }

  return (
    <main className="app-shell">
      <Header
        showDetails={showDetails}
        transformEnabled={transformEnabled}
        summaryType={summaryType}
        theme={theme}
        onToggleDetails={() => setShowDetails((value) => !value)}
        onToggleTransform={() => resetConversation(!transformEnabled)}
        onChangeSummaryType={applySummaryType}
      />
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
