// If no token is produced in this many ms we abort the request and surface
// a clean error instead of leaving the UI stuck on "sending...".
const STREAM_IDLE_TIMEOUT_MS = 90_000;

export const createApiClient = (baseUrl) => {
  const headers = () => ({ "Content-Type": "application/json" });

  return {
    chat: async (userId, query, sessionId, signal) => {
      const res = await fetch(`${baseUrl}/api/chat`, {
        method: "POST",
        headers: headers(),
        body: JSON.stringify({
          user_id: userId,
          query,
          session_id: sessionId,
        }),
        signal,
      });
      if (!res.ok) throw new Error(`Chat failed: ${res.status}`);
      return res.json();
    },

    /**
     * Stream a chat response from /api/chat/stream (SSE).
     *
     * @param {string} userId
     * @param {string} query
     * @param {string} sessionId
     * @param {object} callbacks - {onMeta, onToken, onDone, onError}
     * @param {AbortSignal} [externalSignal] - optional user-triggered abort
     */
    chatStream: async (userId, query, sessionId, callbacks, externalSignal) => {
      const controller = new AbortController();
      // Link user-triggered abort (e.g. "stop" button) to our own controller.
      if (externalSignal) {
        if (externalSignal.aborted) controller.abort();
        else externalSignal.addEventListener("abort", () => controller.abort());
      }

      // Idle-timeout: reset each time we receive data; abort if quiet too long.
      let idleTimer;
      const resetIdle = () => {
        if (idleTimer) clearTimeout(idleTimer);
        idleTimer = setTimeout(() => controller.abort(), STREAM_IDLE_TIMEOUT_MS);
      };
      resetIdle();

      let res;
      try {
        res = await fetch(`${baseUrl}/api/chat/stream`, {
          method: "POST",
          headers: headers(),
          body: JSON.stringify({
            user_id: userId,
            query,
            session_id: sessionId,
          }),
          signal: controller.signal,
        });
      } catch (err) {
        clearTimeout(idleTimer);
        throw err;
      }
      if (!res.ok) {
        clearTimeout(idleTimer);
        throw new Error(`Chat stream failed: ${res.status}`);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      try {
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          resetIdle();
          buffer += decoder.decode(value, { stream: true });

          // SSE frames are separated by blank lines.
          let sep;
          while ((sep = buffer.indexOf("\n\n")) >= 0) {
            const frame = buffer.slice(0, sep);
            buffer = buffer.slice(sep + 2);

            let eventType = "message";
            let dataLine = "";
            for (const line of frame.split("\n")) {
              if (line.startsWith("event:")) eventType = line.slice(6).trim();
              else if (line.startsWith("data:"))
                dataLine += line.slice(5).trimStart();
            }
            if (!dataLine) continue;

            let payload;
            try {
              payload = JSON.parse(dataLine);
            } catch {
              continue;
            }

            if (eventType === "meta") callbacks.onMeta?.(payload);
            else if (eventType === "token") callbacks.onToken?.(payload.content);
            else if (eventType === "done") callbacks.onDone?.(payload);
            else if (eventType === "error")
              callbacks.onError?.(new Error(payload.message || "stream error"));
          }
        }
      } finally {
        clearTimeout(idleTimer);
      }
    },
    health: async () => {
      const res = await fetch(`${baseUrl}/api/health`);
      return res.json();
    },
    searchMemory: async (userId, query, topK = 5) => {
      const res = await fetch(`${baseUrl}/api/memory/${userId}/search`, {
        method: "POST",
        headers: headers(),
        body: JSON.stringify({ query, top_k: topK }),
      });
      if (!res.ok) throw new Error(`Memory search failed: ${res.status}`);
      return res.json();
    },
    getHistory: async (userId, limit = 10) => {
      const res = await fetch(
        `${baseUrl}/api/memory/${userId}/history?limit=${limit}`,
        { headers: headers() }
      );
      if (!res.ok) throw new Error(`History failed: ${res.status}`);
      return res.json();
    },
    deleteMemory: async (userId, memoryId) => {
      const confirmToken = `confirm-delete-${memoryId}`;
      const res = await fetch(
        `${baseUrl}/api/memory/${userId}/${memoryId}?confirmation_token=${confirmToken}`,
        { method: "DELETE", headers: headers() }
      );
      if (!res.ok) throw new Error(`Delete failed: ${res.status}`);
      return res.json();
    },
    portalLogin: async (username, password) => {
      const res = await fetch(`${baseUrl}/api/portal/login`, {
        method: "POST",
        headers: headers(),
        body: JSON.stringify({ username, password }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Portal login failed: ${res.status}`);
      }
      return res.json();
    },
    portalCrawl: async (username) => {
      const res = await fetch(
        `${baseUrl}/api/portal/crawl?username=${encodeURIComponent(username)}`,
        { method: "POST", headers: headers() }
      );
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Portal crawl failed: ${res.status}`);
      }
      return res.json();
    },
  };
};
