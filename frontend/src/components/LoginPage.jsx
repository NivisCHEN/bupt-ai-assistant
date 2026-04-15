import { useState } from "react";
import { BUPTLogo } from "./Icons";

export default function LoginPage({ onLogin, t }) {
  const [studentId, setStudentId] = useState("");
  const [password, setPassword] = useState("");
  const [isRegister, setIsRegister] = useState(false);
  const [nickname, setNickname] = useState("");

  const handleSubmit = () => {
    if (!studentId.trim()) return;
    const token = `${studentId}:${Math.floor(Date.now() / 1000)}:demo_signature_placeholder`;
    onLogin({ userId: studentId, nickname: nickname || studentId, token, password });
  };

  return (
    <div className="login-page">
      <div className="login-card">
        <div style={{ display: "flex", justifyContent: "center" }}>
          <BUPTLogo size={56} />
        </div>
        <h1>{t.loginTitle}</h1>
        <p className="subtitle">{t.loginSubtitle}</p>
        <input
          className="login-input" type="text" placeholder={t.studentId}
          value={studentId} onChange={(e) => setStudentId(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
        />
        <input
          className="login-input" type="password" placeholder={t.password}
          value={password} onChange={(e) => setPassword(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
        />
        {isRegister && (
          <input
            className="login-input" type="text" placeholder={t.nickname}
            value={nickname} onChange={(e) => setNickname(e.target.value)}
          />
        )}
        <button className="login-btn" onClick={handleSubmit}>
          {isRegister ? t.register : t.login}
        </button>
        <p
          style={{ textAlign: "center", marginTop: 16, fontSize: 13, color: "var(--text-link)", cursor: "pointer" }}
          onClick={() => setIsRegister(!isRegister)}
        >
          {isRegister ? t.login : t.register}
        </p>
      </div>
    </div>
  );
}
