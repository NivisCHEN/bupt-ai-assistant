export const createApiClient = (baseUrl, token) => {
  const headers = () => {
    const h = { "Content-Type": "application/json" };
    if (token) h["X-User-Token"] = token;
    return h;
  };

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
