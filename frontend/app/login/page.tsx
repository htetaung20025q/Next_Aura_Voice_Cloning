"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/AuthContext";

export default function LoginPage() {
  const router = useRouter();
  const { login, user } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (user) {
      router.replace("/");
    }
  }, [user, router]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);

    const result = await login(email, password);
    setLoading(false);

    if (result.ok) {
      router.push("/");
    } else {
      setError(result.error || "Authentication failed. Please check your credentials.");
    }
  }

  return (
    <main className="authPage">
      <nav className="nav">
        <Link href="/" className="brandLink">
          <div className="brand">
            <span className="mark">N</span>
            <div>
              <b>Next Aura</b>
              <small>VOICE STUDIO</small>
            </div>
          </div>
        </Link>
        <div className="navActions">
          <Link href="/register" className="textBtn">
            Create account →
          </Link>
        </div>
      </nav>

      <div className="authContainer">
        <div className="authCard">
          <p className="eyebrow">WELCOME BACK</p>
          <h2>Sign in to your account</h2>
          <p className="muted">Enter your email and password to access your voice studio.</p>

          {error && <div className="error">{error}</div>}

          <form onSubmit={handleSubmit} className="authForm">
            <div>
              <label className="fieldLabel">Email Address</label>
              <input
                className="input"
                type="email"
                placeholder="name@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>

            <div>
              <label className="fieldLabel">Password</label>
              <input
                className="input"
                type="password"
                placeholder="Your password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>

            <button className="blackBtn full" type="submit" disabled={loading}>
              {loading ? "Signing in…" : "Sign In →"}
            </button>
          </form>

          <div className="authFooter">
            <span>Don't have an account?</span>{" "}
            <Link href="/register" className="authLink">
              Sign up here
            </Link>
          </div>
        </div>
      </div>

      <style jsx>{`
        .authPage {
          min-height: 100vh;
          background: #fafafa;
          display: flex;
          flex-direction: column;
        }
        .brandLink {
          text-decoration: none;
          color: inherit;
        }
        .authContainer {
          flex: 1;
          display: grid;
          place-items: center;
          padding: 40px 20px 80px;
        }
        .authCard {
          background: #fff;
          border: 1px solid #e5e5e5;
          border-radius: 20px;
          width: min(440px, 100%);
          padding: 40px 34px;
          box-shadow: 0 10px 40px rgba(0, 0, 0, 0.04);
        }
        .authCard h2 {
          font-size: 26px;
          letter-spacing: -1px;
          margin: 0 0 8px;
        }
        .fieldLabel {
          display: block;
          font-size: 12px;
          font-weight: 700;
          color: #444;
          margin-top: 14px;
        }
        .authForm {
          display: flex;
          flex-direction: column;
          gap: 12px;
          margin-top: 14px;
        }
        .authFooter {
          margin-top: 24px;
          text-align: center;
          font-size: 13px;
          color: #666;
        }
        .authLink {
          color: #000;
          font-weight: 700;
          text-decoration: none;
        }
        .authLink:hover {
          text-decoration: underline;
        }
      `}</style>
    </main>
  );
}
