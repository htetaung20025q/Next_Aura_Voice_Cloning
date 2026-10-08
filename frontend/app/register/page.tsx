"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/AuthContext";

export default function RegisterPage() {
  const router = useRouter();
  const { register, user } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
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

    if (password.length < 8) {
      setError("Password must be at least 8 characters long.");
      return;
    }

    if (password !== confirmPassword) {
      setError("Passwords do not match. Please verify your confirmation password.");
      return;
    }

    setLoading(true);
    const result = await register(email, password);
    setLoading(false);

    if (result.ok) {
      router.push("/");
    } else {
      setError(result.error || "Registration failed. Please check password requirements.");
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
          <Link href="/login" className="textBtn">
            Sign in →
          </Link>
        </div>
      </nav>

      <div className="authContainer">
        <div className="authCard">
          <p className="eyebrow">GET STARTED</p>
          <h2>Create your account</h2>
          <p className="muted">Join Next Aura to clone voices, generate speech, and manage subscriptions.</p>

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
                placeholder="Minimum 8 characters with digits/symbols"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>

            <div>
              <label className="fieldLabel">Confirm Password</label>
              <input
                className="input"
                type="password"
                placeholder="Re-type your password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                required
              />
            </div>

            <button className="blackBtn full" type="submit" disabled={loading}>
              {loading ? "Creating account…" : "Create Account →"}
            </button>
          </form>

          <div className="authFooter">
            <span>Already have an account?</span>{" "}
            <Link href="/login" className="authLink">
              Sign in here
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
