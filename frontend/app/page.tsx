"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/AuthContext";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface QuotaState {
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

interface StylePreset {
  id: string;
  name: string;
  myanmar_name: string;
  category: string;
  description: string;
  icon: string;
  default_intensity: number;
  tags: string[];
}

interface StyleCategory {
  id: string;
  name: string;
  myanmar_name: string;
  description: string;
  icon: string;
}

const DEFAULT_CATEGORIES: StyleCategory[] = [
  { id: "character", name: "Character", myanmar_name: "ဇာတ်ကောင်", description: "Character transformations", icon: "👤" },
  { id: "horror", name: "Horror", myanmar_name: "သရဲ / ထိတ်လန့်ဖွယ်", description: "Eerie ghosts, demons & whispers", icon: "👻" },
  { id: "story", name: "Story", myanmar_name: "ဇာတ်လမ်းပြော", description: "Audiobook narration & drama", icon: "📖" },
  { id: "comedy", name: "Comedy", myanmar_name: "ဟာသ / အစီအစဉ်", description: "Cartoons, memes & radio hosts", icon: "😄" },
  { id: "cinematic", name: "Cinematic", myanmar_name: "ရုပ်ရှင် / ဇာတ်ရုံ", description: "Epic blockbuster movie trailers", icon: "🎬" },
  { id: "environment", name: "Environment", myanmar_name: "အသံဝန်းကျင်", description: "Acoustic rooms, radios & caves", icon: "📻" },
];

function getPresetEmoji(preset: StylePreset): string {
  const iconMap: Record<string, string> = {
    normal: "🎙️",
    deep: "🔊",
    funny: "😂",
    cute: "✨",
    angry: "🔥",
    old_man: "👴",
    old_woman: "👵",
    child: "👶",
    robot: "🤖",
    villain: "🦹",
    hero: "🛡️",
    narrator: "🎙️",
    ghost: "👻",
    demon: "👹",
    haunted: "🏚️",
    whisper_horror: "🤫",
    dark_horror: "🌑",
    possessed: "⚡",
    creepy: "🕷️",
    distorted_horror: "📻",
    story_narrator: "📖",
    documentary: "📜",
    dramatic: "🎭",
    emotional: "❤️",
    suspense: "⚠️",
    mystery: "🔍",
    epic: "⚔️",
    trailer: "🎬",
    comedy: "😆",
    cartoon: "⭐",
    crazy: "🤪",
    exaggerated: "📣",
    meme: "💥",
    radio_host: "📻",
    announcer: "📢",
    radio: "📻",
    telephone: "☎️",
    walkie_talkie: "📡",
    megaphone: "📢",
    cave: "⛰️",
    large_hall: "🏛️",
    small_room: "🚪",
    underwater: "🌊",
    dreamy: "☁️",
    echo: "🏔️",
  };
  return iconMap[preset.id] || "🎵";
}

export default function Home() {
  const { user, token, isPro, login, register, logout, refreshUser } = useAuth();

  const [text, setText] = useState("");
  const [audio, setAudio] = useState<File | null>(null);
  const [audioPreviewUrl, setAudioPreviewUrl] = useState<string | null>(null);
  const [prompt, setPrompt] = useState("");
  const [ultimate, setUltimate] = useState(false);
  const [cfgValue, setCfgValue] = useState(1.8);
  const [normalize, setNormalize] = useState(false);
  const [denoise, setDenoise] = useState(false);
  const [showFidelitySettings, setShowFidelitySettings] = useState(false);

  // Audio object URL lifecycle
  useEffect(() => {
    if (!audio) {
      setAudioPreviewUrl(null);
      return;
    }
    const url = URL.createObjectURL(audio);
    setAudioPreviewUrl(url);

    return () => {
      URL.revokeObjectURL(url);
    };
  }, [audio]);

  const [loading, setLoading] = useState(false);
  const [audioUrl, setAudioUrl] = useState("");
  const [generatedAudioId, setGeneratedAudioId] = useState("");
  const [generatedAudioBlob, setGeneratedAudioBlob] = useState<Blob | null>(null);

  // Voice Style State
  const [styledAudioUrl, setStyledAudioUrl] = useState("");
  const [styledAudioBlob, setStyledAudioBlob] = useState<Blob | null>(null);
  const [activeAudioTab, setActiveAudioTab] = useState<"original" | "styled">("original");

  const [styleCategories, setStyleCategories] = useState<StyleCategory[]>(DEFAULT_CATEGORIES);
  const [stylePresets, setStylePresets] = useState<StylePreset[]>([]);
  const [selectedCategory, setSelectedCategory] = useState<string>("all");
  const [selectedPresetId, setSelectedPresetId] = useState<string>("ghost");
  const [intensity, setIntensity] = useState<number>(80);
  const [styleLoading, setStyleLoading] = useState(false);
  const [styleError, setStyleError] = useState("");
  const [styleSuccessMsg, setStyleSuccessMsg] = useState("");
  const [appliedPreset, setAppliedPreset] = useState<StylePreset | null>(null);

  const [error, setError] = useState("");
  const [quota, setQuota] = useState<QuotaState | null>(null);
  const [authOpen, setAuthOpen] = useState(false);
  const [authMode, setAuthMode] = useState<"login" | "register">("register");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [authSubmitting, setAuthSubmitting] = useState(false);
  const [upgradeModalOpen, setUpgradeModalOpen] = useState(false);

  const [isDragging, setIsDragging] = useState(false);

  const effectsRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const count = useMemo(() => (text.trim() ? text.trim().split(/\s+/).length : 0), [text]);

  function handleDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const file = e.dataTransfer.files[0];
      if (file.type.startsWith("audio/") || /\.(wav|mp3|ogg|m4a|flac)$/i.test(file.name)) {
        setAudio(file);
      }
    }
  }

  async function fetchQuota(authToken = token) {
    try {
      if (authToken) {
        const r = await fetch(`${API}/api/me`, {
          headers: { Authorization: `Bearer ${authToken}` },
          credentials: "include",
        });
        if (r.ok) {
          const d: QuotaState = await r.json();
          setQuota(d);
          return;
        }
      }
      const r = await fetch(`${API}/api/voice/quota`, {
        credentials: "include",
      });
      if (r.ok) {
        const d: QuotaState = await r.json();
        setQuota(d);
      }
    } catch {
      // Ignore initial network failure
    }
  }

  async function fetchStyles() {
    try {
      const r = await fetch(`${API}/api/voice/styles`);
      if (r.ok) {
        const d = await r.json();
        if (d.categories && d.categories.length > 0) {
          setStyleCategories(d.categories);
        }
        if (d.presets && d.presets.length > 0) {
          setStylePresets(d.presets);
          if (!selectedPresetId && d.presets.length > 0) {
            setSelectedPresetId(d.presets[0].id);
          }
        }
      }
    } catch {
      // Styles fallback
    }
  }

  useEffect(() => {
    fetchQuota(token);
    fetchStyles();
  }, [token]);

  async function handleAuth(e?: React.FormEvent) {
    if (e) e.preventDefault();
    setError("");
    setAuthSubmitting(true);
    try {
      const res = authMode === "login"
        ? await login(email, password)
        : await register(email, password);

      if (res.ok) {
        setAuthOpen(false);
        setPassword("");
        await refreshUser();
        await fetchQuota();
      } else {
        setError(res.error || "Authentication failed. Please check your credentials.");
      }
    } finally {
      setAuthSubmitting(false);
    }
  }

  async function handleLogoutClick() {
    await logout();
    setQuota(null);
    fetchQuota("");
  }

  const currentPlan = (user?.plan || quota?.plan || "free").toLowerCase();
  const effectivePlan = currentPlan;
  const effectiveIsPro = isPro || Boolean(quota?.is_pro);
  const activeUntil = user?.plan_active_until || quota?.active_until;
  const maxWords = quota?.max_words || (effectiveIsPro ? 5000 : 100);
  const usedGenerations = quota?.used_generations ?? 0;
  const freeGenerationsUsed = quota?.free_generations_used ?? (user?.free_generations_used ?? 0);
  const freeRemaining = Math.max(0, 1 - freeGenerationsUsed);
  const isFreePlanExhausted = !effectiveIsPro && user !== null && freeGenerationsUsed >= 1;

  async function generate() {
    setError("");
    setAudioUrl("");
    setStyledAudioUrl("");
    setStyledAudioBlob(null);
    setAppliedPreset(null);
    setActiveAudioTab("original");

    // 1. Guest Check: Prompt Sign In / Register without calling backend or consuming quota
    if (!token || !user) {
      setAuthMode("register");
      setAuthOpen(true);
      return;
    }

    // 2. Free Quota Check: If 1 free generation is already consumed, show upgrade modal
    if (isFreePlanExhausted) {
      setUpgradeModalOpen(true);
      return;
    }

    // 3. Word Count Check
    if (count > maxWords) {
      setError(`Your current plan allows up to ${maxWords.toLocaleString()} words per generation. Your script has ${count.toLocaleString()} words.`);
      return;
    }

    // 4. Ultimate Cloning Validation
    if (ultimate) {
      if (!audio) {
        setError("Ultimate Cloning requires an uploaded reference voice audio sample. Please upload a voice sample in Step 01.");
        return;
      }
      if (!prompt.trim()) {
        setError("Ultimate Cloning requires the Reference Transcript (what the speaker says in your uploaded audio sample). Please enter the transcript in Step 01 or uncheck Ultimate Cloning.");
        return;
      }
    }

    setLoading(true);
    try {
      const f = new FormData();
      f.append("text", text);
      f.append("ultimate_cloning", String(ultimate));
      f.append("prompt_text", prompt);
      f.append("cfg_value", String(cfgValue));
      f.append("normalize", String(normalize));
      f.append("denoise", String(denoise));
      if (audio) f.append("reference_audio", audio);

      const headers: Record<string, string> = {};
      if (token) {
        headers["Authorization"] = `Bearer ${token}`;
      }

      const r = await fetch(`${API}/api/voice/generate`, {
        method: "POST",
        headers,
        body: f,
        credentials: "include",
      });

      if (!r.ok) {
        if (r.status === 401) {
          await logout();
          throw new Error("Your session has expired. Please log in again.");
        }
        if (r.status === 402) {
          setUpgradeModalOpen(true);
          const d = await r.json().catch(() => ({}));
          throw new Error(d.detail || "Your free generation has been used. Please upgrade to continue.");
        }
        const d = await r.json().catch(() => ({}));
        throw new Error(d.detail || "Voice generation failed. Please try again.");
      }

      const audioIdHeader = r.headers.get("X-Audio-Id");
      if (audioIdHeader) {
        setGeneratedAudioId(audioIdHeader);
      }

      const blob = await r.blob();
      setGeneratedAudioBlob(blob);
      setAudioUrl(URL.createObjectURL(blob));
      await fetchQuota();
      await refreshUser();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "An unexpected error occurred.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }

  async function applyStyle(presetIdToApply?: string, intensityOverride?: number) {
    const targetPresetId = presetIdToApply || selectedPresetId;
    if (!targetPresetId) return;

    setStyleError("");
    setStyleSuccessMsg("");

    const presetObj = stylePresets.find((p) => p.id === targetPresetId) || null;

    if (targetPresetId === "normal") {
      setActiveAudioTab("original");
      setStyleSuccessMsg("Switched to original natural voice.");
      return;
    }

    if (!audioUrl && !generatedAudioBlob && !generatedAudioId) {
      setStyleError("Please generate voice audio before applying a style.");
      return;
    }

    setStyleLoading(true);
    try {
      const effIntensity = intensityOverride !== undefined ? intensityOverride : intensity;

      // 1. Dedicated POST /api/voice/effects JSON endpoint if audio_id is present
      if (generatedAudioId) {
        const headers: Record<string, string> = {
          "Content-Type": "application/json",
        };
        if (token) {
          headers["Authorization"] = `Bearer ${token}`;
        }

        const r = await fetch(`${API}/api/voice/effects`, {
          method: "POST",
          headers,
          body: JSON.stringify({
            audio_id: generatedAudioId,
            preset: targetPresetId,
            intensity: effIntensity,
          }),
          credentials: "include",
        });

        if (r.ok) {
          const resData = await r.json();
          const targetUrl = resData.url?.startsWith("http") ? resData.url : `${API}${resData.url}`;
          
          // Fetch the audio blob for smooth playback and download
          const audioFetch = await fetch(targetUrl);
          const blob = await audioFetch.blob();
          const blobUrl = URL.createObjectURL(blob);

          setStyledAudioBlob(blob);
          setStyledAudioUrl(blobUrl);
          setActiveAudioTab("styled");
          setAppliedPreset(presetObj);
          setStyleSuccessMsg(
            `✓ ${presetObj?.name || targetPresetId} style applied at ${effIntensity}% intensity${
              resData.cached ? " (instant cache hit)" : resData.processing_time_ms ? ` in ${resData.processing_time_ms}ms` : ""
            }`
          );
          return;
        }
      }

      // 2. Direct audio file fallback
      const f = new FormData();
      f.append("style", targetPresetId);
      f.append("intensity", String(effIntensity / 100));

      if (generatedAudioId) {
        f.append("generated_audio_id", generatedAudioId);
      } else if (generatedAudioBlob) {
        f.append("audio_file", generatedAudioBlob, "source.wav");
      }

      const headers: Record<string, string> = {};
      if (token) {
        headers["Authorization"] = `Bearer ${token}`;
      }

      const r = await fetch(`${API}/api/voice/style`, {
        method: "POST",
        headers,
        body: f,
        credentials: "include",
      });

      if (!r.ok) {
        const errJson = await r.json().catch(() => ({}));
        throw new Error(errJson.detail || "Could not apply voice style effect.");
      }

      const isCached = r.headers.get("X-Cached") === "true";
      const procTime = r.headers.get("X-Processing-Time-Ms");
      const blob = await r.blob();
      const newUrl = URL.createObjectURL(blob);

      setStyledAudioBlob(blob);
      setStyledAudioUrl(newUrl);
      setActiveAudioTab("styled");
      setAppliedPreset(presetObj);
      setStyleSuccessMsg(
        `✓ ${presetObj?.name || targetPresetId} style applied at ${effIntensity}% intensity${
          isCached ? " (instant cache hit)" : procTime ? ` in ${procTime}ms` : ""
        }`
      );
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to process voice style.";
      setStyleError(msg);
    } finally {
      setStyleLoading(false);
    }
  }

  const filteredPresets = useMemo(() => {
    if (selectedCategory === "all") return stylePresets;
    return stylePresets.filter((p) => p.category.toLowerCase() === selectedCategory.toLowerCase());
  }, [stylePresets, selectedCategory]);

  const activeSelectedPreset = useMemo(() => {
    return stylePresets.find((p) => p.id === selectedPresetId) || null;
  }, [stylePresets, selectedPresetId]);

  function getIntensityDescriptor(val: number): string {
    if (val <= 25) return "Subtle ambient tint";
    if (val <= 60) return "Balanced natural character";
    if (val <= 85) return "Dramatic character transformation";
    return "Maximum extreme character impact";
  }

  return (
    <main>
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
          <Link href="/settings" className="navPillBtn">
            Settings & Usage
          </Link>

          {user?.is_admin && (
            <Link href="/admin" className="textBtn">
              Admin Portal
            </Link>
          )}

          {token && (user || quota?.email) ? (
            <div className="userNavSection">
              <span className="userEmail">{user?.email || quota?.email}</span>
              <span className={`planPill ${effectiveIsPro ? "proBadge" : "freeBadge"}`}>
                {effectiveIsPro ? `PRO · ${currentPlan.toUpperCase()}` : "FREE"}
              </span>
              {activeUntil && effectiveIsPro && (
                <span className="navExpiry">
                  Until {new Date(activeUntil).toLocaleDateString()}
                </span>
              )}
              <button className="textBtn" onClick={handleLogoutClick}>
                Log out
              </button>
            </div>
          ) : (
            <div className="guestNavSection">
              <span className="planPill freeBadge">GUEST · 1 FREE ON SIGN UP</span>
              <button
                className="blackBtn small"
                onClick={() => {
                  setAuthMode("login");
                  setAuthOpen(true);
                }}
              >
                Sign In
              </button>
            </div>
          )}
        </div>
      </nav>

      <section className="hero">
        <p className="eyebrow">NEXT AURA · VOICE STUDIO</p>
        <h1>
          Turn your words
          <br />
          <i>into a voice.</i>
        </h1>
        <p className="sub">Upload a voice sample, write your script, and create natural speech with VoxCPM.</p>
      </section>

      {/* Main Studio Grid (Reference Voice + Script Generation) */}
      <section className="studio">
        {/* Step 01: Reference Voice */}
        <div className="stepCard">
          <div className="step">01</div>
          <h2>Reference voice</h2>
          <p className="muted">Optional for standard generation. Required for Ultimate Cloning.</p>
          {!audio ? (
            <div
              className={`upload ${isDragging ? "uploadDragging" : ""}`}
              onClick={() => fileRef.current?.click()}
              onDragOver={(e) => {
                e.preventDefault();
                setIsDragging(true);
              }}
              onDragLeave={() => setIsDragging(false)}
              onDrop={handleDrop}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  fileRef.current?.click();
                }
              }}
            >
              <input
                ref={fileRef}
                type="file"
                accept="audio/*,.wav,.mp3,.ogg,.m4a,.flac"
                hidden
                onChange={(e) => setAudio(e.target.files?.[0] || null)}
              />
              <div className="uploadIcon">↑</div>
              <b>Upload audio sample</b>
              <span>Drag & drop or click to upload WAV, MP3, OGG, or M4A (up to 12 MB)</span>
            </div>
          ) : (
            <div
              className={`uploadedAudioCard ${isDragging ? "uploadDragging" : ""}`}
              onDragOver={(e) => {
                e.preventDefault();
                setIsDragging(true);
              }}
              onDragLeave={() => setIsDragging(false)}
              onDrop={handleDrop}
            >
              <input
                ref={fileRef}
                type="file"
                accept="audio/*,.wav,.mp3,.ogg,.m4a,.flac"
                hidden
                onChange={(e) => setAudio(e.target.files?.[0] || null)}
              />
              <div className="uploadedAudioHeader">
                <div className="uploadedAudioInfo">
                  <span className="uploadedAudioLabel">Reference Voice Sample</span>
                  <b className="uploadedAudioName" title={audio.name}>{audio.name}</b>
                  <span className="uploadedAudioMeta">
                    {(audio.size / (1024 * 1024)).toFixed(2)} MB · Ready
                  </span>
                </div>
                <span className="uploadedAudioBadge">Uploaded</span>
              </div>

              {audioPreviewUrl && (
                <div className="uploadedAudioPlayerWrapper" onClick={(e) => e.stopPropagation()}>
                  <audio
                    controls
                    src={audioPreviewUrl}
                    className="uploadedAudioPlayer"
                    preload="metadata"
                  />
                </div>
              )}

              <div className="uploadedAudioActions">
                <button
                  type="button"
                  className="audioActionBtn"
                  onClick={(e) => {
                    e.stopPropagation();
                    fileRef.current?.click();
                  }}
                >
                  ⇄ Replace audio
                </button>
                <button
                  type="button"
                  className="audioRemoveBtn"
                  onClick={(e) => {
                    e.stopPropagation();
                    setAudio(null);
                    if (fileRef.current) fileRef.current.value = "";
                  }}
                >
                  ✕ Remove audio
                </button>
              </div>
            </div>
          )}

          <label className="check">
            <input type="checkbox" checked={ultimate} onChange={(e) => setUltimate(e.target.checked)} />
            <span>
              <b>Ultimate Cloning (Strict 1:1 Voice Match)</b>
              <small>Phonetically lock the reference voice for identical speaker replication</small>
            </span>
          </label>

          {ultimate && (
            <div className="promptWrapper" style={{ marginTop: "8px" }}>
              <input
                className="input"
                placeholder="Reference transcript (exact words spoken in audio sample)"
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
              />
              <span className="fidelityHint">
                Providing the exact spoken transcript guarantees 100% phonetic and timbre alignment with the source voice.
              </span>
            </div>
          )}

          {/* Collapsible Voice Match Fidelity Settings */}
          <div className="fidelitySettingsBox" style={{ marginTop: "12px" }}>
            <button
              type="button"
              className="fidelityToggleBtn"
              onClick={() => setShowFidelitySettings(!showFidelitySettings)}
            >
              <span>⚙️ Voice Fidelity & Match Settings</span>
              <span>{showFidelitySettings ? "▲ Hide" : "▼ Fine-tune"}</span>
            </button>

            {showFidelitySettings && (
              <div className="fidelityControlsPanel">
                <div className="fidelityOptionRow">
                  <label className="check small">
                    <input
                      type="checkbox"
                      checked={denoise}
                      onChange={(e) => setDenoise(e.target.checked)}
                    />
                    <span>
                      <b>ZipEnhancer Denoise Filter</b>
                      <small>Off by default. Keep disabled to preserve natural breath texture and vocal harmonics.</small>
                    </span>
                  </label>
                </div>

                <div className="fidelityOptionRow">
                  <label className="check small">
                    <input
                      type="checkbox"
                      checked={normalize}
                      onChange={(e) => setNormalize(e.target.checked)}
                    />
                    <span>
                      <b>Input Normalization</b>
                      <small>Off by default. Keep disabled to preserve natural dynamic range and speech volume.</small>
                    </span>
                  </label>
                </div>

                <div className="fidelitySliderRow">
                  <div className="fidelitySliderHeader">
                    <span className="fidelitySliderTitle">Guidance Scale (CFG): {cfgValue.toFixed(1)}</span>
                    <span className="fidelitySliderDesc">
                      {cfgValue <= 1.8 ? "High Speaker Fidelity (Recommended)" : "Higher text adherence"}
                    </span>
                  </div>
                  <input
                    type="range"
                    min="1.0"
                    max="3.0"
                    step="0.1"
                    value={cfgValue}
                    onChange={(e) => setCfgValue(parseFloat(e.target.value))}
                    className="customSlider"
                  />
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Step 02: Your Script & Synthesis Output */}
        <div className="stepCard mainCard">
          <div className="step">02</div>
          <div className="scriptHead">
            <div>
              <h2>Your script</h2>
              <p className="muted">
                {effectiveIsPro
                  ? `Maximum ${maxWords.toLocaleString()} words on your Pro plan.`
                  : "100 words maximum on Free tier."}
              </p>
            </div>
            <span className={count > maxWords ? "counter bad" : "counter"}>
              {count.toLocaleString()} / {maxWords.toLocaleString()} words
            </span>
          </div>

          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Type what you want the voice to say..."
          />

          <div className="generateRow">
            <span className="usage">
              {!user
                ? "Guest Mode · 1 Free generation (up to 100 words) available on registration"
                : effectivePlan === "unlimited"
                ? "Unlimited generations"
                : effectivePlan === "weekly"
                ? `${usedGenerations} / 6 generations used this week`
                : `Free Generation: ${freeGenerationsUsed} / 1 · Remaining: ${freeRemaining} / 1`}
            </span>
            <button
              className="blackBtn"
              disabled={loading || !text.trim() || count > maxWords}
              onClick={generate}
            >
              {loading
                ? "Synthesizing voice…"
                : isFreePlanExhausted
                ? "Upgrade to Pro →"
                : !user
                ? "Sign in to Generate →"
                : "Generate voice →"}
            </button>
          </div>

          {error && <div className="error">{error}</div>}

          {/* Original Generated Audio Output Box (Inside Step 02) */}
          {audioUrl && (
            <div className="originalOutputBox">
              <div className="originalOutputHeader">
                <div>
                  <span className="outputBadge">ORIGINAL SYNTHESIS · VOXCPM</span>
                  <h4>Generated Voice Audio</h4>
                </div>
                <a
                  href={audioUrl}
                  download="next-aura-voice-original.wav"
                  className="downloadPill"
                >
                  ↓ Download Original WAV
                </a>
              </div>
              <audio key={audioUrl} controls src={audioUrl} className="originalAudioPlayer" />
              <div className="effectsPromptRow">
                <span>✦ Want to transform this into characters, horror, cinematic or environmental scenes?</span>
                <button
                  type="button"
                  className="jumpToEffectsBtn"
                  onClick={() => {
                    effectsRef.current?.scrollIntoView({ behavior: "smooth" });
                  }}
                >
                  Explore Voice Effects Below ↓
                </button>
              </div>
            </div>
          )}
        </div>
      </section>

      {/* Standalone Premium Voice Effects Panel (Separate Full-Width Box) */}
      {audioUrl && (
        <section className="voiceEffectsSection" ref={effectsRef}>
          <div className="voiceEffectsContainer">
            {/* Header */}
            <div className="voiceEffectsHeader">
              <div className="voiceEffectsTitleGroup">
                <span className="eyebrow">NEXT AURA · CHARACTER ENGINE</span>
                <h2>VOICE EFFECTS</h2>
                <p className="voiceEffectsSubtitle">
                  Transform your generated voice into different characters, moods and scenes.
                </p>
              </div>
              <div className="voiceEffectsBadge">
                <span>⚡ CPU DSP ENGINE</span>
                <small>Zero TTS Re-generation · Instant</small>
              </div>
            </div>

            {/* Top Dual Audio Player & Comparison Bar */}
            <div className="voiceEffectsPlayerCard">
              <div className="dualTabs">
                <button
                  type="button"
                  className={`dualTab ${activeAudioTab === "original" ? "active" : ""}`}
                  onClick={() => setActiveAudioTab("original")}
                >
                  <span>🎙️ Original Voice</span>
                  <span className="tabBadge">VOXCPM</span>
                </button>
                <button
                  type="button"
                  className={`dualTab ${activeAudioTab === "styled" ? "active" : ""}`}
                  onClick={() => {
                    if (styledAudioUrl) {
                      setActiveAudioTab("styled");
                    } else if (selectedPresetId) {
                      applyStyle(selectedPresetId);
                    }
                  }}
                >
                  <span>
                    {appliedPreset ? `✨ Styled: ${appliedPreset.name}` : "✨ Styled Character Voice"}
                  </span>
                  {appliedPreset ? (
                    <span className="tabBadge activeBadge">{appliedPreset.category.toUpperCase()}</span>
                  ) : (
                    <span className="tabBadge">PREVIEW</span>
                  )}
                </button>
              </div>

              <div className="activePlayerSection">
                <div className="playerMetaBar">
                  <div className="playerTrackInfo">
                    <b>
                      {activeAudioTab === "original"
                        ? "Original Synthesized Voice (VoxCPM Clean)"
                        : appliedPreset
                        ? `Character Effect: ${appliedPreset.name} (${appliedPreset.myanmar_name}) · ${intensity}% Intensity`
                        : "Styled Voice Preview"}
                    </b>
                    <span className="playerFormatTag">16-bit PCM WAV · 24 kHz</span>
                  </div>

                  <div className="playerControlsRight">
                    {styledAudioUrl && (
                      <button
                        type="button"
                        className="compareToggleBtn"
                        onClick={() => setActiveAudioTab(activeAudioTab === "original" ? "styled" : "original")}
                      >
                        ⇄ Switch to {activeAudioTab === "original" ? "Styled Voice" : "Original Voice"}
                      </button>
                    )}
                  </div>
                </div>

                <div className="audioPlayerWrapper">
                  {activeAudioTab === "original" ? (
                    <audio key="main-orig-player" controls src={audioUrl} className="primaryAudioEl" />
                  ) : (
                    <audio
                      key={styledAudioUrl || "main-styled-player"}
                      controls
                      src={styledAudioUrl || audioUrl}
                      autoPlay={Boolean(styledAudioUrl)}
                      className="primaryAudioEl"
                    />
                  )}
                </div>

                <div className="playerFooterRow">
                  <div className="playerDownloads">
                    {activeAudioTab === "original" ? (
                      <a href={audioUrl} download="next-aura-voice-original.wav" className="downloadBtn">
                        ↓ Download Original Audio (WAV)
                      </a>
                    ) : styledAudioUrl ? (
                      <a
                        href={styledAudioUrl}
                        download={`next-aura-${appliedPreset?.id || "styled"}.wav`}
                        className="downloadBtn highlight"
                      >
                        ↓ Download Styled Audio ({appliedPreset?.name || "Effect"})
                      </a>
                    ) : (
                      <span className="muted">Select a preset below and click &quot;Apply Effect&quot; to transform this voice.</span>
                    )}
                  </div>

                  {styleSuccessMsg && <span className="statusSuccessPill">{styleSuccessMsg}</span>}
                  {styleError && <span className="statusErrorPill">{styleError}</span>}
                </div>
              </div>
            </div>

            {/* Presets Explorer & Controls */}
            <div className="presetsExplorer">
              {/* Category Filter Tabs */}
              <div className="categoryFilterRow">
                <span className="categoryFilterLabel">Categories:</span>
                <div className="categoryTabsScroll">
                  <button
                    type="button"
                    className={`categoryFilterBtn ${selectedCategory === "all" ? "active" : ""}`}
                    onClick={() => setSelectedCategory("all")}
                  >
                    All Styles ({stylePresets.length})
                  </button>
                  {styleCategories.map((cat) => {
                    const catCount = stylePresets.filter((p) => p.category.toLowerCase() === cat.id.toLowerCase()).length;
                    return (
                      <button
                        key={cat.id}
                        type="button"
                        className={`categoryFilterBtn ${selectedCategory === cat.id ? "active" : ""}`}
                        onClick={() => setSelectedCategory(cat.id)}
                      >
                        {cat.icon} {cat.name} ({catCount})
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Preset Cards Grid */}
              <div className="effectsGrid">
                {filteredPresets.map((preset) => {
                  const isSelected = selectedPresetId === preset.id;
                  const isApplied = appliedPreset?.id === preset.id;
                  return (
                    <div
                      key={preset.id}
                      className={`effectCard ${isSelected ? "selected" : ""} ${isApplied ? "applied" : ""}`}
                      onClick={() => {
                        setSelectedPresetId(preset.id);
                        setIntensity(Math.round(preset.default_intensity * 100));
                      }}
                    >
                      <div className="effectCardTop">
                        <span className="effectEmoji">{getPresetEmoji(preset)}</span>
                        <span className={`effectBadge ${isApplied ? "appliedBadge" : ""}`}>
                          {isApplied ? "ACTIVE" : preset.category.toUpperCase()}
                        </span>
                      </div>
                      <div className="effectTitle">{preset.name}</div>
                      <div className="effectMyanmar">{preset.myanmar_name}</div>
                      <p className="effectDescription">{preset.description}</p>
                    </div>
                  );
                })}
              </div>

              {/* Selected Preset Action & Intensity Bar */}
              {activeSelectedPreset && (
                <div className="effectConfigPanel">
                  <div className="configLeft">
                    <div className="selectedEffectInfo">
                      <span className="selectedEmoji">{getPresetEmoji(activeSelectedPreset)}</span>
                      <div>
                        <div className="selectedEffectName">
                          <b>{activeSelectedPreset.name}</b>
                          <span>{activeSelectedPreset.myanmar_name}</span>
                        </div>
                        <p className="selectedEffectDesc">{activeSelectedPreset.description}</p>
                      </div>
                    </div>
                  </div>

                  <div className="configMiddle">
                    <div className="intensityControl">
                      <div className="intensityHeader">
                        <span className="intensityTitle">Intensity: {intensity}%</span>
                        <span className="intensityHint">{getIntensityDescriptor(intensity)}</span>
                      </div>
                      <input
                        type="range"
                        min="5"
                        max="100"
                        step="5"
                        value={intensity}
                        onChange={(e) => setIntensity(Number(e.target.value))}
                        className="customSlider"
                      />
                    </div>
                  </div>

                  <div className="configRight">
                    <button
                      type="button"
                      className="applyEffectBtn"
                      disabled={styleLoading || !audioUrl}
                      onClick={() => applyStyle(activeSelectedPreset.id, intensity)}
                    >
                      {styleLoading ? (
                        <>
                          <span className="spinner" />
                          <span>Applying {activeSelectedPreset.name}…</span>
                        </>
                      ) : (
                        `Apply ${activeSelectedPreset.name} (${intensity}%) →`
                      )}
                    </button>

                    {styledAudioUrl && (
                      <button
                        type="button"
                        className="resetBtn"
                        onClick={() => {
                          setActiveAudioTab("original");
                          setStyleSuccessMsg("Reset audio player to original VoxCPM voice.");
                        }}
                      >
                        ↺ Reset to Original
                      </button>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        </section>
      )}

      {/* Auth Modal */}
      {authOpen && (
        <div className="modalBack">
          <div className="modal">
            <button className="close" onClick={() => setAuthOpen(false)}>
              ×
            </button>
            <p className="eyebrow">NEXT AURA ACCOUNT</p>
            <h2>{authMode === "login" ? "Welcome back." : "Create your free account."}</h2>
            <p className="muted">
              {authMode === "login"
                ? "Sign in to access your Next Aura studio account and quota."
                : "Registering gives you 1 Free voice generation (up to 100 words) with VoxCPM voice cloning."}
            </p>
            <form onSubmit={handleAuth}>
              <input
                className="input"
                type="email"
                placeholder="Email address"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
              <input
                className="input"
                type="password"
                placeholder="Password (minimum 8 characters)"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
              <button className="blackBtn full" type="submit" disabled={authSubmitting}>
                {authSubmitting
                  ? "Processing…"
                  : authMode === "login"
                  ? "Login"
                  : "Create free account & continue"}
              </button>
            </form>
            <button
              className="switch"
              onClick={() => setAuthMode(authMode === "login" ? "register" : "login")}
            >
              {authMode === "login" ? "New here? Create a free account" : "Already have an account? Login"}
            </button>
          </div>
        </div>
      )}

      {/* Upgrade Modal when Free Generation is Exhausted */}
      {upgradeModalOpen && (
        <div className="modalBack">
          <div className="modal upgradeModal">
            <button className="close" onClick={() => setUpgradeModalOpen(false)}>
              ×
            </button>
            <p className="eyebrow">FREE GENERATION USED</p>
            <h2>Upgrade to Pro</h2>
            <p className="muted">
              You have completed your 1 free generation. Upgrade to a premium plan for higher word limits (5,000 words) and more generation capacity.
            </p>

            <div className="upgradePlanOptions">
              <div className="upgradePlanCard">
                <span className="featuredBadge">POPULAR</span>
                <h3>Weekly Pro</h3>
                <strong className="planPrice">25,000 MMK</strong>
                <p className="planDesc">6 generations / week · 5,000 words per script · Ultimate Cloning</p>
              </div>

              <div className="upgradePlanCard">
                <h3>Unlimited Pro</h3>
                <strong className="planPrice">50,000 MMK</strong>
                <p className="planDesc">Unlimited generations · 5,000 words per script · Priority synthesis</p>
              </div>
            </div>

            <div className="upgradeActions">
              <Link href="/settings" className="blackBtn full" style={{ textAlign: "center", textDecoration: "none" }}>
                View Plans & Upgrade in Settings →
              </Link>
              <button className="outlineBtn" style={{ marginTop: "10px" }} onClick={() => setUpgradeModalOpen(false)}>
                Dismiss
              </button>
            </div>
          </div>
        </div>
      )}

      <style jsx>{`
        .upgradeModal {
          max-width: 480px;
        }
        .upgradePlanOptions {
          display: grid;
          gap: 12px;
          margin: 20px 0;
        }
        .upgradePlanCard {
          border: 1px solid #ddd;
          border-radius: 12px;
          padding: 16px;
          position: relative;
          background: #fafafa;
        }
        .upgradePlanCard h3 {
          margin: 0 0 4px;
          font-size: 16px;
        }
        .planPrice {
          font-size: 18px;
          display: block;
          margin-bottom: 4px;
        }
        .planDesc {
          font-size: 12px;
          color: #666;
          margin: 0;
        }
        .featuredBadge {
          position: absolute;
          top: 12px;
          right: 12px;
          background: #000;
          color: #fff;
          font-size: 9px;
          font-weight: 800;
          padding: 3px 7px;
          border-radius: 4px;
        }
        .upgradeActions {
          display: flex;
          flex-direction: column;
        }
      `}</style>
    </main>
  );
}
