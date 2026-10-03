"use client";

import { useEffect, useMemo, useRef, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const plans = [
  { id: "free", name: "Free", price: "0 MMK", words: "500 words", uses: "2 times / week", note: "No account required" },
  { id: "weekly", name: "Weekly", price: "25,000 MMK", words: "5,000 words", uses: "6 times / week", note: "Login required" },
  { id: "unlimited", name: "Unlimited", price: "50,000 MMK", words: "5,000 words", uses: "Unlimited", note: "Login required" },
];

export default function Home() {
  const [text, setText] = useState(""); const [audio, setAudio] = useState<File | null>(null); const [prompt, setPrompt] = useState("");
  const [ultimate, setUltimate] = useState(false); const [loading, setLoading] = useState(false); const [audioUrl, setAudioUrl] = useState(""); const [error, setError] = useState("");
  const [token, setToken] = useState(""); const [me, setMe] = useState<any>(null); const [authOpen, setAuthOpen] = useState(false); const [authMode, setAuthMode] = useState<"login"|"register">("login");
  const [email, setEmail] = useState(""); const [password, setPassword] = useState(""); const [purchasePlan, setPurchasePlan] = useState<string | null>(null); const [paymentRef, setPaymentRef] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const count = useMemo(() => text.trim() ? text.trim().split(/\s+/).length : 0, [text]);

  async function refreshMe(t = token) { if (!t) return; const r = await fetch(`${API}/api/me`, { headers: { Authorization: `Bearer ${t}` } }); if (r.ok) setMe(await r.json()); }
  useEffect(() => { const t = localStorage.getItem("na_token") || ""; setToken(t); if (t) refreshMe(t); }, []);
  function saveToken(t:string) { localStorage.setItem("na_token", t); setToken(t); refreshMe(t); }

  async function auth() {
    setError(""); const r = await fetch(`${API}/api/auth/${authMode}`, { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({email,password}) });
    const d = await r.json(); if (!r.ok) return setError(d.detail || "Authentication failed."); saveToken(d.token); setAuthOpen(false); setPassword("");
  }
  async function generate() {
    setError(""); setAudioUrl(""); setLoading(true);
    try { const f = new FormData(); f.append("text", text); f.append("ultimate_cloning", String(ultimate)); f.append("prompt_text", prompt); if (audio) f.append("reference_audio", audio);
      const r = await fetch(`${API}/api/voice/generate`, { method:"POST", headers: token ? {Authorization:`Bearer ${token}`} : {}, body:f });
      if (!r.ok) { const d=await r.json().catch(()=>({})); throw new Error(d.detail || "Generation failed."); }
      const blob = await r.blob(); setAudioUrl(URL.createObjectURL(blob)); await refreshMe();
    } catch(e:any) { setError(e.message); } finally { setLoading(false); }
  }
  function choosePlan(id:string) { if (id === "free") return; if (!token) { setPurchasePlan(id); setAuthMode("register"); setAuthOpen(true); } else setPurchasePlan(id); }
  async function submitPurchase() { const r=await fetch(`${API}/api/purchases`,{method:"POST",headers:{"Content-Type":"application/json",Authorization:`Bearer ${token}`},body:JSON.stringify({plan:purchasePlan,payment_reference:paymentRef})}); const d=await r.json(); if(!r.ok) return setError(d.detail||"Could not submit purchase."); setPurchasePlan(null); setPaymentRef(""); alert("Purchase request submitted. Admin approval is required."); }

  const maxWords = me?.max_words || 500;
  return <main>
    <nav className="nav"><div className="brand"><span className="mark">N</span><div><b>Next Aura</b><small>VOICE STUDIO</small></div></div><div className="navActions">{me ? <><span className="planPill">{me.plan}</span><button className="textBtn" onClick={()=>{localStorage.removeItem("na_token");setToken("");setMe(null)}}>Log out</button></> : <button className="blackBtn small" onClick={()=>{setAuthMode("login");setAuthOpen(true)}}>Login</button>}</div></nav>
    <section className="hero"><p className="eyebrow">NEXT AURA · VOICE STUDIO</p><h1>Turn your words<br/><i>into a voice.</i></h1><p className="sub">Upload a voice sample, write your script, and create natural speech with VoxCPM.</p></section>
    <section className="studio">
      <div className="stepCard"><div className="step">01</div><h2>Reference voice</h2><p className="muted">Optional for standard generation. Required for Ultimate Cloning.</p><div className="upload" onClick={()=>fileRef.current?.click()}><input ref={fileRef} type="file" accept="audio/*" hidden onChange={e=>setAudio(e.target.files?.[0]||null)}/><div className="uploadIcon">↑</div><b>{audio ? audio.name : "Upload audio sample"}</b><span>{audio ? "Ready to use" : "WAV, MP3 or M4A"}</span></div><label className="check"><input type="checkbox" checked={ultimate} onChange={e=>setUltimate(e.target.checked)}/><span><b>Ultimate Cloning</b><small>Use the reference voice more closely</small></span></label>{ultimate && <input className="input" placeholder="Reference transcript" value={prompt} onChange={e=>setPrompt(e.target.value)}/>}</div>
      <div className="stepCard mainCard"><div className="step">02</div><div className="scriptHead"><div><h2>Your script</h2><p className="muted">Maximum {maxWords.toLocaleString()} words on your current plan.</p></div><span className={count>maxWords?"counter bad":"counter"}>{count.toLocaleString()} / {maxWords.toLocaleString()}</span></div><textarea value={text} onChange={e=>setText(e.target.value)} placeholder="Type what you want the voice to say..."/><div className="generateRow"><span className="usage">{me ? `${me.used_generations}${me.weekly_generations===null?"":" / "+me.weekly_generations} generations this week` : "Free · 2 generations this week"}</span><button className="blackBtn" disabled={loading||!text.trim()||count>maxWords} onClick={generate}>{loading?"Generating…":"Generate voice →"}</button></div>{error&&<div className="error">{error}</div>}{audioUrl&&<div className="result"><b>Generated voice</b><audio controls src={audioUrl}/><a href={audioUrl} download="next-aura-voice.mp3">Download audio</a></div>}</div>
    </section>
    <section className="pricing"><div className="sectionIntro"><p className="eyebrow">SIMPLE PLANS</p><h2>Choose your voice plan.</h2><p>Start free. Upgrade only when you need more.</p></div><div className="plans">{plans.map(p=><div className={`plan ${p.id==='weekly'?"featured":""}`} key={p.id}><span className="planTag">{p.id==='weekly'?"MOST POPULAR":""}</span><h3>{p.name}</h3><strong>{p.price}</strong><ul><li>{p.words}</li><li>{p.uses}</li><li>{p.note}</li></ul>{p.id==='free'?<button className="outlineBtn" onClick={()=>window.scrollTo({top:0,behavior:"smooth"})}>Use Free</button>:<button className="blackBtn full" onClick={()=>choosePlan(p.id)}>Get {p.name}</button>}</div>)}</div></section>
    {authOpen&&<div className="modalBack"><div className="modal"><button className="close" onClick={()=>setAuthOpen(false)}>×</button><p className="eyebrow">NEXT AURA ACCOUNT</p><h2>{authMode==='login'?"Welcome back.":"Create your account."}</h2><p className="muted">{authMode==='login'?"Login to use premium plans.":"An account is required before purchasing a premium plan."}</p><input className="input" placeholder="Email" value={email} onChange={e=>setEmail(e.target.value)}/><input className="input" type="password" placeholder="Password" value={password} onChange={e=>setPassword(e.target.value)}/><button className="blackBtn full" onClick={auth}>{authMode==='login'?"Login":"Create account"}</button><button className="switch" onClick={()=>setAuthMode(authMode==='login'?"register":"login")}>{authMode==='login'?"Create an account":"Already have an account? Login"}</button></div></div>}
    {purchasePlan&&token&&<div className="modalBack"><div className="modal"><button className="close" onClick={()=>setPurchasePlan(null)}>×</button><p className="eyebrow">PREMIUM REQUEST</p><h2>{purchasePlan==='weekly'?"25,000 MMK · Weekly":"50,000 MMK · Unlimited"}</h2><p className="muted">Complete your payment through your chosen method, then enter the payment reference below. Admin will activate your plan after verification.</p><input className="input" placeholder="Payment reference / transaction ID" value={paymentRef} onChange={e=>setPaymentRef(e.target.value)}/><button className="blackBtn full" disabled={!paymentRef.trim()} onClick={submitPurchase}>Submit purchase</button></div></div>}
  </main>
}
