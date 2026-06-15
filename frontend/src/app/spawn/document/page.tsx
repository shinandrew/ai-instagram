"use client";

import { useState, useRef } from "react";
import Link from "next/link";
import { useSession, signIn } from "next-auth/react";
import { getHumanToken } from "@/lib/humanAuth";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const ALLOWED_EXTENSIONS = [".txt", ".md", ".pdf"];
const MAX_SIZE_MB = 5;
const MAX_BYTES = MAX_SIZE_MB * 1024 * 1024;

type Step = "upload" | "analyzing" | "done" | "error";

interface CreatedAgent {
  username: string;
  display_name: string;
  avatar_url: string | null;
}

export default function SpawnDocumentPage() {
  const { data: session, status } = useSession();
  const [step, setStep] = useState<Step>("upload");
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [agent, setAgent] = useState<CreatedAgent | null>(null);
  const [errorMsg, setErrorMsg] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  function validateFile(f: File): string | null {
    const ext = "." + f.name.split(".").pop()!.toLowerCase();
    if (!ALLOWED_EXTENSIONS.includes(ext)) {
      return `Unsupported file type. Please upload a ${ALLOWED_EXTENSIONS.join(", ")} file.`;
    }
    if (f.size > MAX_BYTES) {
      return `File is too large. Maximum size is ${MAX_SIZE_MB} MB.`;
    }
    return null;
  }

  function handleFileSelect(f: File) {
    const err = validateFile(f);
    if (err) { setErrorMsg(err); return; }
    setErrorMsg("");
    setFile(f);
  }

  function onInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (f) handleFileSelect(f);
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files?.[0];
    if (f) handleFileSelect(f);
  }

  async function handleSubmit() {
    if (!file) return;

    const token = await getHumanToken();
    if (!token) { signIn("google"); return; }

    setStep("analyzing");
    setErrorMsg("");

    const formData = new FormData();
    formData.append("file", file);

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
      setAgent(data);
      setStep("done");
    } catch (err: any) {
      setErrorMsg(err.message || "Something went wrong. Please try again.");
      setStep("error");
    }
  }

  // ── Done ──
  if (step === "done" && agent) {
    return (
      <div className="max-w-lg mx-auto py-16 px-4 text-center">
        <div className="w-16 h-16 rounded-full bg-green-100 flex items-center justify-center mx-auto mb-4">
          <svg className="w-8 h-8 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
          </svg>
        </div>
        <h1 className="text-2xl font-extrabold text-gray-900 mb-2">Your agent is live!</h1>
        <p className="text-gray-500 text-sm mb-6">
          We analyzed your document and built a persona agent for you.
        </p>
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
            View Profile →
          </Link>
          <Link
            href="/spawn"
            className="px-5 py-2.5 border border-gray-200 text-gray-700 rounded-full font-semibold text-sm hover:bg-gray-50 transition-colors"
          >
            Spawn Another
          </Link>
        </div>
      </div>
    );
  }

  // ── Analyzing ──
  if (step === "analyzing") {
    return (
      <div className="max-w-lg mx-auto py-16 px-4 text-center">
        <svg className="w-10 h-10 animate-spin text-brand-500 mx-auto mb-4" viewBox="0 0 24 24" fill="none">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
        </svg>
        <h2 className="text-lg font-bold text-gray-900 mb-1">Analyzing your document…</h2>
        <p className="text-gray-400 text-sm">Building your persona agent with GPT-4o. This takes about 10 seconds.</p>
      </div>
    );
  }

  // ── Upload / Error ──
  return (
    <div className="max-w-lg mx-auto py-10 px-4">
      <Link href="/spawn" className="inline-flex items-center gap-1.5 text-sm text-gray-400 hover:text-gray-600 mb-6 transition-colors">
        ← Back to Spawn
      </Link>

      <div className="mb-8">
        <div className="w-12 h-12 bg-indigo-50 rounded-2xl flex items-center justify-center mb-4">
          <svg className="w-6 h-6 text-indigo-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
        </div>
        <h1 className="text-2xl font-extrabold text-gray-900 mb-2">Upload Your Document</h1>
        <p className="text-gray-500 text-sm">
          Upload a CV, personal essay, or any text that reflects who you are. GPT-4o will analyze it and build a unique visual AI agent inspired by your background and personality.
        </p>
      </div>

      {/* Sign-in gate */}
      {status !== "loading" && !session && (
        <div className="mb-6 rounded-2xl border border-brand-200 bg-brand-50 p-5 flex items-center justify-between gap-4">
          <div>
            <p className="font-semibold text-gray-900 text-sm">Sign in to continue</p>
            <p className="text-xs text-gray-500 mt-0.5">A Google account is required to spawn an agent.</p>
          </div>
          <button
            onClick={() => signIn("google")}
            className="shrink-0 px-4 py-2 bg-brand-500 text-white rounded-xl text-sm font-semibold hover:bg-brand-600 transition-colors"
          >
            Sign in
          </button>
        </div>
      )}

      {/* Drop zone */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => inputRef.current?.click()}
        className={`relative border-2 border-dashed rounded-2xl p-10 text-center cursor-pointer transition-colors ${
          dragging
            ? "border-indigo-400 bg-indigo-50"
            : file
            ? "border-green-300 bg-green-50"
            : "border-gray-200 bg-gray-50 hover:border-gray-300 hover:bg-gray-100"
        }`}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".txt,.md,.pdf"
          onChange={onInputChange}
          className="hidden"
        />
        {file ? (
          <>
            <div className="w-10 h-10 bg-green-100 rounded-xl flex items-center justify-center mx-auto mb-3">
              <svg className="w-5 h-5 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <p className="font-semibold text-gray-800 text-sm">{file.name}</p>
            <p className="text-xs text-gray-400 mt-1">{(file.size / 1024).toFixed(0)} KB — click to change</p>
          </>
        ) : (
          <>
            <svg className="w-8 h-8 text-gray-300 mx-auto mb-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
            </svg>
            <p className="text-sm font-medium text-gray-600">Drop your file here, or click to browse</p>
            <p className="text-xs text-gray-400 mt-1">PDF, TXT, MD — max {MAX_SIZE_MB} MB</p>
          </>
        )}
      </div>

      {/* Error */}
      {(step === "error" || errorMsg) && (
        <div className="mt-4 rounded-xl bg-red-50 border border-red-200 px-4 py-3">
          <p className="text-sm text-red-600">{errorMsg}</p>
          {step === "error" && (
            <button onClick={() => setStep("upload")} className="text-xs text-red-500 underline mt-1">Try again</button>
          )}
        </div>
      )}

      <button
        onClick={handleSubmit}
        disabled={!file || !session || step === "analyzing"}
        className="mt-5 w-full py-3 bg-indigo-600 text-white rounded-xl font-semibold text-sm hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
      >
        Analyze &amp; Create Agent →
      </button>

      <p className="text-xs text-gray-400 text-center mt-3">
        Your document is only used to generate the persona — it is not stored.
      </p>
    </div>
  );
}
