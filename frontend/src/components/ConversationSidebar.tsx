import { useEffect, useState } from "react";

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
  const [openFolderIds, setOpenFolderIds] = useState<Record<string, boolean>>({});

  useEffect(() => {
    setOpenFolderIds((current) => {
      const next: Record<string, boolean> = {};
      for (const folder of folders) {
        const containsActiveConversation = folder.conversations.some((conversation) => conversation.id === activeConversationId);
        next[folder.id] = current[folder.id] ?? containsActiveConversation;
      }
      return next;
    });
  }, [activeConversationId, folders]);

  function toggleFolder(folderId: string) {
    setOpenFolderIds((current) => ({
      ...current,
      [folderId]: !current[folderId],
    }));
  }

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
                        aria-label={`${openFolderIds[folder.id] ? "Close" : "Open"} folder ${folder.name}`}
                        className="conversation-folder-toggle"
                        disabled={actionBusy}
                        type="button"
                        onClick={() => toggleFolder(folder.id)}
                      >
                        {openFolderIds[folder.id] ? <OpenFolderIcon /> : <ClosedFolderIcon />}
                      </button>
                      <button
                        className="conversation-folder-name"
                        disabled={actionBusy}
                        type="button"
                        onClick={() => onOpenFolderRename(folder)}
                      >
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
                    {openFolderIds[folder.id] ? (
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
                              nested
                              onDeleteConversation={onDeleteConversation}
                              onExportConversation={onExportConversation}
                              onMoveConversation={onOpenMoveConversation}
                              onRenameConversation={onOpenConversationRename}
                              onSelectConversation={onSelectConversation}
                            />
                          ))
                        )}
                      </div>
                    ) : null}
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
  nested?: boolean;
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
  nested = false,
  onDeleteConversation,
  onExportConversation,
  onMoveConversation,
  onRenameConversation,
  onSelectConversation,
}: ConversationCardProps) {
  return (
    <div
      className={`conversation-item ${conversation.id === activeConversationId ? "is-active" : ""} ${nested ? "is-nested" : ""}`}
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
            <FileConversationIcon />
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

function FileConversationIcon() {
  return (
    <svg aria-hidden="true" className="conversation-icon" viewBox="0 0 24 24">
      <path
        d="M4.3 9.8c0-.8.7-1.5 1.5-1.5h4.1l1.4 1.4h6.9c.8 0 1.5.7 1.5 1.5v6c0 .8-.7 1.5-1.5 1.5H5.8c-.8 0-1.5-.7-1.5-1.5V9.8Z"
        fill="none"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.8"
      />
      <path
        d="M12 3.1v7m0 0 2.7-2.7M12 10.1 9.3 7.4"
        fill="none"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2.2"
      />
    </svg>
  );
}

function OpenFolderIcon() {
  return (
    <svg aria-hidden="true" className="conversation-icon" viewBox="0 0 24 24">
      <path
        d="M4.3 8.2c0-.8.7-1.4 1.4-1.4H10l1.5 1.4h6.6c.9 0 1.5.7 1.4 1.5"
        fill="none"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.5"
      />
      <path
        d="M6.7 10.8h12.1c.9 0 1.5.8 1.3 1.6l-1 4.1c-.2.7-.8 1.2-1.5 1.2H5.8c-.9 0-1.5-.9-1.1-1.8l1.1-3.1c.2-.6.8-1 1.4-1Z"
        fill="none"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.5"
      />
    </svg>
  );
}

function ClosedFolderIcon() {
  return (
    <svg aria-hidden="true" className="conversation-icon" viewBox="0 0 24 24">
      <path
        d="M4.4 7.7c0-.8.7-1.5 1.5-1.5h4.1l1.5 1.4h6.7c.8 0 1.5.7 1.5 1.5v7.2c0 .8-.7 1.5-1.5 1.5H5.9c-.8 0-1.5-.7-1.5-1.5V7.7Z"
        fill="none"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.5"
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
