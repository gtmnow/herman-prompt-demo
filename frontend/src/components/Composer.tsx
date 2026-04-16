export type UploadedAttachment = {
  id: string;
  kind: "document" | "image";
  name: string;
  mediaType?: string | null;
  providerFileId?: string | null;
  sizeBytes?: number | null;
};

type ComposerProps = {
  disabled: boolean;
  dragActive: boolean;
  attachments: UploadedAttachment[];
  uploadError: string | null;
  uploading: boolean;
  value: string;
  onFileSelect: (files: FileList | null) => void;
  onRemoveAttachment: (attachmentId: string) => void;
  onChange: (value: string) => void;
  onSubmit: () => void;
  onDragStateChange: (dragActive: boolean) => void;
};

export function Composer({
  disabled,
  dragActive,
  attachments,
  uploadError,
  uploading,
  value,
  onFileSelect,
  onRemoveAttachment,
  onChange,
  onSubmit,
  onDragStateChange,
}: ComposerProps) {
  return (
    <div
      className={`composer-shell ${dragActive ? "is-drag-active" : ""}`}
      onDragEnter={(event) => {
        event.preventDefault();
        onDragStateChange(true);
      }}
      onDragLeave={(event) => {
        event.preventDefault();
        const nextTarget = event.relatedTarget as Node | null;
        if (!nextTarget || !event.currentTarget.contains(nextTarget)) {
          onDragStateChange(false);
        }
      }}
      onDragOver={(event) => {
        event.preventDefault();
        onDragStateChange(true);
      }}
      onDrop={(event) => {
        event.preventDefault();
        onDragStateChange(false);
        onFileSelect(event.dataTransfer.files);
      }}
    >
      <input
        aria-hidden="true"
        className="file-input-hidden"
        id="composer-file-input"
        type="file"
        accept=".pdf,.doc,.docx,.txt,.md,.png,.jpg,.jpeg,.webp,.gif,image/*"
        multiple
        onChange={(event) => {
          onFileSelect(event.target.files);
          event.currentTarget.value = "";
        }}
      />
      {attachments.length > 0 ? (
        <div className="attachment-list">
          {attachments.map((attachment) => (
            <div key={attachment.id} className="attachment-chip">
              <span className="attachment-kind" aria-hidden="true">
                {attachment.kind === "image" ? "Image" : "File"}
              </span>
              <span className="attachment-name">{attachment.name}</span>
              <button
                aria-label={`Remove ${attachment.name}`}
                className="attachment-remove"
                disabled={disabled || uploading}
                type="button"
                onClick={() => onRemoveAttachment(attachment.id)}
              >
                ×
              </button>
            </div>
          ))}
        </div>
      ) : null}
      <textarea
        aria-label="Prompt input"
        className="composer-input"
        disabled={disabled}
        placeholder={dragActive ? "Drop file to attach" : "Ask anything"}
        rows={3}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            onSubmit();
          }
        }}
      />
      {uploadError ? <div className="composer-note composer-note-error">{uploadError}</div> : null}
      {uploading ? <div className="composer-note">Uploading attachment...</div> : null}
      <div className="composer-actions">
        <label className="attach-button" htmlFor="composer-file-input">
          +
        </label>
        <button
          className="send-button"
          disabled={disabled || uploading || (!value.trim() && attachments.length === 0)}
          type="button"
          onClick={onSubmit}
        >
          Send
        </button>
      </div>
    </div>
  );
}
