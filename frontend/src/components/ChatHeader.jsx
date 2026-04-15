import * as Icons from "./Icons";
import { BUPTLogo } from "./Icons";

export default function ChatHeader({
  activeSession, activeSessionId, t, settings, rightPanel,
  onOpenSidebar, onPinSession, onExportSession, onSetRightPanel, onToggleTheme,
}) {
  return (
    <div className="chat-header">
      <button className="mobile-menu-btn" onClick={onOpenSidebar}>
        <Icons.Menu />
      </button>
      <BUPTLogo size={28} />
      <div className="chat-title-area">
        <div className="chat-title">{activeSession?.title || t.appName}</div>
        <div className="chat-status">{t.appSubtitle}</div>
      </div>
      <div style={{ display: "flex", gap: 4 }}>
        {activeSessionId && (
          <>
            <button className="input-icon-btn" onClick={() => onPinSession(activeSessionId)} title={t.pin}>
              <Icons.Pin />
            </button>
            <button className="input-icon-btn" onClick={() => onExportSession(activeSessionId, "json")} title={t.export}>
              <Icons.Download />
            </button>
          </>
        )}
        <button className="input-icon-btn"
          onClick={() => onSetRightPanel(rightPanel === "profile" ? null : "profile")}
          title={t.personality}
          style={rightPanel === "profile" ? { color: "var(--bupt-blue-light)", background: "var(--accent-light)" } : {}}
        >
          <Icons.User />
        </button>
        <button className="input-icon-btn" onClick={onToggleTheme} title={t.theme}>
          {settings.theme === "dark" ? <Icons.Sun /> : <Icons.Moon />}
        </button>
      </div>
    </div>
  );
}
