"use client";

import { useEffect, useState, useCallback } from "react";
import { useAuth } from "@/lib/AuthContext";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface PurchaseItem {
  id: number;
  user_id: number;
  user_email?: string | null;
  plan: string;
  amount_mmk: number;
  payment_reference: string;
  status: "pending" | "approved" | "rejected";
  duration_months?: number | null;
  plan_active_from?: string | null;
  plan_active_until?: string | null;
  rejection_reason?: string | null;
  created_at: string;
  approved_by_user_id?: number | null;
  approved_at?: string | null;
}

export default function Admin() {
  const { user, token, isLoading: authLoading, login, logout } = useAuth();

  const [rows, setRows] = useState<PurchaseItem[]>([]);
  const [err, setErr] = useState("");
  const [successMsg, setSuccessMsg] = useState("");
  const [loadingRows, setLoadingRows] = useState(false);
  const [processingId, setProcessingId] = useState<number | null>(null);
  const [durations, setDurations] = useState<Record<number, number>>({});

  // Admin login form state for unauthenticated / non-admin viewers
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loginSubmitting, setLoginSubmitting] = useState(false);

  function getDurationFor(id: number): number {
    return durations[id] !== undefined ? durations[id] : 1;
  }

  function setDurationFor(id: number, months: number) {
    setDurations((prev) => ({ ...prev, [id]: Math.max(1, months) }));
  }

  function calculateExpiryPreview(months: number): string {
    const d = new Date();
    d.setMonth(d.getMonth() + months);
    return d.toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  }

  function formatExpiryStatus(untilIso?: string | null): { text: string; isExpired: boolean } {
    if (!untilIso) return { text: "Indefinite", isExpired: false };
    const until = new Date(untilIso).getTime();
    const now = Date.now();
    const diff = until - now;
    if (diff <= 0) {
      return { text: "Expired", isExpired: true };
    }
    const days = Math.ceil(diff / (1000 * 60 * 60 * 24));
    return { text: `${days} day${days === 1 ? "" : "s"} remaining`, isExpired: false };
  }

  const loadPurchases = useCallback(async (authToken?: string) => {
    const activeToken = authToken || token;
    if (!activeToken) return;
    setLoadingRows(true);
    setErr("");
    try {
      const r = await fetch(`${API}/api/admin/purchases`, {
        headers: { Authorization: `Bearer ${activeToken}` },
        credentials: "include",
      });
      if (!r.ok) {
        const d = await r.json().catch(() => ({}));
        setErr(d.detail || "Admin access required. Please log in with administrator credentials.");
        return;
      }
      const data: PurchaseItem[] = await r.json();
      setRows(data);
    } catch {
      setErr("Failed to connect to server. Please verify backend is running.");
    } finally {
      setLoadingRows(false);
    }
  }, [token]);

  useEffect(() => {
    if (!authLoading && user && user.is_admin && token) {
      loadPurchases(token);
    }
  }, [authLoading, user, token, loadPurchases]);

  async function handleAdminLogin(e: React.FormEvent) {
    e.preventDefault();
    setErr("");
    setSuccessMsg("");
    setLoginSubmitting(true);
    try {
      const res = await login(email.trim(), password);
      if (!res.ok) {
        setErr(res.error || "Authentication failed. Invalid email or password.");
        return;
      }
      setPassword("");
    } catch {
      setErr("Could not reach authentication server.");
    } finally {
      setLoginSubmitting(false);
    }
  }

  async function handleLogoutClick() {
    await logout();
    setRows([]);
    setSuccessMsg("Logged out successfully.");
  }

  async function approve(id: number) {
    if (processingId !== null || !token) return;
    const durationMonths = getDurationFor(id);
    setProcessingId(id);
    setErr("");
    setSuccessMsg("");
    try {
      const r = await fetch(`${API}/api/admin/purchases/${id}/approve`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ duration_months: durationMonths }),
        credentials: "include",
      });
      const d = await r.json();
      if (r.ok) {
        setSuccessMsg(`Request #${id} approved successfully for ${durationMonths} month(s). Subscription is active.`);
        loadPurchases(token);
      } else {
        setErr(d.detail || "Could not approve request.");
      }
    } catch {
      setErr("Network error while approving request.");
    } finally {
      setProcessingId(null);
    }
  }

  async function reject(id: number) {
    if (processingId !== null || !token) return;
    const reasonPrompt = window.prompt(`Reject purchase request #${id}? Optional reason:`);
    if (reasonPrompt === null) return; // User cancelled prompt

    setProcessingId(id);
    setErr("");
    setSuccessMsg("");
    try {
      const r = await fetch(`${API}/api/admin/purchases/${id}/reject`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ reason: reasonPrompt.trim() || undefined }),
        credentials: "include",
      });
      const d = await r.json();
      if (r.ok) {
        setSuccessMsg(`Request #${id} rejected.`);
        loadPurchases(token);
      } else {
        setErr(d.detail || "Could not reject request.");
      }
    } catch {
      setErr("Network error while rejecting request.");
    } finally {
      setProcessingId(null);
    }
  }

  const isAuthorizedAdmin = !authLoading && user && user.is_admin;

  return (
    <main className="admin">
      <div className="adminHead">
        <div>
          <p className="eyebrow">NEXT AURA · CONTROL PANEL</p>
          <h1>Administrator Portal</h1>
        </div>
        <div className="headActions">
          {isAuthorizedAdmin && (
            <button className="logoutBtn" onClick={handleLogoutClick}>
              Log out
            </button>
          )}
          <a className="backLink" href="/">
            ← Back to studio
          </a>
        </div>
      </div>

      {err && <div className="errorBanner">{err}</div>}
      {successMsg && <div className="successBanner">{successMsg}</div>}

      {authLoading ? (
        <div className="skeletonWrapper">
          <div className="skeletonHeader" />
          <div className="skeletonRow" />
          <div className="skeletonRow" />
          <div className="skeletonRow" />
        </div>
      ) : !isAuthorizedAdmin ? (
        <div className="loginCard">
          <h2>Administrator Sign In</h2>
          <p className="muted">
            {user && !user.is_admin
              ? `Signed in as ${user.email} (Non-admin). Administrator credentials required.`
              : "Enter administrator credentials to manage subscription requests."}
          </p>
          <form onSubmit={handleAdminLogin} className="loginForm">
            <input
              className="adminInput"
              type="email"
              placeholder="Admin Email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
            <input
              className="adminInput"
              type="password"
              placeholder="Admin Password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
            <button className="primaryBtn" type="submit" disabled={loginSubmitting}>
              {loginSubmitting ? "Authenticating…" : "Sign In to Admin"}
            </button>
          </form>
        </div>
      ) : (
        <div className="tableWrapper">
          <div className="tableHeader">
            <h2>Purchase Requests ({rows.length})</h2>
            <button className="refreshBtn" onClick={() => loadPurchases()} disabled={loadingRows}>
              {loadingRows ? "Refreshing…" : "↻ Refresh"}
            </button>
          </div>

          <div className="table">
            {rows.map((r) => {
              const currentMonths = getDurationFor(r.id);
              const expiryPreview = calculateExpiryPreview(currentMonths);
              const expiryStatus = formatExpiryStatus(r.plan_active_until);

              return (
                <div className="row" key={r.id}>
                  <div className="rowMain">
                    <div className="rowTitle">
                      <b>#{r.id} · <span className="planName">{r.plan.toUpperCase()}</span></b>
                      <span className="priceBadge">
                        {r.amount_mmk ? `${r.amount_mmk.toLocaleString()} MMK` : r.plan === "weekly" ? "25,000 MMK" : "50,000 MMK"}
                      </span>
                    </div>

                    <small className="rowMeta">
                      User: <strong>{r.user_email || `ID #${r.user_id}`}</strong> · Submitted: {new Date(r.created_at).toLocaleString()}
                    </small>

                    {r.status === "approved" && (
                      <div className="subscriptionDetails">
                        <div className="dateInfo">
                          <span>Duration: <strong>{r.duration_months || 1} month(s)</strong></span>
                          <span>Active until: <strong>{r.plan_active_until ? new Date(r.plan_active_until).toLocaleDateString() : "Indefinite"}</strong></span>
                        </div>
                        <span className={`expiryBadge ${expiryStatus.isExpired ? "expired" : "active"}`}>
                          {expiryStatus.text}
                        </span>
                      </div>
                    )}

                    {r.status === "rejected" && r.rejection_reason && (
                      <small className="rejectReason">Reason: {r.rejection_reason}</small>
                    )}

                    {r.approved_at && (
                      <small className="auditMeta">
                        Reviewed on {new Date(r.approved_at).toLocaleString()} {r.approved_by_user_id ? `by Admin #${r.approved_by_user_id}` : ""}
                      </small>
                    )}
                  </div>

                  <div className="rowRef">
                    <span className="refLabel">Transaction Reference:</span>
                    <code className="refCode">{r.payment_reference}</code>

                    {r.status === "pending" && (
                      <div className="durationPicker">
                        <span className="durationLabel">Set Duration:</span>
                        <div className="durationControls">
                          <select
                            className="durationSelect"
                            value={currentMonths}
                            onChange={(e) => setDurationFor(r.id, parseInt(e.target.value, 10))}
                          >
                            <option value={1}>1 Month (Default)</option>
                            <option value={2}>2 Months</option>
                            <option value={3}>3 Months (Quarterly)</option>
                            <option value={6}>6 Months (Half Year)</option>
                            <option value={12}>12 Months (1 Year)</option>
                          </select>
                          <span className="expiryPreview">Expires on ~{expiryPreview}</span>
                        </div>
                      </div>
                    )}
                  </div>

                  <div className="rowActions">
                    <span className={`statusPill ${r.status}`}>{r.status}</span>
                    {r.status === "pending" && (
                      <div className="btnGroup">
                        <button
                          className="approveBtn"
                          disabled={processingId === r.id}
                          onClick={() => approve(r.id)}
                          title={`Approve subscription for ${currentMonths} month(s)`}
                        >
                          {processingId === r.id ? "…" : `Approve (${currentMonths}m)`}
                        </button>
                        <button
                          className="rejectBtn"
                          disabled={processingId === r.id}
                          onClick={() => reject(r.id)}
                        >
                          Reject
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}

            {!rows.length && !loadingRows && (
              <div className="emptyState">
                <p>No purchase requests found.</p>
              </div>
            )}
          </div>
        </div>
      )}

      <style jsx>{`
        .admin {
          min-height: 100vh;
          background: #fafafa;
          padding: 60px 8vw;
          color: #111;
          font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        }
        .eyebrow {
          font-size: 11px;
          letter-spacing: 2px;
          font-weight: 700;
          color: #666;
          margin-bottom: 6px;
        }
        .adminHead {
          display: flex;
          justify-content: space-between;
          align-items: flex-end;
          border-bottom: 1px solid #e5e5e5;
          padding-bottom: 24px;
          margin-bottom: 32px;
        }
        .admin h1 {
          font-size: 38px;
          letter-spacing: -1.5px;
          margin: 0;
          font-weight: 800;
        }
        .headActions {
          display: flex;
          align-items: center;
          gap: 16px;
        }
        .backLink {
          color: #111;
          text-decoration: none;
          font-size: 13px;
          font-weight: 600;
        }
        .backLink:hover {
          text-decoration: underline;
        }
        .logoutBtn {
          background: none;
          border: 1px solid #ddd;
          padding: 8px 14px;
          border-radius: 8px;
          font-size: 13px;
          font-weight: 600;
          cursor: pointer;
          transition: 0.15s;
        }
        .logoutBtn:hover {
          background: #eee;
        }
        .errorBanner {
          background: #fee2e2;
          color: #991b1b;
          padding: 12px 16px;
          border-radius: 8px;
          margin-bottom: 24px;
          font-size: 13px;
          font-weight: 500;
        }
        .successBanner {
          background: #dcfce7;
          color: #166534;
          padding: 12px 16px;
          border-radius: 8px;
          margin-bottom: 24px;
          font-size: 13px;
          font-weight: 500;
        }
        .loginCard {
          background: #fff;
          border: 1px solid #e5e5e5;
          border-radius: 16px;
          padding: 36px;
          max-width: 440px;
          margin: 40px auto;
          box-shadow: 0 10px 30px rgba(0, 0, 0, 0.05);
        }
        .loginCard h2 {
          font-size: 24px;
          margin: 0 0 8px;
          letter-spacing: -0.5px;
        }
        .muted {
          color: #666;
          font-size: 13px;
          line-height: 1.5;
          margin-bottom: 24px;
        }
        .loginForm {
          display: flex;
          flex-direction: column;
          gap: 14px;
        }
        .adminInput {
          width: 100%;
          padding: 12px 14px;
          border: 1px solid #ddd;
          border-radius: 8px;
          font-size: 14px;
          outline: none;
        }
        .adminInput:focus {
          border-color: #000;
        }
        .primaryBtn {
          background: #000;
          color: #fff;
          border: none;
          padding: 14px;
          border-radius: 8px;
          font-weight: 600;
          cursor: pointer;
          transition: 0.15s;
        }
        .primaryBtn:hover:not(:disabled) {
          background: #222;
        }
        .primaryBtn:disabled {
          opacity: 0.5;
        }
        .skeletonWrapper {
          background: #fff;
          border: 1px solid #e5e5e5;
          border-radius: 16px;
          padding: 24px;
          display: flex;
          flex-direction: column;
          gap: 16px;
        }
        .skeletonHeader {
          height: 32px;
          width: 240px;
          background: linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%);
          background-size: 200% 100%;
          animation: shimmer 1.5s infinite;
          border-radius: 8px;
        }
        .skeletonRow {
          height: 90px;
          background: linear-gradient(90deg, #f4f4f4 25%, #e8e8e8 50%, #f4f4f4 75%);
          background-size: 200% 100%;
          animation: shimmer 1.5s infinite;
          border-radius: 12px;
        }
        @keyframes shimmer {
          0% { background-position: 200% 0; }
          100% { background-position: -200% 0; }
        }
        .tableWrapper {
          background: #fff;
          border: 1px solid #e5e5e5;
          border-radius: 16px;
          overflow: hidden;
        }
        .tableHeader {
          padding: 20px 24px;
          display: flex;
          justify-content: space-between;
          align-items: center;
          border-bottom: 1px solid #eee;
        }
        .tableHeader h2 {
          font-size: 18px;
          margin: 0;
          font-weight: 700;
        }
        .refreshBtn {
          background: #f4f4f5;
          border: 1px solid #e4e4e7;
          padding: 6px 12px;
          border-radius: 6px;
          font-size: 12px;
          font-weight: 600;
          cursor: pointer;
        }
        .refreshBtn:hover:not(:disabled) {
          background: #e4e4e7;
        }
        .table {
          display: flex;
          flex-direction: column;
        }
        .row {
          padding: 20px 24px;
          border-bottom: 1px solid #eee;
          display: grid;
          grid-template-columns: 1.4fr 1.2fr 1fr;
          gap: 20px;
          align-items: center;
        }
        .row:last-child {
          border-bottom: none;
        }
        .rowMain {
          display: flex;
          flex-direction: column;
          gap: 6px;
        }
        .rowTitle {
          display: flex;
          align-items: center;
          gap: 8px;
        }
        .planName {
          letter-spacing: 0.5px;
        }
        .priceBadge {
          background: #f4f4f5;
          font-size: 11px;
          font-weight: 600;
          padding: 2px 6px;
          border-radius: 4px;
          color: #555;
        }
        .rowMeta {
          font-size: 12px;
          color: #777;
        }
        .subscriptionDetails {
          display: flex;
          align-items: center;
          gap: 12px;
          margin-top: 4px;
          background: #f8fafc;
          padding: 6px 10px;
          border-radius: 6px;
          border: 1px solid #f1f5f9;
        }
        .dateInfo {
          display: flex;
          flex-direction: column;
          font-size: 11px;
          color: #475569;
          gap: 2px;
        }
        .expiryBadge {
          font-size: 11px;
          font-weight: 700;
          padding: 3px 8px;
          border-radius: 4px;
        }
        .expiryBadge.active {
          background: #e0f2fe;
          color: #0369a1;
        }
        .expiryBadge.expired {
          background: #fee2e2;
          color: #b91c1c;
        }
        .rejectReason {
          color: #b91c1c;
          font-size: 11px;
          margin-top: 2px;
        }
        .auditMeta {
          font-size: 10px;
          color: #999;
        }
        .rowRef {
          display: flex;
          flex-direction: column;
          gap: 8px;
        }
        .refLabel {
          font-size: 11px;
          color: #888;
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }
        .refCode {
          font-family: monospace;
          background: #f4f4f5;
          padding: 6px 10px;
          border-radius: 6px;
          font-size: 13px;
          word-break: break-all;
          border: 1px solid #e4e4e7;
        }
        .durationPicker {
          display: flex;
          flex-direction: column;
          gap: 4px;
          margin-top: 2px;
        }
        .durationLabel {
          font-size: 11px;
          color: #666;
          font-weight: 600;
        }
        .durationControls {
          display: flex;
          align-items: center;
          gap: 8px;
        }
        .durationSelect {
          padding: 4px 8px;
          border-radius: 6px;
          border: 1px solid #ccc;
          font-size: 12px;
          background: #fff;
          outline: none;
          font-weight: 500;
        }
        .durationSelect:focus {
          border-color: #000;
        }
        .expiryPreview {
          font-size: 11px;
          color: #0284c7;
          font-weight: 500;
        }
        .rowActions {
          display: flex;
          align-items: center;
          gap: 14px;
        }
        .statusPill {
          font-size: 11px;
          text-transform: uppercase;
          padding: 4px 10px;
          border-radius: 20px;
          font-weight: 700;
          letter-spacing: 0.5px;
        }
        .statusPill.pending {
          background: #fef3c7;
          color: #92400e;
        }
        .statusPill.approved {
          background: #dcfce7;
          color: #166534;
        }
        .statusPill.rejected {
          background: #fee2e2;
          color: #991b1b;
        }
        .btnGroup {
          display: flex;
          gap: 8px;
        }
        .approveBtn {
          background: #111;
          color: #fff;
          border: none;
          border-radius: 8px;
          padding: 8px 14px;
          font-size: 13px;
          font-weight: 600;
          cursor: pointer;
        }
        .approveBtn:hover:not(:disabled) {
          background: #333;
        }
        .approveBtn:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }
        .rejectBtn {
          background: #fff;
          color: #b91c1c;
          border: 1px solid #fca5a5;
          border-radius: 8px;
          padding: 8px 12px;
          font-size: 13px;
          font-weight: 600;
          cursor: pointer;
        }
        .rejectBtn:hover:not(:disabled) {
          background: #fef2f2;
        }
        .emptyState {
          padding: 48px 24px;
          text-align: center;
          color: #888;
        }
        @media (max-width: 800px) {
          .row {
            grid-template-columns: 1fr;
            gap: 14px;
          }
          .adminHead {
            flex-direction: column;
            align-items: flex-start;
            gap: 16px;
          }
        }
      `}</style>
    </main>
  );
}
