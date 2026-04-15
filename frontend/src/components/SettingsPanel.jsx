import * as Icons from "./Icons";

export default function SettingsPanel({ onClose, t, settings, onUpdate }) {
  return (
    <div className="right-panel">
      <div className="panel-header">
        <h3>{t.settings}</h3>
        <button className="panel-close" onClick={onClose}><Icons.X /></button>
      </div>
      <div className="panel-body">
        <div className="settings-section">
          <div className="settings-label">{t.theme}</div>
          <div className="settings-row">
            {["light", "dark", "system"].map((v) => (
              <button key={v} className={`settings-chip ${settings.theme === v ? "active" : ""}`}
                onClick={() => onUpdate({ theme: v })}>
                {v === "light" ? t.light : v === "dark" ? t.dark : t.system}
              </button>
            ))}
          </div>
        </div>

        <div className="settings-section">
          <div className="settings-label">{t.language}</div>
          <div className="settings-row">
            <button className={`settings-chip ${settings.lang === "zh" ? "active" : ""}`}
              onClick={() => onUpdate({ lang: "zh" })}>中文</button>
            <button className={`settings-chip ${settings.lang === "en" ? "active" : ""}`}
              onClick={() => onUpdate({ lang: "en" })}>English</button>
          </div>
        </div>

        <div className="settings-section">
          <div className="settings-label">{t.fontSize}</div>
          <div className="settings-row">
            {["small", "medium", "large"].map((v) => (
              <button key={v} className={`settings-chip ${settings.fontSize === v ? "active" : ""}`}
                onClick={() => onUpdate({ fontSize: v })}>
                {t[v]}
              </button>
            ))}
          </div>
        </div>

        <div className="settings-section">
          <div className="settings-label">{t.density}</div>
          <div className="settings-row">
            {["compact", "default", "relaxed"].map((v) => (
              <button key={v} className={`settings-chip ${settings.density === v ? "active" : ""}`}
                onClick={() => onUpdate({ density: v })}>
                {t[v]}
              </button>
            ))}
          </div>
        </div>

        <div className="settings-section">
          <div className="toggle-row">
            <span className="toggle-label">{t.longTermMemory}</span>
            <button className={`toggle-switch ${settings.memoryEnabled ? "on" : ""}`}
              onClick={() => onUpdate({ memoryEnabled: !settings.memoryEnabled })} />
          </div>
          <div style={{ fontSize: 12, color: "var(--text-tertiary)", marginTop: 4 }}>
            {settings.memoryEnabled ? t.memoryEnabled : t.memoryDisabled}
          </div>
        </div>

        <div className="settings-section">
          <div className="settings-label">{t.apiConfig}</div>
          <input className="login-input" style={{ marginBottom: 0 }}
            value={settings.baseUrl} placeholder={t.baseUrl}
            onChange={(e) => onUpdate({ baseUrl: e.target.value })} />
        </div>

        <div className="settings-section">
          <div className="privacy-note">{t.privacyNote}</div>
        </div>

        <div className="settings-section">
          <button className="danger-btn" onClick={() => {
            localStorage.clear();
            window.location.reload();
          }}>{t.clearCache}</button>
        </div>

        <div className="settings-section">
          <div style={{ fontSize: 12, color: "var(--text-tertiary)" }}>
            {t.version}: 0.1.0 · {t.appName} · BUPT
          </div>
        </div>
      </div>
    </div>
  );
}
