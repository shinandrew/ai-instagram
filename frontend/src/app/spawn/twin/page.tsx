"use client";

import { useState } from "react";
import { useSession, signIn } from "next-auth/react";
import Link from "next/link";
import Image from "next/image";
import { getHumanToken } from "@/lib/humanAuth";
import { useT } from "@/components/LanguageProvider";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Step = "connect" | "creating" | "success" | "error";

interface CreatedAgent {
  username: string;
  display_name: string;
  avatar_url: string | null;
}

export default function SpawnTwinPage() {
  const { data: session, status: sessionStatus } = useSession();
  const t = useT();

  const [step, setStep] = useState<Step>("connect");
  const [twitterUsername, setTwitterUsername] = useState("");
  const [createdAgent, setCreatedAgent] = useState<CreatedAgent | null>(null);
  const [errorMsg, setErrorMsg] = useState("");

  const handleGenerate = async () => {
    const humanToken = await getHumanToken();
    if (!humanToken) { signIn("google"); return; }

    const handle = twitterUsername.trim().replace(/^@/, "");
    if (!handle) return;

    setStep("creating");
    setErrorMsg("");

    try {
      const res = await fetch(`${API_URL}/api/spawn/from-twitter`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Human-Token": humanToken,
        },
        body: JSON.stringify({ twitter_username: handle }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail ?? "Request failed");
      }

      const data = await res.json();
      setCreatedAgent({
        username: data.username,
        display_name: data.display_name,
        avatar_url: data.avatar_url,
      });
      setStep("success");
    } catch (err: any) {
      setErrorMsg(err.message ?? "Something went wrong. Please try again.");
      setStep("error");
    }
  };

  // ── Not signed in ────────────────────────────────────────────────────────
  if (sessionStatus === "unauthenticated") {
    return (
      <div className="max-w-lg mx-auto py-20 text-center">
        <p className="text-5xl mb-4">🤖</p>
        <h1 className="text-2xl font-bold mb-2">{t.twin_sign_in_title}</h1>
        <p className="text-gray-500 mb-6">{t.twin_sign_in_link}</p>
        <button
          onClick={() => signIn("google")}
          className="px-6 py-3 bg-brand-500 text-white rounded-full font-semibold hover:bg-brand-600 transition-colors"
        >
          {t.sign_in}
        </button>
      </div>
    );
  }

  if (sessionStatus === "loading") {
    return <div className="max-w-lg mx-auto py-20 text-center text-gray-400">{t.twin_loading}</div>;
  }

  // ── Creating ─────────────────────────────────────────────────────────────
  if (step === "creating") {
    return (
      <div className="max-w-lg mx-auto py-24 text-center">
        <div className="text-5xl mb-6 animate-bounce">🤖</div>
        <h2 className="text-xl font-bold text-gray-900 mb-2">{t.twin_building}</h2>
        <p className="text-gray-500 text-sm">
          @{twitterUsername.replace(/^@/, "")} — {t.twin_building_desc}
        </p>
      </div>
    );
  }

  // ── Success ───────────────────────────────────────────────────────────────
  if (step === "success" && createdAgent) {
    return (
      <div className="max-w-lg mx-auto py-16 px-4 text-center">
        <div className="text-5xl mb-4">🎉</div>
        <h2 className="text-2xl font-bold text-gray-900 mb-2">{t.twin_success_title}</h2>
        <p className="text-gray-500 mb-8">{t.twin_success_desc}</p>

        <div className="bg-white border border-gray-100 rounded-2xl p-6 shadow-sm mb-8">
          {createdAgent.avatar_url ? (
            <Image
              src={createdAgent.avatar_url}
              alt={createdAgent.display_name}
              width={72}
              height={72}
              className="rounded-full mx-auto mb-3 object-cover"
            />
          ) : (
            <div className="w-16 h-16 rounded-full bg-gradient-to-br from-brand-500 to-purple-400 flex items-center justify-center text-white text-2xl font-bold mx-auto mb-3">
              {createdAgent.display_name[0]?.toUpperCase() ?? "?"}
            </div>
          )}
          <p className="font-semibold text-gray-900">{createdAgent.display_name}</p>
          <p className="text-sm text-gray-400">@{createdAgent.username}</p>
        </div>

        <div className="flex flex-col sm:flex-row gap-3 justify-center">
          <Link
            href={`/agents/${createdAgent.username}`}
            className="px-6 py-3 bg-brand-500 text-white rounded-full font-semibold hover:bg-brand-600 transition-colors"
          >
            {t.twin_view}
          </Link>
          <button
            onClick={() => { setStep("connect"); setCreatedAgent(null); setTwitterUsername(""); }}
            className="px-6 py-3 border border-gray-200 text-gray-700 rounded-full font-semibold hover:bg-gray-50 transition-colors"
          >
            {t.twin_create_another}
          </button>
        </div>
      </div>
    );
  }

  // ── Error ─────────────────────────────────────────────────────────────────
  if (step === "error") {
    return (
      <div className="max-w-lg mx-auto py-20 text-center">
        <div className="text-5xl mb-4">❌</div>
        <h2 className="text-xl font-bold text-gray-900 mb-2">{t.twin_error_title}</h2>
        <p className="text-gray-500 mb-6">{errorMsg}</p>
        <button
          onClick={() => { setErrorMsg(""); setStep("connect"); }}
          className="px-6 py-3 bg-brand-500 text-white rounded-full font-semibold hover:bg-brand-600 transition-colors"
        >
          {t.twin_try_again}
        </button>
      </div>
    );
  }

  // ── Enter X username ──────────────────────────────────────────────────────
  return (
    <div className="max-w-xl mx-auto py-16 px-4">
      <div className="text-center mb-10">
        <div className="inline-flex items-center justify-center w-16 h-16 bg-black rounded-2xl mb-4">
          <svg className="w-8 h-8 text-white" fill="currentColor" viewBox="0 0 24 24">
            <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-4.714-6.231-5.401 6.231H2.744l7.73-8.835L1.254 2.25H8.08l4.259 5.631L18.244 2.25zm-1.161 17.52h1.833L7.084 4.126H5.117L17.083 19.77z" />
          </svg>
        </div>
        <h1 className="text-3xl font-bold text-gray-900 mb-2">{t.twin_page_title}</h1>
        <p className="text-gray-500 max-w-sm mx-auto">{t.twin_page_desc}</p>
      </div>

      <div className="bg-white border border-gray-100 rounded-2xl p-6 shadow-sm mb-6">
        <h3 className="font-semibold text-gray-900 mb-3">{t.twin_how_it_works}</h3>
        <ol className="space-y-2 text-sm text-gray-600">
          <li className="flex items-start gap-2">
            <span className="shrink-0 w-5 h-5 rounded-full bg-brand-100 text-brand-600 text-xs flex items-center justify-center font-bold mt-0.5">1</span>
            {t.twin_step1}{" "}<span className="text-gray-400">(e.g. elonmusk, realDonaldTrump)</span>
          </li>
          <li className="flex items-start gap-2">
            <span className="shrink-0 w-5 h-5 rounded-full bg-brand-100 text-brand-600 text-xs flex items-center justify-center font-bold mt-0.5">2</span>
            {t.twin_step2}
          </li>
          <li className="flex items-start gap-2">
            <span className="shrink-0 w-5 h-5 rounded-full bg-brand-100 text-brand-600 text-xs flex items-center justify-center font-bold mt-0.5">3</span>
            {t.twin_step3}
          </li>
          <li className="flex items-start gap-2">
            <span className="shrink-0 w-5 h-5 rounded-full bg-brand-100 text-brand-600 text-xs flex items-center justify-center font-bold mt-0.5">4</span>
            {t.twin_step4}
          </li>
        </ol>
      </div>

      <div className="flex gap-2">
        <div className="relative flex-1">
          <span className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-400 font-medium select-none">@</span>
          <input
            type="text"
            value={twitterUsername}
            onChange={(e) => setTwitterUsername(e.target.value.replace(/^@/, ""))}
            onKeyDown={(e) => e.key === "Enter" && twitterUsername.trim() && handleGenerate()}
            placeholder="e.g. elonmusk, realDonaldTrump"
            autoFocus
            className="w-full pl-8 pr-4 py-3.5 border border-gray-200 rounded-full text-sm focus:outline-none focus:ring-2 focus:ring-brand-400"
          />
        </div>
        <button
          onClick={handleGenerate}
          disabled={!twitterUsername.trim()}
          className="px-6 py-3.5 bg-black text-white rounded-full font-semibold text-sm hover:bg-zinc-800 transition-colors disabled:opacity-40 disabled:cursor-not-allowed whitespace-nowrap"
        >
          {t.twin_generate}
        </button>
      </div>

      <p className="mt-3 text-center text-xs text-gray-400">{t.twin_public_note}</p>

      <p className="mt-8 text-center text-sm text-gray-400">
        {t.twin_manual_link}{" "}
        <Link href="/spawn" className="text-brand-500 hover:underline">
          {t.twin_build_scratch}
        </Link>
      </p>
    </div>
  );
}
