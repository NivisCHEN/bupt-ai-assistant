import { useState } from "react";
import * as Icons from "./Icons";

export default function MemoryPanel({ onClose, t, memories, onSearch, onDelete }) {
  const [query, setQuery] = useState("");

  return (
    <div className="right-panel">
      <div className="panel-header">
        <h3>{t.memory}</h3>
        <button className="panel-close" onClick={onClose}><Icons.X /></button>
      </div>
      <div className="panel-body">
        <div style={{ position: "relative", marginBottom: 12 }}>
          <input className="login-input" style={{ marginBottom: 0, paddingLeft: 32 }}
            placeholder={t.memorySearch} value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && onSearch(query)} />
          <span style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)", color: "var(--text-tertiary)" }}>
            <Icons.Search />
          </span>
        </div>

        {memories.length === 0 ? (
          <div style={{ textAlign: "center", padding: 40, color: "var(--text-tertiary)" }}>
            <Icons.Brain />
            <p style={{ marginTop: 8 }}>{t.memoryEmpty}</p>
          </div>
        ) : (
          memories.map((m, i) => (
            <div key={m.id || i} className="memory-item">
              <div className="memory-content">{m.content}</div>
              <div className="memory-meta">
                <span className={`importance-badge ${
                  m.importance_score > 0.7 ? "importance-high" :
                  m.importance_score > 0.4 ? "importance-mid" : "importance-low"
                }`}>
                  {t.importance}: {(m.importance_score * 100).toFixed(0)}%
                </span>
                <span>{m.type}</span>
                {m.timestamp && <span>{new Date(m.timestamp).toLocaleDateString()}</span>}
                <button className="msg-action-btn" onClick={() => onDelete(m.id)} style={{ marginLeft: "auto" }}>
                  <Icons.Trash />
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
