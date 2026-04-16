export type ConversationSummary = {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
};

type ConversationSidebarProps = {
  collapsed: boolean;
  isMobile: boolean;
  conversations: ConversationSummary[];
  error: string | null;
  activeConversationId: string;
  loading: boolean;
  actionBusy: boolean;
  onSelectConversation: (conversationId: string) => void;
  onStartConversation: () => void;
  onToggleCollapsed: () => void;
  onDeleteConversation: (conversationId: string) => void;
  onExportConversation: (conversationId: string) => void;
};

export function ConversationSidebar({
  collapsed,
  isMobile,
  conversations,
  error,
  activeConversationId,
  loading,
  actionBusy,
  onSelectConversation,
  onStartConversation,
  onToggleCollapsed,
  onDeleteConversation,
  onExportConversation,
}: ConversationSidebarProps) {
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
        <div className="conversation-sidebar-body">
          {loading ? <div className="conversation-sidebar-note">Loading conversations...</div> : null}
          {!loading && error ? <div className="conversation-sidebar-note">{error}</div> : null}
          {!loading && !error && conversations.length === 0 ? (
            <div className="conversation-sidebar-note">No saved conversations yet.</div>
          ) : null}
          {conversations.map((conversation) => (
            <div
              key={conversation.id}
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
              <span className="conversation-item-title">{conversation.title}</span>
              <div className="conversation-item-footer">
                <span className="conversation-item-date">
                  {new Date(conversation.updatedAt).toLocaleDateString()}
                </span>
                <div className="conversation-item-actions">
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
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : null}
    </aside>
  );
}
