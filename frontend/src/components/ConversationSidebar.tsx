export type ConversationSummary = {
  id: string;
  title: string;
  folderId: string | null;
  createdAt: string;
  updatedAt: string;
};

export type ConversationFolder = {
  id: string;
  name: string;
  createdAt: string;
  updatedAt: string;
  conversations: ConversationSummary[];
};

type ConversationSidebarProps = {
  collapsed: boolean;
  isMobile: boolean;
  unfiledConversations: ConversationSummary[];
  folders: ConversationFolder[];
  error: string | null;
  activeConversationId: string;
  loading: boolean;
  actionBusy: boolean;
  onSelectConversation: (conversationId: string) => void;
  onStartConversation: () => void;
  onToggleCollapsed: () => void;
  onDeleteConversation: (conversationId: string) => void;
  onDeleteAllConversations: () => void;
  onExportConversation: (conversationId: string) => void;
  onOpenConversationRename: (conversation: ConversationSummary) => void;
  onOpenFolderRename: (folder: ConversationFolder) => void;
  onOpenMoveConversation: (conversation: ConversationSummary) => void;
  onOpenDeleteFolder: (folder: ConversationFolder) => void;
};

export function ConversationSidebar({
  collapsed,
  isMobile,
  unfiledConversations,
  folders,
  error,
  activeConversationId,
  loading,
  actionBusy,
  onSelectConversation,
  onStartConversation,
  onToggleCollapsed,
  onDeleteConversation,
  onDeleteAllConversations,
  onExportConversation,
  onOpenConversationRename,
  onOpenFolderRename,
  onOpenMoveConversation,
  onOpenDeleteFolder,
}: ConversationSidebarProps) {
  const hasConversations = unfiledConversations.length > 0 || folders.some((folder) => folder.conversations.length > 0);
  const hasFolders = folders.length > 0;

  return (
    <aside className={`conversation-sidebar ${collapsed ? "is-collapsed" : ""} ${isMobile ? "is-mobile" : ""}`}>
      <div className="conversation-sidebar-header">
        <button className="sidebar-toggle-button" type="button" onClick={onToggleCollapsed}>
          {collapsed ? ">" : "<"}
        </button>
        {!collapsed ? (
          <>
            <div className="conversation-sidebar-title">Conversations</div>
            <button className="sidebar-new-button" type="button" onClick={onStartConversation}>
              New Chat
            </button>
          </>
        ) : null}
      </div>

      {!collapsed ? (
        <>
          <div className="conversation-sidebar-body">
            {loading ? <div className="conversation-sidebar-note">Loading conversations...</div> : null}
            {!loading && error ? <div className="conversation-sidebar-note">{error}</div> : null}
            {!loading && !error && !hasConversations && !hasFolders ? (
              <div className="conversation-sidebar-note">No saved conversations yet.</div>
            ) : null}

            {unfiledConversations.length > 0 ? (
              <div className="conversation-section">
                {unfiledConversations.map((conversation) => (
                  <ConversationCard
                    key={conversation.id}
                    actionBusy={actionBusy}
                    activeConversationId={activeConversationId}
                    conversation={conversation}
                    onDeleteConversation={onDeleteConversation}
                    onExportConversation={onExportConversation}
                    onMoveConversation={onOpenMoveConversation}
                    onRenameConversation={onOpenConversationRename}
                    onSelectConversation={onSelectConversation}
                  />
                ))}
              </div>
            ) : null}

            <div className="conversation-folder-section">
              <div className="conversation-folder-section-title">Conversation Folders</div>
              {folders.length === 0 ? (
                <div className="conversation-sidebar-note">No folders yet.</div>
              ) : (
                folders.map((folder) => (
                  <div key={folder.id} className="conversation-folder-group">
                    <div className="conversation-folder-row">
                      <button
                        className="conversation-folder-name"
                        disabled={actionBusy}
                        type="button"
                        onClick={() => onOpenFolderRename(folder)}
                      >
                        <FolderIcon />
                        <span>{folder.name}</span>
                      </button>
                      <button
                        aria-label={`Delete folder ${folder.name}`}
                        className="conversation-icon-button is-danger"
                        disabled={actionBusy}
                        type="button"
                        onClick={() => onOpenDeleteFolder(folder)}
                      >
                        <TrashIcon />
                      </button>
                    </div>
                    <div className="conversation-folder-conversations">
                      {folder.conversations.length === 0 ? (
                        <div className="conversation-sidebar-note">No conversations in this folder.</div>
                      ) : (
                        folder.conversations.map((conversation) => (
                          <ConversationCard
                            key={conversation.id}
                            actionBusy={actionBusy}
                            activeConversationId={activeConversationId}
                            conversation={conversation}
                            onDeleteConversation={onDeleteConversation}
                            onExportConversation={onExportConversation}
                            onMoveConversation={onOpenMoveConversation}
                            onRenameConversation={onOpenConversationRename}
                            onSelectConversation={onSelectConversation}
                          />
                        ))
                      )}
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
          {unfiledConversations.length > 0 ? (
            <div className="conversation-sidebar-footer">
              <button
                className="conversation-delete-all-button"
                disabled={actionBusy}
                type="button"
                onClick={onDeleteAllConversations}
              >
                <span>Delete all unfiled conversations</span>
                <TrashIcon />
              </button>
            </div>
          ) : null}
        </>
      ) : null}
    </aside>
  );
}

type ConversationCardProps = {
  actionBusy: boolean;
  activeConversationId: string;
  conversation: ConversationSummary;
  onDeleteConversation: (conversationId: string) => void;
  onExportConversation: (conversationId: string) => void;
  onMoveConversation: (conversation: ConversationSummary) => void;
  onRenameConversation: (conversation: ConversationSummary) => void;
  onSelectConversation: (conversationId: string) => void;
};

function ConversationCard({
  actionBusy,
  activeConversationId,
  conversation,
  onDeleteConversation,
  onExportConversation,
  onMoveConversation,
  onRenameConversation,
  onSelectConversation,
}: ConversationCardProps) {
  return (
    <div
      className={`conversation-item ${conversation.id === activeConversationId ? "is-active" : ""}`}
      role="button"
      tabIndex={0}
      onClick={() => onSelectConversation(conversation.id)}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onSelectConversation(conversation.id);
        }
      }}
    >
      <button
        className="conversation-item-title-button"
        disabled={actionBusy}
        type="button"
        onClick={(event) => {
          event.stopPropagation();
          onRenameConversation(conversation);
        }}
      >
        <span className="conversation-item-title">{conversation.title}</span>
      </button>
      <div className="conversation-item-footer">
        <span className="conversation-item-date">{new Date(conversation.updatedAt).toLocaleDateString()}</span>
        <div className="conversation-item-actions">
          <button
            aria-label={`File ${conversation.title}`}
            className="conversation-icon-button"
            disabled={actionBusy}
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              onMoveConversation(conversation);
            }}
          >
            <FolderIcon />
          </button>
          <button
            aria-label={`Export ${conversation.title}`}
            className="conversation-icon-button"
            disabled={actionBusy}
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              onExportConversation(conversation.id);
            }}
          >
            <DownloadIcon />
          </button>
          <button
            aria-label={`Delete ${conversation.title}`}
            className="conversation-icon-button is-danger"
            disabled={actionBusy}
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              onDeleteConversation(conversation.id);
            }}
          >
            <TrashIcon />
          </button>
        </div>
      </div>
    </div>
  );
}

function FolderIcon() {
  return (
    <svg aria-hidden="true" className="conversation-icon" viewBox="0 0 24 24">
      <path
        d="M3 7.4c0-1 .8-1.8 1.8-1.8h4.1l1.8 2h8.5c1 0 1.8.8 1.8 1.8v7.8c0 1-.8 1.8-1.8 1.8H4.8c-1 0-1.8-.8-1.8-1.8V7.4Z"
        fill="currentColor"
      />
    </svg>
  );
}

function DownloadIcon() {
  return (
    <svg aria-hidden="true" className="conversation-icon" viewBox="0 0 24 24">
      <path
        d="M12 4v9m0 0 3.4-3.4M12 13 8.6 9.6M5 15.5v2.2c0 .7.6 1.3 1.3 1.3h11.4c.7 0 1.3-.6 1.3-1.3v-2.2"
        fill="none"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.8"
      />
    </svg>
  );
}

function TrashIcon() {
  return (
    <svg aria-hidden="true" className="conversation-icon" viewBox="0 0 24 24">
      <path
        d="M4.5 7h15M9.2 3.8h5.6M9 10.2v6.3m6-6.3v6.3M7.8 20h8.4c.7 0 1.3-.6 1.3-1.3L18 7H6l.5 11.7c0 .7.6 1.3 1.3 1.3Z"
        fill="none"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.8"
      />
    </svg>
  );
}
