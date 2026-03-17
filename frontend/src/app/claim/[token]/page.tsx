"use client";

import { use, useState } from "react";
import { api, ClaimTokenInfo } from "@/lib/api";
import useSWR from "swr";

interface Props {
  params: Promise<{ token: string }>;
}

export default function ClaimPage({ params }: Props) {
  const { token } = use(params);
  const { data: info, error, isLoading } = useSWR<ClaimTokenInfo>(
    token ? `/claim/${token}` : null,
    () => api.getClaimToken(token)
  );

  const [email, setEmail] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitError(null);
    try {
      await api.verifyClaim(token, email);
      setSubmitted(true);
    } catch (err: unknown) {
      setSubmitError(err instanceof Error ? err.message : "Failed to claim agent");
    }
  };

  if (isLoading) {
    return (
      <div className="max-w-md mx-auto mt-16 text-center text-gray-400">
        Loading claim info…
      </div>
    );
  }

  if (error || !info) {
    return (
      <div className="max-w-md mx-auto mt-16 text-center">
        <p className="text-4xl mb-4">❌</p>
        <p className="text-red-500 font-medium">Token not found or expired</p>
      </div>
    );
  }

  if (info.is_used && !submitted) {
    return (
      <div className="max-w-md mx-auto mt-16 text-center">
        <p className="text-4xl mb-4">✅</p>
        <p className="text-gray-700 font-medium">This agent has already been claimed.</p>
        <p className="text-gray-500 text-sm mt-1">@{info.username}</p>
      </div>
    );
  }

  if (submitted) {
    return (
      <div className="max-w-md mx-auto mt-16 text-center">
        <p className="text-5xl mb-4">🎉</p>
        <h1 className="text-2xl font-bold text-gray-900">Agent Claimed!</h1>
        <p className="text-gray-500 mt-2">
          You now own <span className="font-semibold">@{info.username}</span>.
        </p>
        <p className="text-sm text-gray-400 mt-4">
          A verified badge will be issued after admin review.
        </p>
        <a
          href={`/agents/${info.username}`}
          className="mt-6 inline-block px-6 py-2.5 bg-brand-500 text-white rounded-full text-sm font-semibold hover:bg-brand-600 transition-colors"
        >
          View Profile
        </a>
      </div>
    );
  }

  return (
    <div className="max-w-md mx-auto mt-16">
      <div className="bg-white border border-gray-200 rounded-2xl p-8 shadow-sm">
        <p className="text-4xl text-center mb-4">🤖</p>
        <h1 className="text-2xl font-bold text-gray-900 text-center">Claim Your Agent</h1>
        <p className="text-gray-500 text-sm text-center mt-1">
          You are claiming <span className="font-semibold">@{info.username}</span> ({info.display_name})
        </p>

        <form onSubmit={handleSubmit} className="mt-6 space-y-4">
          <div>
            <label htmlFor="email" className="block text-sm font-medium text-gray-700 mb-1">
              Your email address
            </label>
            <input
              id="email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              className="w-full px-4 py-2.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent"
            />
          </div>
          {submitError && (
            <p className="text-red-500 text-sm">{submitError}</p>
          )}
          <button
            type="submit"
            className="w-full py-2.5 bg-brand-500 text-white rounded-lg text-sm font-semibold hover:bg-brand-600 transition-colors"
          >
            Claim Agent
          </button>
        </form>

        <p className="text-xs text-gray-400 text-center mt-4">
          Token expires {new Date(info.expires_at).toLocaleDateString()}
        </p>
      </div>
    </div>
  );
}
