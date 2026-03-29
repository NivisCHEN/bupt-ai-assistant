import * as Icons from "./Icons";
import { BUPTLogo } from "./Icons";

export default function Sidebar({
  sessions, activeSessionId, searchQuery, messages, t,
  sidebarOpen, rightPanel,
  onCreateSession, onSelectSession, onDeleteSession,
  onSearchChange, onSetRightPanel, onLogout, onCloseSidebar,
}) {
  return (
    <div className={`sidebar ${sidebarOpen ? "open" : ""}`}>
      <div className="sidebar-header">
        <div className="sidebar-brand">
          <BUPTLogo size={32} />
          <h2>{t.appName}</h2>
        </div>
        <button className="new-chat-btn" onClick={onCreateSession}>
          <Icons.Plus /> {t.newChat}
        </button>
      </div>

      <div className="sidebar-search" style={{ position: "relative" }}>
        <span className="sidebar-search-icon"><Icons.Search /></span>
        <input placeholder={t.searchChats} value={searchQuery}
          onChange={(e) => onSearchChange(e.target.value)} />
      </div>

      <div className="chat-list">
        {Object.entries(sessions).map(([group, items]) => {
          if (items.length === 0) return null;
          return (
            <div key={group}>
              <div className="chat-group-label">{t[group]}</div>
              {items.map((s) => (
                <div key={s.id}
                  className={`chat-item ${s.id === activeSessionId ? "active" : ""}`}
                  onClick={() => { onSelectSession(s.id); onCloseSidebar(); }}
                  onContextMenu={(e) => {
                    e.preventDefault();
                    if (window.confirm(`${t.delete}?`)) onDeleteSession(s.id);
                  }}
                >
                  {s.pinned && <span className="chat-item-pin">📌</span>}
                  <div className="chat-item-content">
                    <div className="chat-item-title">{s.title || t.newChat}</div>
                    <div className="chat-item-preview">
                      {(messages[s.id] || []).slice(-1)[0]?.content?.slice(0, 40) || ""}
                    </div>
                    {s.tags.length > 0 && (
                      <div className="chat-item-tags">
                        {s.tags.map((tag, i) => <span key={i} className="tag-pill">{tag}</span>)}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          );
        })}
        {Object.values(sessions).flat().length === 0 && (
          <div style={{ textAlign: "center", padding: 40, color: "var(--text-tertiary)" }}>
            <p>{t.noChats}</p>
            <p style={{ fontSize: 12, marginTop: 4 }}>{t.startChat}</p>
          </div>
        )}
      </div>

      <div className="sidebar-footer">
        <button className="sidebar-footer-btn" onClick={() => onSetRightPanel(rightPanel === "profile" ? null : "profile")}
          style={rightPanel === "profile" ? { color: "var(--bupt-blue-light)", background: "var(--accent-light)" } : {}}>
          <Icons.User /> {t.personality}
        </button>
        <button className="sidebar-footer-btn" onClick={() => onSetRightPanel(rightPanel === "memory" ? null : "memory")}
          style={rightPanel === "memory" ? { color: "var(--bupt-blue-light)", background: "var(--accent-light)" } : {}}>
          <Icons.Brain /> {t.memory}
        </button>
        <button className="sidebar-footer-btn" onClick={() => onSetRightPanel(rightPanel === "settings" ? null : "settings")}
          style={rightPanel === "settings" ? { color: "var(--bupt-blue-light)", background: "var(--accent-light)" } : {}}>
          <Icons.Settings />
        </button>
        <button className="sidebar-footer-btn" onClick={onLogout} title={t.logout}>
          <Icons.Logout />
        </button>
      </div>
    </div>
  );
}
