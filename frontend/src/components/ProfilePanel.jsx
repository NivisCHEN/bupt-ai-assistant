import { useState } from "react";
import * as Icons from "./Icons";

export default function ProfilePanel({ onClose, t, profile, onUpdateProfile, onRefresh, onExport, memories, onAddManualMemory, onDeleteMemory, onFeedbackMemory }) {
  const [addingTag, setAddingTag] = useState(null);
  const [newTagText, setNewTagText] = useState("");
  const [newMemoryText, setNewMemoryText] = useState("");

  const hasProfile = profile && (
    (profile.preferences && Object.keys(profile.preferences).length > 0) ||
    (profile.personality_tags && profile.personality_tags.length > 0) ||
    (profile.frequent_topics && profile.frequent_topics.length > 0) ||
    profile.summary
  );

  const prefTags = profile?.preferences ? Object.entries(profile.preferences).map(([k, v]) => ({ key: k, value: v, id: k })) : [];
  const personalityTags = profile?.personality_tags || [];
  const frequentTopics = profile?.frequent_topics || [];
  const summary = profile?.summary || "";

  const handleAddTag = (type) => {
    if (!newTagText.trim()) return;
    if (type === "pref") {
      const updated = { ...profile, preferences: { ...(profile?.preferences || {}), [newTagText.trim()]: true } };
      onUpdateProfile(updated);
    } else if (type === "personality") {
      const updated = { ...profile, personality_tags: [...(profile?.personality_tags || []), { label: newTagText.trim(), important: false }] };
      onUpdateProfile(updated);
    }
    setNewTagText("");
    setAddingTag(null);
  };

  const handleRemovePref = (key) => {
    const newPrefs = { ...(profile?.preferences || {}) };
    delete newPrefs[key];
    onUpdateProfile({ ...profile, preferences: newPrefs });
  };

  const handleRemovePersonalityTag = (idx) => {
    const newTags = [...(profile?.personality_tags || [])];
    newTags.splice(idx, 1);
    onUpdateProfile({ ...profile, personality_tags: newTags });
  };

  const handleToggleImportant = (idx) => {
    const newTags = [...(profile?.personality_tags || [])];
    newTags[idx] = { ...newTags[idx], important: !newTags[idx].important };
    onUpdateProfile({ ...profile, personality_tags: newTags });
  };

  const maxTopicCount = Math.max(...frequentTopics.map((ft) => ft.count || 1), 1);

  return (
    <div className="right-panel">
      <div className="panel-header">
        <h3>{t.personality}</h3>
        <button className="panel-close" onClick={onClose}><Icons.X /></button>
      </div>
      <div className="panel-body">
        {/* Header card */}
        <div className="profile-card">
          <div className="profile-card-header">
            <div className="profile-icon"><Icons.User /></div>
            <div>
              <h4>{t.personalityTitle}</h4>
              <div className="profile-sub">{t.personalityDesc}</div>
            </div>
          </div>
          <div className="profile-actions-bar">
            <button className="profile-action-btn primary" onClick={onRefresh}>
              <Icons.Retry /> {t.refreshProfile}
            </button>
            <button className="profile-action-btn" onClick={onExport}>
              <Icons.Download /> {t.exportProfile}
            </button>
          </div>
        </div>

        {!hasProfile ? (
          <div className="empty-profile">
            <div className="empty-profile-icon"><Icons.Brain /></div>
            <p style={{ fontWeight: 500, marginBottom: 4 }}>{t.noProfileYet}</p>
            <p style={{ fontSize: 12, lineHeight: 1.6 }}>{t.personalityDesc}</p>
          </div>
        ) : (
          <>
            {/* Profile Summary */}
            {summary && (
              <div className="profile-section">
                <div className="profile-section-title">{t.profileSummary}</div>
                <div className="profile-summary-text">{summary}</div>
              </div>
            )}

            {/* Preference Tags */}
            <div className="profile-section">
              <div className="profile-section-title">
                {t.prefTags}
                <span className="count-badge">{prefTags.length}</span>
              </div>
              <div className="profile-tags">
                {prefTags.map((tag) => (
                  <span key={tag.key} className="profile-tag">
                    {tag.key}{typeof tag.value === "string" ? `: ${tag.value}` : ""}
                    <span className="tag-remove" onClick={() => handleRemovePref(tag.key)}>✕</span>
                  </span>
                ))}
                {addingTag === "pref" ? (
                  <span className="profile-tag" style={{ padding: "3px 4px" }}>
                    <input
                      autoFocus
                      value={newTagText}
                      onChange={(e) => setNewTagText(e.target.value)}
                      onKeyDown={(e) => { if (e.key === "Enter") handleAddTag("pref"); if (e.key === "Escape") { setAddingTag(null); setNewTagText(""); } }}
                      onBlur={() => { if (newTagText.trim()) handleAddTag("pref"); else { setAddingTag(null); setNewTagText(""); } }}
                      style={{ border: "none", outline: "none", background: "transparent", width: 80, fontSize: 12, color: "var(--text-primary)", fontFamily: "inherit" }}
                      placeholder={t.addCustomTag}
                    />
                  </span>
                ) : (
                  <button className="profile-tag-add" onClick={() => setAddingTag("pref")}>+ {t.addTag}</button>
                )}
              </div>
            </div>

            {/* Personality Tags */}
            <div className="profile-section">
              <div className="profile-section-title">
                {t.personalityTags}
                <span className="count-badge">{personalityTags.length}</span>
              </div>
              <div className="profile-tags">
                {personalityTags.map((tag, idx) => (
                  <span key={idx} className={`profile-tag ${tag.important ? "important" : ""}`}
                    onClick={() => handleToggleImportant(idx)} title={t.markImportant}>
                    {tag.important && <span className="tag-star">★</span>}
                    {tag.label || tag}
                    <span className="tag-remove" onClick={(e) => { e.stopPropagation(); handleRemovePersonalityTag(idx); }}>✕</span>
                  </span>
                ))}
                {addingTag === "personality" ? (
                  <span className="profile-tag" style={{ padding: "3px 4px" }}>
                    <input
                      autoFocus
                      value={newTagText}
                      onChange={(e) => setNewTagText(e.target.value)}
                      onKeyDown={(e) => { if (e.key === "Enter") handleAddTag("personality"); if (e.key === "Escape") { setAddingTag(null); setNewTagText(""); } }}
                      onBlur={() => { if (newTagText.trim()) handleAddTag("personality"); else { setAddingTag(null); setNewTagText(""); } }}
                      style={{ border: "none", outline: "none", background: "transparent", width: 80, fontSize: 12, color: "var(--text-primary)", fontFamily: "inherit" }}
                      placeholder={t.addCustomTag}
                    />
                  </span>
                ) : (
                  <button className="profile-tag-add" onClick={() => setAddingTag("personality")}>+ {t.addTag}</button>
                )}
              </div>
            </div>

            {/* Frequent Topics */}
            {frequentTopics.length > 0 && (
              <div className="profile-section">
                <div className="profile-section-title">
                  {t.frequentTopics}
                  <span className="count-badge">{frequentTopics.length}</span>
                </div>
                {frequentTopics.map((topic, idx) => (
                  <div key={idx} className="topic-item">
                    <span className="topic-label">{topic.name || topic}</span>
                    <div className="topic-bar-container">
                      <div className="topic-bar" style={{ width: `${((topic.count || 1) / maxTopicCount) * 100}%` }} />
                    </div>
                    <span className="topic-count">{topic.count || ""}</span>
                  </div>
                ))}
              </div>
            )}
          </>
        )}

        {/* Memory entries with source tracing + feedback */}
        <div className="profile-section">
          <div className="profile-section-title" style={{ marginTop: 8 }}>
            {t.memory}
            <span className="count-badge">{memories.length}</span>
          </div>

          <div className="add-memory-row">
            <input
              value={newMemoryText}
              onChange={(e) => setNewMemoryText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && newMemoryText.trim()) {
                  onAddManualMemory(newMemoryText.trim());
                  setNewMemoryText("");
                }
              }}
              placeholder={t.addMemoryPlaceholder}
            />
            <button className="profile-action-btn" onClick={() => {
              if (newMemoryText.trim()) { onAddManualMemory(newMemoryText.trim()); setNewMemoryText(""); }
            }}>
              <Icons.Plus />
            </button>
          </div>

          {memories.length === 0 ? (
            <div style={{ textAlign: "center", padding: 20, color: "var(--text-tertiary)", fontSize: 12 }}>
              {t.memoryEmpty}
            </div>
          ) : (
            <div style={{ marginTop: 8 }}>
              {memories.map((m, i) => (
                <div key={m.id || i} className="memory-item">
                  <div className="memory-content">{m.content}</div>
                  <div className="memory-meta">
                    <span className={`importance-badge ${
                      (m.importance_score || 0) > 0.7 ? "importance-high" :
                      (m.importance_score || 0) > 0.4 ? "importance-mid" : "importance-low"
                    }`}>
                      {((m.importance_score || 0) * 100).toFixed(0)}%
                    </span>
                    {m.source_session && (
                      <span className="memory-origin-badge" title={t.memoryOrigin}>
                        {t.memoryOrigin}: {m.source_session}
                      </span>
                    )}
                    <div className="feedback-btns" style={{ marginLeft: "auto" }}>
                      <button
                        className={`feedback-btn ${m.feedback === "correct" ? "correct" : ""}`}
                        onClick={() => onFeedbackMemory(m.id, "correct")}
                      >
                        <Icons.Check /> {t.markCorrect}
                      </button>
                      <button
                        className={`feedback-btn ${m.feedback === "wrong" ? "wrong" : ""}`}
                        onClick={() => onFeedbackMemory(m.id, "wrong")}
                      >
                        ✕ {t.markWrong}
                      </button>
                      <button className="feedback-btn" onClick={() => onDeleteMemory(m.id)}>
                        <Icons.Trash />
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
