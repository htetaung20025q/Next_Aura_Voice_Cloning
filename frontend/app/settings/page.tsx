"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/AuthContext";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const pricingPlans = [
  {
    id: "free",
    name: "Free",
    price: "0 MMK",
    words: "100 words / generation",
    uses: "1 free lifetime generation",
    description: "Standard voice generation with essential VoxCPM features.",
    note: "Free tier for registered users",
  },
  {
    id: "weekly",
    name: "Weekly Pro",
    price: "25,000 MMK",
    words: "5,000 words / generation",
    uses: "6 generations / week",
    description: "Extended word limits and Ultimate Voice Cloning capabilities.",
    note: "Account required · Most popular",
  },
  {
    id: "unlimited",
    name: "Unlimited Pro",
    price: "50,000 MMK",
    words: "5,000 words / generation",
    uses: "Unlimited generations",
    description: "Maximum generation capacity with priority processing queue.",
    note: "Account required · Professional studio",
  },
];

interface QuotaData {
  id?: number | null;
  email?: string | null;
  plan: string;
  is_pro?: boolean;
  subscription_active?: boolean;
  used_generations: number;
  weekly_generations: number | null;
  weekly_generations_used: number;
  weekly_generations_limit: number | null;
  max_words: number;
  words_limit: number;
  credits?: number | null;
  token_usage?: number;
  generation_limit?: number | null;
  generation_period?: string;
  free_generations_used?: number;
  free_generations_limit?: number;
  active_from?: string | null;
  active_until?: string | null;
  resets_at?: string | null;
}

export default function SettingsPage() {
  const router = useRouter();
  const { user, token, isPro, logout, refreshUser } = useAuth();

  const [quota, setQuota] = useState<QuotaData | null>(null);
  const [loadingQuota, setLoadingQuota] = useState(false);
  const [purchaseModalPlan, setPurchaseModalPlan] = useState<string | null>(null);
  const [paymentRef, setPaymentRef] = useState("");
  const [submittingPurchase, setSubmittingPurchase] = useState(false);
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  const fetchQuotaData = useCallback(async () => {
    setLoadingQuota(true);
    try {
      if (token) {
        const res = await fetch(`${API}/api/me`, {
          headers: { Authorization: `Bearer ${token}` },
          credentials: "include",
        });
        if (res.ok) {
          const data: QuotaData = await res.json();
          setQuota(data);
          return;
        }
      }
      const res = await fetch(`${API}/api/voice/quota`, {
        credentials: "include",
      });
      if (res.ok) {
        const data: QuotaData = await res.json();
        setQuota(data);
      }
    } catch {
      // Network failure
    } finally {
      setLoadingQuota(false);
    }
  }, [token]);

  useEffect(() => {
    fetchQuotaData();
  }, [fetchQuotaData]);

  async function handleLogout() {
    await logout();
    router.push("/");
  }

  function handleChoosePlan(planId: string) {
    if (planId === "free") {
      router.push("/");
      return;
    }
    if (!token || !user) {
      router.push("/login");
      return;
    }
    setPurchaseModalPlan(planId);
    setPaymentRef("");
    setMessage(null);
  }

  async function submitPurchaseRequest(e: React.FormEvent) {
    e.preventDefault();
    if (!purchaseModalPlan || !paymentRef.trim() || !token) return;

    setSubmittingPurchase(true);
    setMessage(null);
    try {
      const res = await fetch(`${API}/api/purchases`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          plan: purchaseModalPlan,
          payment_reference: paymentRef.trim(),
        }),
        credentials: "include",
      });
      const data = await res.json();
      if (res.ok) {
        setMessage({
          type: "success",
          text: "Purchase request submitted successfully. Administrator will review and activate your plan.",
        });
        setPurchaseModalPlan(null);
        setPaymentRef("");
        await refreshUser();
        await fetchQuotaData();
      } else {
        setMessage({
          type: "error",
          text: data.detail || "Could not submit purchase request.",
        });
      }
    } catch {
      setMessage({
        type: "error",
        text: "Network error while submitting purchase request.",
      });
    } finally {
      setSubmittingPurchase(false);
    }
  }

  const effectivePlan = (user?.plan || quota?.plan || "free").toLowerCase();
  const effectiveIsPro = isPro || Boolean(quota?.is_pro);
  const activeUntil = user?.plan_active_until || quota?.active_until;
  const activeFrom = user?.plan_active_from || quota?.active_from;

  const freeGenerationsUsed = quota?.free_generations_used ?? (user?.free_generations_used ?? 0);
  const freeRemaining = Math.max(0, 1 - freeGenerationsUsed);

  const creditsRemaining = quota?.credits !== undefined && quota?.credits !== null
    ? quota.credits
    : effectivePlan === "unlimited" || user?.is_admin
    ? null
    : effectivePlan === "weekly"
    ? Math.max(0, 6 - (quota?.used_generations || 0))
    : freeRemaining;

  const tokenUsage = quota?.token_usage ?? (user?.token_usage ?? 0);

  return (
    <main className="settingsPage">
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
          {user?.is_admin && (
            <Link href="/admin" className="textBtn">
              Admin Portal
            </Link>
          )}
          <Link href="/" className="textBtn">
            ← Studio
          </Link>
          {user ? (
            <button className="logoutBtn" onClick={handleLogout}>
              Log out
            </button>
          ) : (
            <Link href="/login" className="blackBtn small">
              Sign In
            </Link>
          )}
        </div>
      </nav>

      <div className="settingsContainer">
        <div className="settingsHeader">
          <p className="eyebrow">SETTINGS & SUBSCRIPTION</p>
          <h1>Account & Usage</h1>
          <p className="subText">
            Manage your subscription plan, view token and generation usage, and review account details.
          </p>
        </div>

        {message && (
          <div className={`alertBanner ${message.type === "success" ? "alertSuccess" : "alertError"}`}>
            {message.text}
          </div>
        )}

        <div className="settingsGrid">
          {/* Section 1: Account Information */}
          <section className="settingsCard">
            <div className="cardHeader">
              <h2>Account Information</h2>
              <span className="badge">
                {user?.is_admin ? "Administrator" : user ? "Verified Member" : "Guest Mode"}
              </span>
            </div>

            <div className="infoList">
              <div className="infoRow">
                <span className="infoLabel">Email Address</span>
                <span className="infoValue">{user?.email || "Not signed in"}</span>
              </div>
              <div className="infoRow">
                <span className="infoLabel">Account ID</span>
                <span className="infoValue">{user?.id ? `#${user.id}` : "Anonymous Session"}</span>
              </div>
              <div className="infoRow">
                <span className="infoLabel">Member Since</span>
                <span className="infoValue">
                  {user?.created_at ? new Date(user.created_at).toLocaleDateString() : "Current Session"}
                </span>
              </div>
            </div>

            {!user && (
              <div className="cardAction">
                <Link href="/login" className="blackBtn full">
                  Sign in to Save Account →
                </Link>
              </div>
            )}
          </section>

          {/* Section 2: Subscription Status */}
          <section className="settingsCard">
            <div className="cardHeader">
              <h2>Subscription Status</h2>
              <span className={`planPill ${effectiveIsPro ? "proBadge" : "freeBadge"}`}>
                {effectiveIsPro ? `PRO · ${effectivePlan.toUpperCase()}` : "FREE PLAN"}
              </span>
            </div>

            <div className="infoList">
              <div className="infoRow">
                <span className="infoLabel">Current Plan</span>
                <span className="infoValue strong">
                  {effectivePlan.charAt(0).toUpperCase() + effectivePlan.slice(1)} Plan
                </span>
              </div>

              {effectiveIsPro && activeFrom && (
                <div className="infoRow">
                  <span className="infoLabel">Activated On</span>
                  <span className="infoValue">{new Date(activeFrom).toLocaleDateString()}</span>
                </div>
              )}

              {effectiveIsPro && activeUntil && (
                <div className="infoRow">
                  <span className="infoLabel">Valid Until</span>
                  <span className="infoValue highlight">{new Date(activeUntil).toLocaleDateString()}</span>
                </div>
              )}

              <div className="infoRow">
                <span className="infoLabel">Status</span>
                <span className={`statusTag ${effectiveIsPro ? "statusActive" : "statusNeutral"}`}>
                  {effectiveIsPro ? "● Active Subscription" : "● Free Tier"}
                </span>
              </div>
            </div>
          </section>

          {/* Section 3: Credits & Token Usage */}
          <section className="settingsCard fullWidth">
            <div className="cardHeader">
              <div>
                <h2>Credits & Generation Usage</h2>
                <p className="cardSub">Calculated in real-time from backend database records.</p>
              </div>
              <button className="refreshBtn" onClick={fetchQuotaData} disabled={loadingQuota}>
                {loadingQuota ? "Refreshing…" : "↻ Refresh Quota"}
              </button>
            </div>

            <div className="statsGrid">
              <div className="statBox">
                <span className="statLabel">Generations Available</span>
                <strong className="statValue">
                  {effectivePlan === "unlimited"
                    ? "Unlimited"
                    : effectivePlan === "weekly"
                    ? `${creditsRemaining} credits`
                    : `Free Generation: ${freeGenerationsUsed} / 1`}
                </strong>
                <small className="statNote">
                  {effectivePlan === "unlimited"
                    ? "Unlimited generations"
                    : effectivePlan === "weekly"
                    ? `${quota?.used_generations ?? 0} used of 6 weekly limit`
                    : `Remaining: ${freeRemaining} / 1 · Lifetime quota`}
                </small>
              </div>

              <div className="statBox">
                <span className="statLabel">Max Words / Generation</span>
                <strong className="statValue">
                  {quota?.max_words ? `${quota.max_words.toLocaleString()} words` : effectiveIsPro ? "5,000 words" : "100 words"}
                </strong>
                <small className="statNote">
                  {effectiveIsPro ? "Pro allocation per script" : "100 words maximum for Free tier"}
                </small>
              </div>

              <div className="statBox">
                <span className="statLabel">Tokens / Words Synthesized</span>
                <strong className="statValue">{tokenUsage.toLocaleString()} words</strong>
                <small className="statNote">Total script volume synthesized</small>
              </div>

              <div className="statBox">
                <span className="statLabel">Reset Schedule</span>
                <strong className="statValue">
                  {effectiveIsPro
                    ? quota?.resets_at
                      ? new Date(quota.resets_at).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" })
                      : "Monday 00:00 UTC"
                    : "No Reset (1 Lifetime)"}
                </strong>
                <small className="statNote">
                  {effectiveIsPro ? "Weekly quotas reset every Monday" : "Upgrade to Pro for recurring weekly limits"}
                </small>
              </div>
            </div>
          </section>

          {/* Section 4: Pricing Plans */}
          <section className="settingsCard fullWidth">
            <div className="cardHeader">
              <div>
                <h2>Available Pricing Plans</h2>
                <p className="cardSub">Choose a tier that matches your production speech volume.</p>
              </div>
            </div>

            <div className="pricingPlansGrid">
              {pricingPlans.map((p) => {
                const isCurrent = effectivePlan === p.id;
                return (
                  <div className={`planCard ${p.id === "weekly" ? "featuredPlan" : ""}`} key={p.id}>
                    {p.id === "weekly" && <span className="featuredBadge">RECOMMENDED</span>}
                    <div className="planHead">
                      <h3>{p.name}</h3>
                      <strong className="planPrice">{p.price}</strong>
                      <p className="planDesc">{p.description}</p>
                    </div>

                    <ul className="planFeatures">
                      <li>✓ {p.words}</li>
                      <li>✓ {p.uses}</li>
                      <li>✓ {p.note}</li>
                    </ul>

                    <div className="planAction">
                      {isCurrent ? (
                        <button className="currentPlanBtn" disabled>
                          Current Active Plan
                        </button>
                      ) : p.id === "free" ? (
                        <button className="outlineBtn" onClick={() => router.push("/")}>
                          Use Free Tier
                        </button>
                      ) : (
                        <button className="blackBtn full" onClick={() => handleChoosePlan(p.id)}>
                          Upgrade to {p.name} →
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </section>

          {/* Section 5: Security & Sign Out */}
          {user && (
            <section className="settingsCard fullWidth dangerZone">
              <div className="cardHeader">
                <div>
                  <h2>Session & Sign Out</h2>
                  <p className="cardSub">Securely invalidate your current active JWT session and clear stored tokens.</p>
                </div>
                <button className="logoutBtn danger" onClick={handleLogout}>
                  Log Out of Next Aura
                </button>
              </div>
            </section>
          )}
        </div>
      </div>

      {/* Purchase Request Modal */}
      {purchaseModalPlan && token && (
        <div className="modalBack">
          <div className="modal">
            <button className="close" onClick={() => setPurchaseModalPlan(null)}>
              ×
            </button>
            <p className="eyebrow">PREMIUM SUBSCRIPTION REQUEST</p>
            <h2>{purchaseModalPlan === "weekly" ? "Weekly Pro · 25,000 MMK" : "Unlimited Pro · 50,000 MMK"}</h2>
            <p className="muted">
              Transfer payment using KBZPay or WavePay, then enter your transaction reference ID below for administrator approval.
            </p>

            <form onSubmit={submitPurchaseRequest} className="purchaseForm">
              <div className="paymentDetails">
                <span className="payOption">KBZPay / WavePay: <strong>09-777-000-111</strong></span>
                <span className="payOption">Account Name: <strong>Next Aura Voice Studio</strong></span>
              </div>

              <div>
                <label className="fieldLabel">Transaction Reference / Transaction ID</label>
                <input
                  className="input"
                  placeholder="e.g. 2026100412345678"
                  value={paymentRef}
                  onChange={(e) => setPaymentRef(e.target.value)}
                  required
                />
              </div>

              <button
                className="blackBtn full"
                type="submit"
                disabled={!paymentRef.trim() || submittingPurchase}
              >
                {submittingPurchase ? "Submitting Request…" : "Submit Purchase Request →"}
              </button>
            </form>
          </div>
        </div>
      )}

      <style jsx>{`
        .settingsPage {
          min-height: 100vh;
          background: #fafafa;
          color: #111;
          display: flex;
          flex-direction: column;
        }
        .settingsContainer {
          max-width: 1080px;
          margin: 0 auto;
          padding: 48px 24px 80px;
          width: 100%;
        }
        .settingsHeader {
          margin-bottom: 36px;
        }
        .settingsHeader h1 {
          font-size: clamp(32px, 4vw, 44px);
          letter-spacing: -1.5px;
          margin: 0 0 8px;
          font-weight: 800;
        }
        .subText {
          color: #666;
          font-size: 15px;
          margin: 0;
          max-width: 600px;
          line-height: 1.5;
        }
        .alertBanner {
          padding: 14px 18px;
          border-radius: 12px;
          font-size: 13px;
          font-weight: 500;
          margin-bottom: 24px;
        }
        .alertSuccess {
          background: #dcfce7;
          color: #166534;
          border: 1px solid #bbf7d0;
        }
        .alertError {
          background: #fee2e2;
          color: #991b1b;
          border: 1px solid #fecaca;
        }
        .settingsGrid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 24px;
        }
        .settingsCard {
          background: #fff;
          border: 1px solid #e5e5e5;
          border-radius: 18px;
          padding: 28px;
          display: flex;
          flex-direction: column;
          gap: 20px;
          box-shadow: 0 4px 20px rgba(0, 0, 0, 0.02);
        }
        .fullWidth {
          grid-column: 1 / -1;
        }
        .cardHeader {
          display: flex;
          justify-content: space-between;
          align-items: flex-start;
          gap: 16px;
        }
        .cardHeader h2 {
          font-size: 20px;
          letter-spacing: -0.5px;
          margin: 0;
          font-weight: 700;
        }
        .cardSub {
          font-size: 13px;
          color: #666;
          margin: 4px 0 0;
        }
        .badge {
          font-size: 11px;
          font-weight: 600;
          background: #f4f4f5;
          color: #555;
          padding: 4px 10px;
          border-radius: 20px;
          border: 1px solid #e4e4e7;
        }
        .infoList {
          display: flex;
          flex-direction: column;
          gap: 14px;
        }
        .infoRow {
          display: flex;
          justify-content: space-between;
          align-items: center;
          border-bottom: 1px solid #f4f4f5;
          padding-bottom: 12px;
          font-size: 13px;
        }
        .infoRow:last-child {
          border-bottom: none;
          padding-bottom: 0;
        }
        .infoLabel {
          color: #777;
        }
        .infoValue {
          font-weight: 500;
          color: #111;
        }
        .infoValue.strong {
          font-weight: 700;
        }
        .infoValue.highlight {
          color: #0284c7;
          font-weight: 600;
        }
        .statusTag {
          font-size: 12px;
          font-weight: 600;
        }
        .statusActive {
          color: #16a34a;
        }
        .statusNeutral {
          color: #64748b;
        }
        .statsGrid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
          gap: 16px;
        }
        .statBox {
          background: #fafafa;
          border: 1px solid #eee;
          border-radius: 12px;
          padding: 18px;
          display: flex;
          flex-direction: column;
          gap: 6px;
        }
        .statLabel {
          font-size: 12px;
          color: #777;
          font-weight: 500;
        }
        .statValue {
          font-size: 20px;
          font-weight: 800;
          letter-spacing: -0.5px;
          color: #000;
        }
        .statNote {
          font-size: 11px;
          color: #888;
          line-height: 1.4;
        }
        .refreshBtn {
          background: #fff;
          border: 1px solid #ddd;
          border-radius: 8px;
          padding: 6px 12px;
          font-size: 12px;
          font-weight: 600;
          color: #444;
          transition: 0.15s ease;
        }
        .refreshBtn:hover {
          border-color: #000;
          color: #000;
        }
        .pricingPlansGrid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
          gap: 20px;
          margin-top: 8px;
        }
        .planCard {
          background: #fff;
          border: 1px solid #dedede;
          border-radius: 16px;
          padding: 24px;
          display: flex;
          flex-direction: column;
          position: relative;
          transition: 0.2s ease;
        }
        .featuredPlan {
          border: 2px solid #000;
          box-shadow: 0 10px 30px rgba(0, 0, 0, 0.04);
        }
        .featuredBadge {
          position: absolute;
          top: -12px;
          right: 20px;
          background: #000;
          color: #fff;
          font-size: 10px;
          font-weight: 800;
          letter-spacing: 0.5px;
          padding: 4px 10px;
          border-radius: 20px;
        }
        .planHead h3 {
          font-size: 18px;
          margin: 0 0 6px;
          font-weight: 700;
        }
        .planPrice {
          font-size: 26px;
          letter-spacing: -1px;
          display: block;
          margin-bottom: 8px;
        }
        .planDesc {
          font-size: 13px;
          color: #666;
          margin: 0;
          line-height: 1.4;
        }
        .planFeatures {
          list-style: none;
          padding: 16px 0;
          margin: 16px 0;
          border-top: 1px solid #eee;
          border-bottom: 1px solid #eee;
          display: flex;
          flex-direction: column;
          gap: 8px;
          flex: 1;
        }
        .planFeatures li {
          font-size: 13px;
          color: #444;
        }
        .planAction {
          margin-top: auto;
        }
        .currentPlanBtn {
          width: 100%;
          background: #f4f4f5;
          color: #888;
          border: 1px solid #e4e4e7;
          border-radius: 10px;
          padding: 12px;
          font-weight: 700;
          font-size: 13px;
          cursor: default;
        }
        .dangerZone {
          border-color: #fee2e2;
          background: #fffafa;
        }
        .logoutBtn {
          background: #fff;
          border: 1px solid #ddd;
          border-radius: 8px;
          padding: 7px 14px;
          font-size: 12px;
          font-weight: 600;
          color: #333;
        }
        .logoutBtn.danger {
          border-color: #fca5a5;
          color: #dc2626;
          background: #fff;
        }
        .logoutBtn.danger:hover {
          background: #fee2e2;
        }
        .purchaseForm {
          display: flex;
          flex-direction: column;
          gap: 16px;
          margin-top: 18px;
        }
        .paymentDetails {
          background: #f9f9f9;
          border: 1px solid #eee;
          border-radius: 10px;
          padding: 12px 14px;
          display: flex;
          flex-direction: column;
          gap: 4px;
          font-size: 12px;
        }
        .payOption strong {
          color: #000;
        }
        .cardAction {
          margin-top: 12px;
        }
        @media (max-width: 768px) {
          .settingsGrid {
            grid-template-columns: 1fr;
          }
        }
      `}</style>
    </main>
  );
}
