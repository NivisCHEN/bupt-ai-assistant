import { forwardRef } from "react";
import * as Icons from "./Icons";

const MAX_CHARS = 2000;

const InputArea = forwardRef(function InputArea(
  { inputText, isGenerating, quotedText, t, onInputChange, onSend, onStop, onClearQuote },
  ref
) {
  return (
    <div className="input-area">
      <div className="input-wrapper">
        {quotedText && (
          <div className="quote-preview" style={{ marginBottom: 8, borderRadius: "var(--radius-sm)" }}>
            <Icons.Quote />
            <span className="q-text">{quotedText}</span>
            <button className="msg-action-btn" onClick={onClearQuote}><Icons.X /></button>
          </div>
        )}
        <div className="input-box">
          <textarea
            ref={ref}
            className="input-textarea"
            rows={1}
            value={inputText}
            onChange={(e) => {
              if (e.target.value.length <= MAX_CHARS) onInputChange(e.target.value);
            }}
            placeholder={t.typeMessage}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                onSend(inputText);
              }
            }}
            disabled={isGenerating}
          />
          <div className="input-actions">
            <button className="input-icon-btn" title={t.uploadFile}>
              <Icons.File />
            </button>
            {isGenerating ? (
              <button className="send-btn stop-btn" onClick={onStop}>
                <Icons.Stop /> {t.stop}
              </button>
            ) : (
              <button className="send-btn" onClick={() => onSend(inputText)}
                disabled={!inputText.trim()}>
                <Icons.Send /> {t.send}
              </button>
            )}
          </div>
        </div>
        <div className={`char-counter ${inputText.length > MAX_CHARS * 0.9 ? "warn" : ""}`}>
          {inputText.length} / {MAX_CHARS} {t.charCount}
        </div>
      </div>
    </div>
  );
});

export default InputArea;
