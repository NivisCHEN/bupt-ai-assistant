import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { debounce } from "lodash-es";

import { TRANSLATIONS } from "./i18n/translations";
import { createApiClient } from "./api/client";
import { generateId, formatTime, formatDate } from "./utils/helpers";

import Sidebar from "./components/Sidebar";
import ChatHeader from "./components/ChatHeader";
import ChatArea from "./components/ChatArea";
import InputArea from "./components/InputArea";
import SettingsPanel from "./components/SettingsPanel";
import MemoryPanel from "./components/MemoryPanel";
import ProfilePanel from "./components/ProfilePanel";

export default function App() {
  // ── State ───────────────────────────────────────────────────
  const [user, setUser] = useState({ userId: "default_user", name: "用户" });
  const [settings, setSettings] = useState({
    theme: "light", lang: "zh", fontSize: "medium", density: "default",
    memoryEnabled: true, baseUrl: "http://localhost:8000",
  });
  const [sessions, setSessions] = useState([]);
  const [activeSessionId, setActiveSessionId] = useState(null);
  const [messages, setMessages] = useState({});
  const [inputText, setInputText] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [rightPanel, setRightPanel] = useState(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [memories, setMemories] = useState([]);
  const [quotedText, setQuotedText] = useState(null);
  const [userProfile, setUserProfile] = useState({
    preferences: {},
    personality_tags: [],
    frequent_topics: [],
    summary: "",
  });

  const abortRef = useRef(null);
  const messagesEndRef = useRef(null);
  const textareaRef = useRef(null);
  const pendingMessageRef = useRef(null);

  const t = TRANSLATIONS[settings.lang] || TRANSLATIONS.zh;

  // ── Load from localStorage ──────────────────────────────────
  useEffect(() => {
    try {
      const saved = localStorage.getItem("xiaoqyou_state");
      if (saved) {
        const s = JSON.parse(saved);
        if (s.user) setUser(s.user);
        if (s.settings) setSettings((p) => ({ ...p, ...s.settings }));
        if (s.sessions) setSessions(s.sessions);
        if (s.activeSessionId) setActiveSessionId(s.activeSessionId);
        if (s.messages) setMessages(s.messages);
        if (s.userProfile) setUserProfile(s.userProfile);
      }
    } catch (e) { /* ignore */ }
    // Auto-create first session for fresh users
    if (!localStorage.getItem("xiaoqyou_state")) {
      const id = generateId();
      const session = {
        id, title: "", createdAt: Date.now(), updatedAt: Date.now(),
        pinned: false, archived: false, tags: [],
      };
      setSessions([session]);
      setMessages({ [id]: [] });
      setActiveSessionId(id);
    }
  }, []);

  // ── Save to localStorage ────────────────────────────────────
  useEffect(() => {
    if (!user) return;
    const save = debounce(() => {
      try {
        // Trim to most recent 50 sessions to avoid exceeding localStorage quota
        const trimmedSessions = sessions.slice(0, 50);
        const trimmedMessages = {};
        for (const s of trimmedSessions) {
          if (messages[s.id]) trimmedMessages[s.id] = messages[s.id];
        }
        localStorage.setItem("xiaoqyou_state", JSON.stringify({
          user, settings, sessions: trimmedSessions, activeSessionId,
          messages: trimmedMessages, userProfile,
        }));
      } catch (e) {
        // Quota exceeded — clear old data and retry with minimal state
        try {
          localStorage.setItem("xiaoqyou_state", JSON.stringify({
            user, settings, sessions: sessions.slice(0, 10),
            activeSessionId, messages: {}, userProfile,
          }));
        } catch { /* give up */ }
      }
    }, 500);
    save();
    return () => save.cancel();
  }, [user, settings, sessions, activeSessionId, messages, userProfile]);

  // ── Theme ───────────────────────────────────────────────────
  useEffect(() => {
    const root = document.documentElement;
    let theme = settings.theme;
    if (theme === "system") {
      theme = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    }
    root.setAttribute("data-theme", theme);
    root.setAttribute("data-density", settings.density);
    root.setAttribute("data-fontsize", settings.fontSize);
  }, [settings.theme, settings.density, settings.fontSize]);

  // ── Scroll to bottom ───────────────────────────────────────
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, activeSessionId]);

  // ── Auto-resize textarea ───────────────────────────────────
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 120) + "px";
    }
  }, [inputText]);

  // ── Active session ─────────────────────────────────────────
  const activeSession = sessions.find((s) => s.id === activeSessionId);
  const activeMessages = messages[activeSessionId] || [];

  // ── API client ─────────────────────────────────────────────
  const api = useMemo(() =>
    createApiClient(settings.baseUrl),
    [settings.baseUrl]
  );

  // ── Create new session ─────────────────────────────────────
  const createSession = useCallback(() => {
    const id = generateId();
    const session = {
      id, title: "", createdAt: Date.now(), updatedAt: Date.now(),
      pinned: false, archived: false, tags: [],
    };
    setSessions((prev) => [session, ...prev]);
    setMessages((prev) => ({ ...prev, [id]: [] }));
    setActiveSessionId(id);
    setSidebarOpen(false);
  }, []);

  // ── Send pending message after session creation ─────────────
  useEffect(() => {
    if (activeSessionId && pendingMessageRef.current) {
      const text = pendingMessageRef.current;
      pendingMessageRef.current = null;
      sendMessage(text);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeSessionId]);

  // ── Send message ───────────────────────────────────────────
  const sendMessage = useCallback(async (text) => {
    if (!text.trim() || isGenerating || !user) return;
    if (!activeSessionId) {
      pendingMessageRef.current = text;
      createSession();
      return;
    }

    const userMsg = {
      id: generateId(), role: "user", content: text.trim(),
      timestamp: Date.now(), status: "done",
      quotedText: quotedText,
    };
    const aiMsg = {
      id: generateId(), role: "assistant", content: "",
      timestamp: Date.now(), status: "sending",
      sources: [], suggestions: [], confidence: 0,
    };

    setMessages((prev) => ({
      ...prev,
      [activeSessionId]: [...(prev[activeSessionId] || []), userMsg, aiMsg],
    }));
    setInputText("");
    setQuotedText(null);
    setIsGenerating(true);

    // Auto-generate title from first message
    if (!sessions.find((s) => s.id === activeSessionId)?.title) {
      const title = text.trim().slice(0, 30) + (text.trim().length > 30 ? "..." : "");
      setSessions((prev) => prev.map((s) =>
        s.id === activeSessionId ? { ...s, title, updatedAt: Date.now() } : s
      ));
    } else {
      setSessions((prev) => prev.map((s) =>
        s.id === activeSessionId ? { ...s, updatedAt: Date.now() } : s
      ));
    }

    const controller = new AbortController();
    abortRef.current = controller;

    // Incrementally update the AI message as SSE frames arrive. Keep the
    // streamed content in a local variable so each state update reflects
    // the latest accumulation even when tokens arrive faster than React
    // can flush.
    let streamedContent = "";
    let streamedSources = [];
    let streamedConfidence = 0;
    const patchAi = (patch) => {
      setMessages((prev) => ({
        ...prev,
        [activeSessionId]: prev[activeSessionId].map((m) =>
          m.id === aiMsg.id ? { ...m, ...patch } : m
        ),
      }));
    };

    try {
      await api.chatStream(
        user.userId,
        text.trim(),
        activeSessionId,
        {
          onMeta: (meta) => {
            streamedSources = meta.sources || [];
            streamedConfidence = meta.confidence || 0;
            patchAi({
              status: "streaming",
              sources: streamedSources,
              confidence: streamedConfidence,
            });
          },
          onToken: (chunk) => {
            streamedContent += chunk;
            patchAi({ content: streamedContent, status: "streaming" });
          },
          onDone: (done) => {
            patchAi({
              content: done.answer || streamedContent,
              status: "done",
              sources: streamedSources,
              suggestions: done.suggestions || [],
              confidence: streamedConfidence,
            });
          },
          onError: (err) => {
            throw err;
          },
        },
        controller.signal,
      );
    } catch (err) {
      if (err.name === "AbortError") {
        setMessages((prev) => ({
          ...prev,
          [activeSessionId]: prev[activeSessionId].map((m) =>
            m.id === aiMsg.id ? { ...m, status: "done", content: m.content || t.stop } : m
          ),
        }));
      } else if (streamedContent) {
        // Stream errored mid-way — keep what we got and mark done.
        patchAi({ content: streamedContent, status: "done" });
      } else {
        // Demo fallback when backend is unavailable
        const demoResponses = [
          "图书馆开放时间为：工作日 8:00-22:00，周末 9:00-21:00。自习室 7:00-22:30。\n\n借阅规则：本科生可借10册，研究生可借15册，借期30天，可续借一次。",
          "选课时间为2025年1月6日至1月10日，分三轮进行：\n\n1. **预选**（1月6-7日）\n2. **正选**（1月8-9日）\n3. **补退选**（1月10日）\n\n请登录教务系统 jwxt.bupt.edu.cn 进行操作。",
          "北邮校医院位于学校西门附近。\n\n- **门诊时间**：周一至周五 8:00-11:30, 13:30-17:00\n- **周六上午**：8:00-11:30（仅内科）\n- **急诊**：24小时开放\n- **心理咨询**：校医院2楼，预约电话：010-62281001",
          "作为北邮智能校园助理，我可以帮你：\n\n• 查询校园设施和服务信息\n• 了解教务相关通知和流程\n• 获取活动和社团信息\n• 查找建筑位置和导航\n\n有什么我可以帮到你的吗？",
        ];
        const fallback = demoResponses[Math.floor(Math.random() * demoResponses.length)];
        setMessages((prev) => ({
          ...prev,
          [activeSessionId]: prev[activeSessionId].map((m) =>
            m.id === aiMsg.id ? {
              ...m, content: fallback, status: "done",
              sources: [{ id: "demo", title: "演示数据", snippet: "后端未连接，显示本地演示回答", url: null, score: 0.9 }],
              suggestions: ["图书馆开放时间？", "如何申请转专业？", "校园网怎么连？"],
              confidence: 0.85,
            } : m
          ),
        }));
      }
    }

    setIsGenerating(false);
    abortRef.current = null;
  }, [activeSessionId, isGenerating, user, api, quotedText, sessions, createSession, t.stop]);

  const handleStop = () => {
    if (abortRef.current) abortRef.current.abort();
  };

  // ── Session operations ─────────────────────────────────────
  const deleteSession = (id) => {
    setSessions((prev) => prev.filter((s) => s.id !== id));
    setMessages((prev) => { const n = { ...prev }; delete n[id]; return n; });
    if (activeSessionId === id) setActiveSessionId(sessions.find((s) => s.id !== id)?.id || null);
  };

  const pinSession = (id) => {
    setSessions((prev) => prev.map((s) => s.id === id ? { ...s, pinned: !s.pinned } : s));
  };

  const exportSession = (id, format = "json") => {
    const msgs = messages[id] || [];
    const session = sessions.find((s) => s.id === id);
    let content, filename, type;
    if (format === "json") {
      content = JSON.stringify({ session, messages: msgs }, null, 2);
      filename = `${session?.title || id}.json`;
      type = "application/json";
    } else {
      content = msgs.map((m) => `**${m.role === "user" ? "用户" : "助手"}** (${formatTime(m.timestamp)}):\n${m.content}\n`).join("\n---\n\n");
      filename = `${session?.title || id}.md`;
      type = "text/markdown";
    }
    const blob = new Blob([content], { type });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = filename; a.click();
    URL.revokeObjectURL(url);
  };

  // ── Memory operations ──────────────────────────────────────
  const searchMemories = async (query) => {
    if (!user || !query.trim()) return;
    try {
      const result = await api.searchMemory(user.userId, query);
      setMemories(result.results || []);
    } catch {
      setMemories([]);
    }
  };

  const saveAsMemory = async (content) => {
    const newMem = {
      id: generateId(), content, type: "user_saved",
      importance_score: 0.8, timestamp: new Date().toISOString(),
      source_session: activeSession?.title || activeSessionId,
    };
    setMemories((prev) => [newMem, ...prev]);
    setRightPanel("memory");
  };

  // ── Profile functions ──────────────────────────────────────
  const refreshProfile = async () => {
    const allMsgs = Object.values(messages).flat();
    const userMsgs = allMsgs.filter((m) => m.role === "user").map((m) => m.content);

    if (userMsgs.length === 0) return;

    const topicCounts = {};
    const keywords = {
      "图书馆": "library", "食堂": "dining", "课程": "courses", "选课": "courses",
      "考试": "exams", "宿舍": "dormitory", "校园网": "network", "活动": "activities",
      "奖学金": "scholarship", "实习": "internship", "社团": "clubs", "运动": "sports",
      "报修": "repair", "转专业": "transfer", "毕业": "graduation", "校医院": "hospital",
      "校车": "shuttle", "快递": "delivery", "考研": "postgrad",
      "library": "library", "cafeteria": "dining", "course": "courses",
    };
    userMsgs.forEach((msg) => {
      Object.entries(keywords).forEach(([kw, topic]) => {
        if (msg.includes(kw)) topicCounts[topic] = (topicCounts[topic] || 0) + 1;
      });
    });

    const frequentTopics = Object.entries(topicCounts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 8)
      .map(([name, count]) => ({ name, count }));

    const inferredTags = [];
    if (userMsgs.length > 10) inferredTags.push({ label: "活跃用户", important: false });
    if (topicCounts["courses"] || topicCounts["exams"]) inferredTags.push({ label: "关注学业", important: true });
    if (topicCounts["activities"] || topicCounts["clubs"]) inferredTags.push({ label: "社交活跃", important: false });
    if (topicCounts["library"]) inferredTags.push({ label: "爱读书", important: false });
    if (topicCounts["internship"]) inferredTags.push({ label: "关注就业", important: true });
    if (topicCounts["postgrad"]) inferredTags.push({ label: "考研导向", important: true });

    const prefs = { ...(userProfile.preferences || {}) };
    if (settings.lang === "zh") prefs["语言偏好"] = "中文";
    if (settings.lang === "en") prefs["语言偏好"] = "English";
    if (settings.theme === "dark") prefs["主题偏好"] = "深色模式";

    const summaryParts = [];
    if (frequentTopics.length > 0) summaryParts.push(`经常关注：${frequentTopics.slice(0, 3).map((ft) => ft.name).join("、")}`);
    if (userMsgs.length > 0) summaryParts.push(`累计提问 ${userMsgs.length} 次`);
    if (inferredTags.length > 0) summaryParts.push(`性格特征：${inferredTags.map((it) => it.label).join("、")}`);

    setUserProfile((prev) => ({
      ...prev,
      preferences: prefs,
      personality_tags: [...(prev.personality_tags || []).filter((pt) => {
        const existing = inferredTags.map((it) => it.label);
        return !existing.includes(pt.label || pt);
      }), ...inferredTags],
      frequent_topics: frequentTopics,
      summary: summaryParts.join("。\n") + "。",
    }));
  };

  const exportProfile = () => {
    const data = {
      user: user?.userId,
      profile: userProfile,
      memories: memories,
      exportedAt: new Date().toISOString(),
    };
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `profile_${user?.userId || "user"}.json`; a.click();
    URL.revokeObjectURL(url);
  };

  const addManualMemory = (content) => {
    setMemories((prev) => [{
      id: generateId(), content, type: "manual",
      importance_score: 0.7, timestamp: new Date().toISOString(),
      source_session: null,
    }, ...prev]);
  };

  const feedbackMemory = (memId, feedback) => {
    setMemories((prev) => prev.map((m) =>
      m.id === memId ? { ...m, feedback: m.feedback === feedback ? null : feedback } : m
    ));
  };

  // ── Filter & sort sessions ─────────────────────────────────
  const filteredSessions = useMemo(() => {
    let list = [...sessions];
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      list = list.filter((s) => {
        if (s.title?.toLowerCase().includes(q)) return true;
        const msgs = messages[s.id] || [];
        return msgs.some((m) => m.content?.toLowerCase().includes(q));
      });
    }
    list.sort((a, b) => {
      if (a.pinned && !b.pinned) return -1;
      if (!a.pinned && b.pinned) return 1;
      return b.updatedAt - a.updatedAt;
    });
    return list;
  }, [sessions, searchQuery, messages]);

  const groupedSessions = useMemo(() => {
    const groups = { today: [], yesterday: [], earlier: [] };
    filteredSessions.forEach((s) => {
      const g = formatDate(s.updatedAt);
      groups[g]?.push(s);
    });
    return groups;
  }, [filteredSessions]);

  // ── Render ─────────────────────────────────────────────────
  return (
    <div className="xiaoqyou-root">
      {/* Mobile overlay */}
      <div className={`sidebar-overlay ${sidebarOpen ? "show" : ""}`}
        onClick={() => setSidebarOpen(false)} />

      <Sidebar
        sessions={groupedSessions}
        activeSessionId={activeSessionId}
        searchQuery={searchQuery}
        messages={messages}
        t={t}
        sidebarOpen={sidebarOpen}
        rightPanel={rightPanel}
        onCreateSession={createSession}
        onSelectSession={setActiveSessionId}
        onDeleteSession={deleteSession}
        onSearchChange={setSearchQuery}
        onSetRightPanel={setRightPanel}
        onLogout={() => { localStorage.removeItem("xiaoqyou_state"); window.location.reload(); }}
        onCloseSidebar={() => setSidebarOpen(false)}
      />

      <div className="main-area">
        <ChatHeader
          activeSession={activeSession}
          activeSessionId={activeSessionId}
          t={t}
          settings={settings}
          rightPanel={rightPanel}
          onOpenSidebar={() => setSidebarOpen(true)}
          onPinSession={pinSession}
          onExportSession={exportSession}
          onSetRightPanel={setRightPanel}
          onToggleTheme={() => {
            const next = settings.theme === "light" ? "dark" : "light";
            setSettings((p) => ({ ...p, theme: next }));
          }}
        />

        <ChatArea
          ref={messagesEndRef}
          messages={activeMessages}
          t={t}
          onSendMessage={sendMessage}
          onQuote={(text) => { setQuotedText(text); textareaRef.current?.focus(); }}
          onSaveMemory={saveAsMemory}
        />

        <InputArea
          ref={textareaRef}
          inputText={inputText}
          isGenerating={isGenerating}
          quotedText={quotedText}
          t={t}
          onInputChange={setInputText}
          onSend={sendMessage}
          onStop={handleStop}
          onClearQuote={() => setQuotedText(null)}
        />
      </div>

      {rightPanel === "settings" && (
        <SettingsPanel
          onClose={() => setRightPanel(null)} t={t}
          settings={settings}
          onUpdate={(patch) => setSettings((p) => ({ ...p, ...patch }))}
        />
      )}
      {rightPanel === "memory" && (
        <MemoryPanel
          onClose={() => setRightPanel(null)} t={t}
          memories={memories} onSearch={searchMemories}
          onDelete={(id) => setMemories((prev) => prev.filter((m) => m.id !== id))}
        />
      )}
      {rightPanel === "profile" && (
        <ProfilePanel
          onClose={() => setRightPanel(null)} t={t}
          profile={userProfile}
          onUpdateProfile={setUserProfile}
          onRefresh={refreshProfile}
          onExport={exportProfile}
          memories={memories}
          onAddManualMemory={addManualMemory}
          onDeleteMemory={(id) => setMemories((prev) => prev.filter((m) => m.id !== id))}
          onFeedbackMemory={feedbackMemory}
        />
      )}
    </div>
  );
}
