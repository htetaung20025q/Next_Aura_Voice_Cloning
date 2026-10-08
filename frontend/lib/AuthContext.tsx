"use client";

import React, { createContext, useContext, useEffect, useState, useCallback } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface UserProfile {
  id: number;
  email: string;
  plan: string;
  is_admin: boolean;
  is_pro: boolean;
  subscription_active: boolean;
  plan_active_from?: string | null;
  plan_active_until?: string | null;
  credits?: number | null;
  token_usage?: number;
  free_generations_used?: number;
  free_generations_limit?: number;
  created_at: string;
}

interface AuthContextType {
  user: UserProfile | null;
  token: string;
  isLoading: boolean;
  isPro: boolean;
  login: (email: string, pass: string) => Promise<{ ok: boolean; error?: string }>;
  register: (email: string, pass: string) => Promise<{ ok: boolean; error?: string }>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<UserProfile | null>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string>("");
  const [user, setUser] = useState<UserProfile | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  const refreshUser = useCallback(async (authToken?: string): Promise<UserProfile | null> => {
    const t = authToken !== undefined ? authToken : (typeof window !== "undefined" ? localStorage.getItem("na_token") || "" : "");
    if (!t) {
      setUser(null);
      return null;
    }

    try {
      const res = await fetch(`${API}/api/auth/me`, {
        headers: {
          Authorization: `Bearer ${t}`,
        },
        credentials: "include",
      });

      if (res.ok) {
        const data: UserProfile = await res.json();
        setUser(data);
        return data;
      } else if (res.status === 401 || res.status === 403) {
        // Expired or invalid token -> clear auth state
        if (typeof window !== "undefined") {
          localStorage.removeItem("na_token");
        }
        setToken("");
        setUser(null);
        return null;
      }
    } catch {
      // Network or offline error -> preserve local state for now
    }
    return null;
  }, []);

  useEffect(() => {
    const t = localStorage.getItem("na_token") || "";
    setToken(t);
    if (t) {
      refreshUser(t).finally(() => setIsLoading(false));
    } else {
      setIsLoading(false);
    }
  }, [refreshUser]);

  const login = async (emailInput: string, passwordInput: string): Promise<{ ok: boolean; error?: string }> => {
    try {
      const res = await fetch(`${API}/api/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: emailInput.trim(),
          password: passwordInput,
        }),
        credentials: "include",
      });

      const data = await res.json();
      if (!res.ok) {
        return { ok: false, error: data.detail || "Invalid email or password." };
      }

      const receivedToken = data.token;
      if (typeof window !== "undefined") {
        localStorage.setItem("na_token", receivedToken);
      }
      setToken(receivedToken);
      setUser(data.user);
      return { ok: true };
    } catch {
      return { ok: false, error: "Unable to connect to authentication service." };
    }
  };

  const register = async (emailInput: string, passwordInput: string): Promise<{ ok: boolean; error?: string }> => {
    try {
      const res = await fetch(`${API}/api/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: emailInput.trim(),
          password: passwordInput,
        }),
        credentials: "include",
      });

      const data = await res.json();
      if (!res.ok) {
        return { ok: false, error: data.detail || "Registration failed. Please check password requirements." };
      }

      const receivedToken = data.token;
      if (typeof window !== "undefined") {
        localStorage.setItem("na_token", receivedToken);
      }
      setToken(receivedToken);
      setUser(data.user);
      return { ok: true };
    } catch {
      return { ok: false, error: "Unable to connect to authentication service." };
    }
  };

  const logout = async (): Promise<void> => {
    try {
      await fetch(`${API}/api/auth/logout`, {
        method: "POST",
        credentials: "include",
      });
    } catch {
      // Ignore network error on logout
    } finally {
      if (typeof window !== "undefined") {
        localStorage.removeItem("na_token");
      }
      setToken("");
      setUser(null);
    }
  };

  const isPro = Boolean(user && user.is_pro);

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isLoading,
        isPro,
        login,
        register,
        logout,
        refreshUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
