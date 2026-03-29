import { forwardRef } from "react";
import { BUPTLogo } from "./Icons";
import MessageBubble from "./MessageBubble";

const ChatArea = forwardRef(function ChatArea(
  { messages, t, onSendMessage, onQuote, onSaveMemory },
  ref
) {
  return (
    <div className="messages-container">
      {messages.length === 0 ? (
        <div className="welcome-state">
          <BUPTLogo size={72} />
          <div className="welcome-text">{t.welcomeMsg}</div>
          <div className="msg-suggestions" style={{ marginTop: 20 }}>
            {["图书馆几点开门？", "如何申请转专业？", "校园网怎么连？"].map((q, i) => (
              <button key={i} className="suggestion-chip" onClick={() => onSendMessage(q)}>{q}</button>
            ))}
          </div>
        </div>
      ) : (
        messages.map((msg) => (
          <MessageBubble
            key={msg.id} msg={msg} isUser={msg.role === "user"} t={t}
            onRetry={() => {
              const prevUser = messages.slice().reverse().find((m) => m.role === "user");
              if (prevUser) onSendMessage(prevUser.content);
            }}
            onSuggestionClick={onSendMessage}
            onQuote={(text) => onQuote(text.slice(0, 100))}
            onSaveMemory={onSaveMemory}
          />
        ))
      )}
      <div ref={ref} />
    </div>
  );
});

export default ChatArea;
