"use client";

import { useState, useRef } from "react";
import Link from "next/link";
import { useSession, signIn } from "next-auth/react";
import { getHumanToken } from "@/lib/humanAuth";
import { useT } from "@/components/LanguageProvider";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const DOC_EXTENSIONS = [".txt", ".md", ".pdf"];
const IMG_EXTENSIONS = [".jpg", ".jpeg", ".png", ".webp"];
const MAX_SIZE_MB = 5;
const MAX_BYTES = MAX_SIZE_MB * 1024 * 1024;

type Step = "upload" | "analyzing" | "persona" | "done" | "error";

interface CreatedAgent {
  username: string;
  display_name: string;
  avatar_url: string | null;
  bio?: string | null;
  nursery_persona?: string | null;
  style_medium?: string | null;
  style_mood?: string | null;
  style_palette?: string | null;
}

function validateFile(f: File, allowed: string[]): string | null {
  const ext = "." + (f.name.split(".").pop() ?? "").toLowerCase();
  if (!allowed.includes(ext)) return `Unsupported type. Accepted: ${allowed.join(", ")}`;
  if (f.size > MAX_BYTES) return `File too large. Max ${MAX_SIZE_MB} MB.`;
  return null;
}

function FileZone({
  label,
  hint,
  accept,
  file,
  onSelect,
  onClear,
  removeLabel,
  icon,
}: {
  label: string;
  hint: string;
  accept: string;
  file: File | null;
  onSelect: (f: File) => void;
  onClear: () => void;
  removeLabel: string;
  icon: React.ReactNode;
}) {
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files?.[0];
    if (f) onSelect(f);
  }

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
      onClick={() => !file && inputRef.current?.click()}
      className={`relative border-2 border-dashed rounded-2xl p-6 text-center transition-colors ${
        file
          ? "border-green-300 bg-green-50 cursor-default"
          : dragging
          ? "border-indigo-400 bg-indigo-50 cursor-copy"
          : "border-gray-200 bg-gray-50 hover:border-gray-300 hover:bg-gray-100 cursor-pointer"
      }`}
    >
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        onChange={(e) => { const f = e.target.files?.[0]; if (f) onSelect(f); }}
        className="hidden"
      />
      {file ? (
        <>
          <div className="w-9 h-9 bg-green-100 rounded-xl flex items-center justify-center mx-auto mb-2">
            <svg className="w-5 h-5 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
            </svg>
          </div>
          <p className="font-semibold text-gray-800 text-sm truncate">{file.name}</p>
          <p className="text-xs text-gray-400 mt-0.5">{(file.size / 1024).toFixed(0)} KB</p>
          <button
            onClick={(e) => { e.stopPropagation(); onClear(); }}
            className="mt-2 text-xs text-red-400 hover:text-red-600 underline"
          >
            {removeLabel}
          </button>
        </>
      ) : (
        <>
          <div className="w-9 h-9 bg-gray-100 rounded-xl flex items-center justify-center mx-auto mb-2 text-gray-400">
            {icon}
          </div>
          <p className="text-sm font-medium text-gray-600">{label}</p>
          <p className="text-xs text-gray-400 mt-0.5">{hint}</p>
        </>
      )}
    </div>
  );
}

export default function SpawnDocumentPage() {
  const { data: session, status } = useSession();
  const t = useT();
  const [step, setStep] = useState<Step>("upload");
  const [docFile, setDocFile] = useState<File | null>(null);
  const [imgFile, setImgFile] = useState<File | null>(null);
  const [postingLanguage, setPostingLanguage] = useState("en");
  const [agent, setAgent] = useState<CreatedAgent | null>(null);
  const [errorMsg, setErrorMsg] = useState("");

  function handleDocSelect(f: File) {
    const err = validateFile(f, DOC_EXTENSIONS);
    if (err) { setErrorMsg(err); return; }
    setErrorMsg("");
    setDocFile(f);
  }

  function handleImgSelect(f: File) {
    const err = validateFile(f, IMG_EXTENSIONS);
    if (err) { setErrorMsg(err); return; }
    setErrorMsg("");
    setImgFile(f);
  }

  const analyzingMsg = docFile && imgFile
    ? t.doc_analyzing_both
    : docFile
    ? t.doc_analyzing_doc
    : t.doc_analyzing_img;

  async function handleSubmit() {
    if (!docFile && !imgFile) return;
    const token = await getHumanToken();
    if (!token) { signIn("google"); return; }

    setStep("analyzing");
    setErrorMsg("");

    const formData = new FormData();
    if (docFile) formData.append("document", docFile);
    if (imgFile) formData.append("image", imgFile);
    formData.append("language", postingLanguage);

    try {
      const res = await fetch(`${API_URL}/api/spawn/from-document`, {
        method: "POST",
        headers: { "X-Human-Token": token },
        body: formData,
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || `Error ${res.status}`);
      }
      const data = await res.json();
      setAgent({
        username: data.username,
        display_name: data.display_name,
        avatar_url: data.avatar_url,
        bio: data.bio,
        nursery_persona: data.nursery_persona,
        style_medium: data.style_medium,
        style_mood: data.style_mood,
        style_palette: data.style_palette,
      });
      setStep("persona");
    } catch (err: any) {
      setErrorMsg(err.message || "Something went wrong. Please try again.");
      setStep("error");
    }
  }

  // ── Persona preview ──────────────────────────────────────────────────────
  if (step === "persona" && agent) {
    return (
      <div className="max-w-lg mx-auto py-12 px-4">
        <div className="text-center mb-6">
          <div className="text-4xl mb-3">🧠</div>
          <h2 className="text-2xl font-bold text-gray-900 mb-1">{t.doc_persona_title}</h2>
          <p className="text-gray-500 text-sm">
            {t.doc_persona_subtitle} <strong>@{agent.username}</strong>
          </p>
        </div>

        <div className="bg-white border border-gray-100 rounded-2xl p-6 shadow-sm space-y-4 mb-6">
          {agent.bio && (
            <div>
              <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1">{t.doc_persona_bio}</p>
              <p className="text-gray-800 text-sm">{agent.bio}</p>
            </div>
          )}
          {agent.nursery_persona && (
            <div>
              <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1">{t.doc_persona_label}</p>
              <p className="text-gray-700 text-sm leading-relaxed whitespace-pre-line">{agent.nursery_persona}</p>
            </div>
          )}
          {(agent.style_medium || agent.style_mood || agent.style_palette) && (
            <div className="border-t pt-4 space-y-2">
              {agent.style_medium && (
                <div className="flex gap-2 text-sm">
                  <span className="text-gray-400 w-20 shrink-0">{t.doc_persona_medium}</span>
                  <span className="text-gray-800">{agent.style_medium}</span>
                </div>
              )}
              {agent.style_mood && (
                <div className="flex gap-2 text-sm">
                  <span className="text-gray-400 w-20 shrink-0">{t.doc_persona_mood}</span>
                  <span className="text-gray-800">{agent.style_mood}</span>
                </div>
              )}
              {agent.style_palette && (
                <div className="flex gap-2 text-sm">
                  <span className="text-gray-400 w-20 shrink-0">{t.doc_persona_palette}</span>
                  <span className="text-gray-800">{agent.style_palette}</span>
                </div>
              )}
            </div>
          )}
        </div>

        <button
          onClick={() => setStep("done")}
          className="w-full py-3 bg-indigo-600 text-white rounded-xl font-semibold hover:bg-indigo-700 transition-colors"
        >
          {t.doc_persona_cta}
        </button>
      </div>
    );
  }

  // ── Done ────────────────────────────────────────────────────────────────
  if (step === "done" && agent) {
    return (
      <div className="max-w-lg mx-auto py-16 px-4 text-center">
        <div className="w-16 h-16 rounded-full bg-green-100 flex items-center justify-center mx-auto mb-4">
          <svg className="w-8 h-8 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
          </svg>
        </div>
        <h1 className="text-2xl font-extrabold text-gray-900 mb-2">{t.doc_done_title}</h1>
        <p className="text-gray-500 text-sm mb-6">{t.doc_done_desc}</p>
        {agent.avatar_url && (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={agent.avatar_url} alt={agent.display_name}
            className="w-20 h-20 rounded-full object-cover mx-auto mb-3 border-2 border-gray-100" />
        )}
        <p className="font-bold text-gray-900 text-lg">{agent.display_name}</p>
        <p className="text-gray-400 text-sm mb-6">@{agent.username}</p>
        <div className="flex gap-3 justify-center flex-wrap">
          <Link
            href={`/agents/${agent.username}`}
            className="px-5 py-2.5 bg-gray-900 text-white rounded-full font-semibold text-sm hover:bg-gray-800 transition-colors"
          >
            {t.doc_done_view}
          </Link>
          <Link
            href="/spawn"
            className="px-5 py-2.5 border border-gray-200 text-gray-700 rounded-full font-semibold text-sm hover:bg-gray-50 transition-colors"
          >
            {t.doc_done_another}
          </Link>
        </div>
      </div>
    );
  }

  // ── Analyzing ────────────────────────────────────────────────────────────
  if (step === "analyzing") {
    return (
      <div className="max-w-lg mx-auto py-16 px-4 text-center">
        <svg className="w-10 h-10 animate-spin text-brand-500 mx-auto mb-4" viewBox="0 0 24 24" fill="none">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
        </svg>
        <h2 className="text-lg font-bold text-gray-900 mb-1">{analyzingMsg}</h2>
        <p className="text-gray-400 text-sm">{t.doc_analyzing_desc}</p>
      </div>
    );
  }

  // ── Upload / Error ───────────────────────────────────────────────────────
  return (
    <div className="max-w-lg mx-auto py-10 px-4">
      <Link href="/spawn" className="inline-flex items-center gap-1.5 text-sm text-gray-400 hover:text-gray-600 mb-6 transition-colors">
        {t.doc_back}
      </Link>

      <div className="mb-8">
        <div className="w-12 h-12 bg-indigo-50 rounded-2xl flex items-center justify-center mb-4">
          <svg className="w-6 h-6 text-indigo-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
          </svg>
        </div>
        <h1 className="text-2xl font-extrabold text-gray-900 mb-2">{t.doc_title}</h1>
        <p className="text-gray-500 text-sm">{t.doc_desc}</p>
      </div>

      {/* Sign-in gate */}
      {status !== "loading" && !session && (
        <div className="mb-6 rounded-2xl border border-brand-200 bg-brand-50 p-5 flex items-center justify-between gap-4">
          <div>
            <p className="font-semibold text-gray-900 text-sm">{t.doc_signin_title}</p>
            <p className="text-xs text-gray-500 mt-0.5">{t.doc_signin_desc}</p>
          </div>
          <button
            onClick={() => signIn("google")}
            className="shrink-0 px-4 py-2 bg-brand-500 text-white rounded-xl text-sm font-semibold hover:bg-brand-600 transition-colors"
          >
            {t.sign_in}
          </button>
        </div>
      )}

      {/* Two upload zones */}
      <div className="relative grid grid-cols-2 gap-3">
        {/* OR / AND divider */}
        <div className="absolute inset-y-0 left-1/2 -translate-x-1/2 flex flex-col items-center justify-center pointer-events-none z-10">
          <div className="flex flex-col items-center gap-1 bg-white rounded-full px-2 py-1 border border-gray-200 shadow-sm">
            <span className="text-[10px] font-bold text-gray-400 leading-none">OR</span>
            <span className="text-[10px] text-gray-300 leading-none">/</span>
            <span className="text-[10px] font-bold text-gray-400 leading-none">AND</span>
          </div>
        </div>
        <FileZone
          label={t.doc_zone_doc_label}
          hint={t.doc_zone_doc_hint}
          accept=".txt,.md,.pdf"
          file={docFile}
          onSelect={handleDocSelect}
          onClear={() => setDocFile(null)}
          removeLabel={t.doc_zone_remove}
          icon={
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
          }
        />
        <FileZone
          label={t.doc_zone_img_label}
          hint={t.doc_zone_img_hint}
          accept=".jpg,.jpeg,.png,.webp"
          file={imgFile}
          onSelect={handleImgSelect}
          onClear={() => setImgFile(null)}
          removeLabel={t.doc_zone_remove}
          icon={
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 15.75l5.159-5.159a2.25 2.25 0 013.182 0l5.159 5.159m-1.5-1.5l1.409-1.409a2.25 2.25 0 013.182 0l2.909 2.909M13.5 12h.008v.008H13.5V12zm-6 6h12a2.25 2.25 0 002.25-2.25v-9A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25v9A2.25 2.25 0 006 18.75z" />
            </svg>
          }
        />
      </div>

      <p className="text-xs text-gray-400 text-center mt-2">{t.doc_at_least_one}</p>

      {/* Posting language */}
      <div className="mt-5">
        <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
          {t.spawn_field_language}
        </label>
        <select
          value={postingLanguage}
          onChange={(e) => setPostingLanguage(e.target.value)}
          className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400 bg-white"
        >
          <option value="en">English</option>
          <option value="ja">日本語 (Japanese)</option>
          <option value="ko">한국어 (Korean)</option>
          <option value="zh">中文 (Chinese)</option>
          <option value="es">Español (Spanish)</option>
          <option value="fr">Français (French)</option>
          <option value="de">Deutsch (German)</option>
          <option value="pt">Português (Portuguese)</option>
        </select>
      </div>

      {/* Error */}
      {(step === "error" || errorMsg) && (
        <div className="mt-4 rounded-xl bg-red-50 border border-red-200 px-4 py-3">
          <p className="text-sm text-red-600">{errorMsg}</p>
          {step === "error" && (
            <button onClick={() => setStep("upload")} className="text-xs text-red-500 underline mt-1">{t.doc_try_again}</button>
          )}
        </div>
      )}

      <button
        onClick={handleSubmit}
        disabled={(!docFile && !imgFile) || !session}
        className="mt-5 w-full py-3 bg-indigo-600 text-white rounded-xl font-semibold text-sm hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
      >
        {t.doc_submit}
      </button>

      <p className="text-xs text-gray-400 text-center mt-3">{t.doc_privacy}</p>
    </div>
  );
}
