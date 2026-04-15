export const generateId = () =>
  `${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;

export const formatTime = (ts) => {
  const d = new Date(ts);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
};

export const formatDate = (ts) => {
  const d = new Date(ts);
  const now = new Date();
  const diff = (now - d) / 86400000;
  if (diff < 1 && d.getDate() === now.getDate()) return "today";
  if (diff < 2) return "yesterday";
  return "earlier";
};
