import type { CSSProperties } from "react";
import { useEffect, useState } from "react";
import closedFolderIcon from "../../assets/folder-closed.svg";
import openFolderIcon from "../../assets/folder-open.svg";
import conversationFileIcon from "../../assets/conversation-file.svg";
import downloadIcon from "../../assets/download.svg";
import settingsGearIcon from "../../assets/settings-gear.svg";
import sidebarArrowLeftIcon from "../../assets/sidebar-arrow-left.svg";
import sidebarArrowRightIcon from "../../assets/sidebar-arrow-right.svg";
import trashIcon from "../../assets/trash.svg";

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
  onOpenSettings: () => void;
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
  onOpenSettings,
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
        {collapsed ? (
          <button className="sidebar-toggle-button" type="button" onClick={onToggleCollapsed}>
            <SvgMaskIcon assetUrl={sidebarArrowRightIcon} className="sidebar-arrow-icon" />
          </button>
        ) : (
          <>
            <div className="conversation-sidebar-title">Conversations</div>
            <button className="sidebar-new-button" type="button" onClick={onStartConversation}>
              New Chat
            </button>
            <button className="sidebar-toggle-button" type="button" onClick={onToggleCollapsed}>
              <SvgMaskIcon assetUrl={sidebarArrowLeftIcon} className="sidebar-arrow-icon" />
            </button>
          </>
        )}
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
                        <SvgMaskIcon assetUrl={openFolderIds[folder.id] ? openFolderIcon : closedFolderIcon} />
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
                        <SvgMaskIcon assetUrl={trashIcon} />
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
          <div className="conversation-sidebar-footer">
            <div className="conversation-sidebar-footer-actions">
              <button
                aria-label="Open personal settings"
                className="conversation-settings-button"
                disabled={actionBusy}
                type="button"
                onClick={onOpenSettings}
              >
                <img alt="" aria-hidden="true" className="conversation-settings-icon-image" src={settingsGearIcon} />
              </button>
              {unfiledConversations.length > 0 ? (
                <button
                  className="conversation-delete-all-button"
                  disabled={actionBusy}
                  type="button"
                  onClick={onDeleteAllConversations}
                >
                  <span>Delete all unfiled conversations</span>
                  <SvgMaskIcon assetUrl={trashIcon} />
                </button>
              ) : null}
            </div>
          </div>
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
            <SvgMaskIcon assetUrl={conversationFileIcon} />
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
            <SvgMaskIcon assetUrl={downloadIcon} />
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
            <SvgMaskIcon assetUrl={trashIcon} />
          </button>
        </div>
      </div>
    </div>
  );
}

function SvgMaskIcon({ assetUrl, className }: { assetUrl: string; className?: string }) {
  const style = {
    "--icon-mask-url": `url("${assetUrl}")`,
  } as CSSProperties;

  return (
    <span
      aria-hidden="true"
      className={className ? `conversation-icon-mask ${className}` : "conversation-icon-mask conversation-icon"}
      style={style}
    />
  );
}
