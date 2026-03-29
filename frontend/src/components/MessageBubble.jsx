import { useState } from "react";
import * as Icons from "./Icons";
import { renderMarkdown } from "../utils/markdown";
import { formatTime } from "../utils/helpers";

export default function MessageBubble({ msg, isUser, t, onRetry, onSuggestionClick, onQuote, onSaveMemory }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(msg.content).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  const statusLabel = msg.status === "sending" ? t.sending : msg.status === "error" ? t.failed : "";
  const statusClass = msg.status === "sending" ? "sending" : msg.status === "error" ? "error" : "done";

  return (
    <div className={`message-group ${isUser ? "user" : ""}`}>
      <div className={`msg-avatar ${isUser ? "user-av" : "ai"}`}>
        {isUser ? <Icons.User /> : "邮"}
      </div>
      <div className="msg-content">
        {msg.quotedText && (
          <div className="quote-preview">
            <Icons.Quote />
            <span className="q-text">{msg.quotedText}</span>
          </div>
        )}
        <div className={`msg-bubble ${isUser ? "user-bubble" : "ai-bubble"}`}>
          {msg.status === "sending" && !msg.content ? (
            <div className="typing-dots"><span /><span /><span /></div>
          ) : (
            <div dangerouslySetInnerHTML={{ __html: renderMarkdown(msg.content) }} />
          )}
        </div>

        {!isUser && msg.sources && msg.sources.length > 0 && (
          <div className="msg-sources">
            <div style={{ fontWeight: 600, marginBottom: 4, fontSize: 11, color: "var(--text-tertiary)" }}>
              {t.sources}
            </div>
            {msg.sources.map((s, i) => (
              <div key={i} className="msg-source-item">
                <span className="msg-source-idx">[{i + 1}]</span>
                <span className="msg-source-title">{s.title}</span>
                {s.url && <a href={s.url} target="_blank" rel="noopener noreferrer" style={{ fontSize: 11, color: "var(--text-link)" }}>↗</a>}
              </div>
            ))}
          </div>
        )}

        {!isUser && msg.suggestions && msg.suggestions.length > 0 && (
          <div className="msg-suggestions">
            {msg.suggestions.map((s, i) => (
              <button key={i} className="suggestion-chip" onClick={() => onSuggestionClick(s)}>{s}</button>
            ))}
          </div>
        )}

        {!isUser && msg.confidence != null && msg.confidence > 0 && (
          <div className="msg-confidence">
            <span>{t.confidence}: {(msg.confidence * 100).toFixed(0)}%</span>
            <div className="confidence-bar">
              <div
                className="confidence-fill"
                style={{
                  width: `${msg.confidence * 100}%`,
                  background: msg.confidence > 0.7 ? "#4CAF50" : msg.confidence > 0.4 ? "#FF9800" : "#F44336",
                }}
              />
            </div>
          </div>
        )}

        <div className="msg-meta">
          <span className="msg-time">{formatTime(msg.timestamp)}</span>
          {statusLabel && <span className={`msg-status ${statusClass}`}>{statusLabel}</span>}
          <div className="msg-actions">
            <button className="msg-action-btn" onClick={handleCopy} title={t.copy}>
              {copied ? <><Icons.Check /> {t.copied}</> : <Icons.Copy />}
            </button>
            {!isUser && (
              <>
                <button className="msg-action-btn" onClick={() => onQuote(msg.content)} title={t.quote}>
                  <Icons.Quote />
                </button>
                <button className="msg-action-btn" onClick={() => onSaveMemory(msg.content)} title={t.saveMemory}>
                  <Icons.Brain />
                </button>
              </>
            )}
            {msg.status === "error" && (
              <button className="msg-action-btn" onClick={onRetry} title={t.retry}>
                <Icons.Retry /> {t.retry}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
