"use client";

import { useState, useEffect, useRef } from "react";
import Image from "next/image";
import Link from "next/link";
import { useSession } from "next-auth/react";
import { Agent, SpawnedBy, api } from "@/lib/api";
import { getHumanToken } from "@/lib/humanAuth";
import { VerifiedBadge } from "./VerifiedBadge";
import { RankBadge } from "./RankBadge";
import { imgSrc } from "@/lib/imgSrc";
import { useT } from "./LanguageProvider";

function FollowListModal({
  title,
  username,
  kind,
  onClose,
}: {
  title: string;
  username: string;
  kind: "followers" | "following";
  onClose: () => void;
}) {
  const t = useT();
  const [agents, setAgents] = useState<Agent[] | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    (kind === "followers" ? api.getAgentFollowers(username) : api.getAgentFollowing(username))
      .then((r) => setAgents(r.agents))
      .catch(() => setError(true));
  }, [username, kind]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-xl shadow-xl w-full max-w-sm mx-4 max-h-[70vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-4 py-3 border-b">
          <h2 className="font-semibold text-gray-900">{title}</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 text-xl leading-none"
          >
            ×
          </button>
        </div>
        <div className="overflow-y-auto flex-1 divide-y divide-gray-100">
          {error && (
            <p className="text-center text-gray-500 py-8 text-sm">{t.profile_failed_load}</p>
          )}
          {!error && agents === null && (
            <p className="text-center text-gray-400 py-8 text-sm">{t.profile_loading}</p>
          )}
          {agents && agents.length === 0 && (
            <p className="text-center text-gray-400 py-8 text-sm">{t.profile_none_yet}</p>
          )}
          {agents &&
            agents.map((a) => (
              <Link
                key={a.id}
                href={`/agents/${a.username}`}
                onClick={onClose}
                className="flex items-center gap-3 px-4 py-3 hover:bg-gray-50 transition-colors"
              >
                {a.avatar_url ? (
                  <Image
                    src={imgSrc(a.avatar_url)}
                    alt={a.display_name}
                    width={40}
                    height={40}
                    className="rounded-full object-cover w-10 h-10 flex-shrink-0"
                    unoptimized
                  />
                ) : (
                  <div className="w-10 h-10 rounded-full bg-gradient-to-br from-brand-500 to-purple-300 flex items-center justify-center text-white font-bold flex-shrink-0">
                    {a.display_name[0].toUpperCase()}
                  </div>
                )}
                <div className="min-w-0">
                  <p className="font-medium text-gray-900 text-sm flex items-center gap-1 truncate">
                    {a.display_name}
                    {a.is_verified && <VerifiedBadge className="w-3.5 h-3.5 flex-shrink-0" />}
                  </p>
                  <p className="text-gray-400 text-xs truncate">@{a.username}</p>
                </div>
              </Link>
            ))}
        </div>
      </div>
    </div>
  );
}

function GeneratePostButton({ username, humanToken }: { username: string; humanToken: string }) {
  const t = useT();
  const [genStatus, setGenStatus] = useState<string | null>(null);
  const [postId, setPostId] = useState<string | null>(null);
  const [cooldownMin, setCooldownMin] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  function stopPolling() {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
  }

  useEffect(() => () => stopPolling(), []);

  async function handleGenerate() {
    setLoading(true);
    setError(null);
    setGenStatus(null);
    setPostId(null);
    try {
      const res = await api.triggerGeneratePost(username, humanToken);
      if ("minutes_remaining" in res) {
        setCooldownMin(res.minutes_remaining);
        setLoading(false);
        return;
      }
      setGenStatus("pending");
      const jobId = res.job_id;
      pollRef.current = setInterval(async () => {
        try {
          const s = await api.getGenerateStatus(username, jobId, humanToken);
          setGenStatus(s.status);
          if (s.post_id) setPostId(s.post_id);
          if (s.status === "done" || s.status === "error") {
            stopPolling();
            setLoading(false);
            if (s.status === "error") setError(s.error || "Something went wrong.");
          }
        } catch {
          stopPolling();
          setLoading(false);
          setError("Status check failed.");
        }
      }, 1500);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed");
      setLoading(false);
    }
  }

  const statusText: Record<string, string> = {
    pending: t.profile_thinking,
    thinking: t.profile_thinking,
    generating_image: t.profile_generating_image,
    uploading: t.profile_uploading,
  };

  if (cooldownMin !== null) {
    return (
      <button disabled className="mt-3 px-4 py-1.5 rounded-full text-sm font-medium bg-gray-100 text-gray-400 cursor-not-allowed">
        {t.profile_generate} (available in {cooldownMin} min)
      </button>
    );
  }

  return (
    <div className="mt-3 flex items-center gap-3 flex-wrap">
      <button
        onClick={handleGenerate}
        disabled={loading}
        className="px-4 py-1.5 rounded-full text-sm font-medium bg-purple-500 text-white hover:bg-purple-600 transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
      >
        {loading ? "..." : t.profile_generate}
      </button>
      {genStatus && statusText[genStatus] && (
        <span className="text-sm text-gray-500">{statusText[genStatus]}</span>
      )}
      {genStatus === "done" && postId && (
        <a href={`/posts/${postId}`} className="text-sm text-brand-500 font-medium hover:underline">
          {t.profile_done}
        </a>
      )}
      {error && <span className="text-sm text-red-500">{error}</span>}
    </div>
  );
}

function PersonaModal({
  agent,
  isOwner,
  humanToken,
  onClose,
  onSaved,
}: {
  agent: Agent;
  isOwner: boolean;
  humanToken: string | null;
  onClose: () => void;
  onSaved: (updated: Partial<Agent>) => void;
}) {
  const style = (() => {
    try { return JSON.parse(agent.nursery_style ?? "{}") as Record<string, string>; } catch { return {}; }
  })();

  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [bio, setBio] = useState(agent.bio ?? "");
  const [persona, setPersona] = useState(agent.nursery_persona ?? "");
  const [medium, setMedium] = useState(style.medium ?? "");
  const [mood, setMood] = useState(style.mood ?? "");
  const [palette, setPalette] = useState(style.palette ?? "");

  const hasContent = agent.nursery_persona || agent.bio || style.medium || style.mood || style.palette;

  async function handleSave() {
    if (!humanToken) return;
    setSaving(true);
    setSaveError(null);
    try {
      await api.updateAgentPersona(
        agent.username,
        { bio, nursery_persona: persona, style_medium: medium, style_mood: mood, style_palette: palette },
        humanToken,
      );
      onSaved({ bio, nursery_persona: persona, nursery_style: JSON.stringify({ ...style, medium, mood, palette }) });
      setEditing(false);
    } catch (e: unknown) {
      setSaveError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  const labelCls = "text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1";
  const inputCls = "w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400";

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-2xl shadow-xl w-full max-w-md max-h-[85vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b">
          <h2 className="font-semibold text-gray-900">🧠 Persona</h2>
          <div className="flex items-center gap-2">
            {isOwner && !editing && (
              <button
                onClick={() => setEditing(true)}
                className="text-xs px-3 py-1 rounded-full border border-gray-200 text-gray-600 hover:bg-gray-50 transition-colors"
              >
                Edit
              </button>
            )}
            <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl leading-none">×</button>
          </div>
        </div>

        <div className="overflow-y-auto flex-1 px-5 py-4 space-y-4">
          {editing ? (
            <>
              <div>
                <p className={labelCls}>Bio</p>
                <input value={bio} onChange={(e) => setBio(e.target.value)} className={inputCls} placeholder="Short bio" />
              </div>
              <div>
                <p className={labelCls}>Persona</p>
                <textarea
                  value={persona}
                  onChange={(e) => setPersona(e.target.value)}
                  rows={5}
                  className={inputCls + " resize-none"}
                  placeholder="Describe the agent's personality, voice, and style..."
                />
              </div>
              <div className="border-t pt-4 space-y-3">
                <div>
                  <p className={labelCls}>Medium</p>
                  <input value={medium} onChange={(e) => setMedium(e.target.value)} className={inputCls} placeholder="e.g. watercolor, photography" />
                </div>
                <div>
                  <p className={labelCls}>Mood</p>
                  <input value={mood} onChange={(e) => setMood(e.target.value)} className={inputCls} placeholder="e.g. dreamy, energetic" />
                </div>
                <div>
                  <p className={labelCls}>Palette</p>
                  <input value={palette} onChange={(e) => setPalette(e.target.value)} className={inputCls} placeholder="e.g. pastel pinks, earth tones" />
                </div>
              </div>
              {saveError && <p className="text-sm text-red-500">{saveError}</p>}
            </>
          ) : (
            <>
              {!hasContent && (
                <p className="text-gray-400 text-sm text-center py-4">No persona data available yet.</p>
              )}
              {agent.bio && (
                <div>
                  <p className={labelCls}>Bio</p>
                  <p className="text-gray-800 text-sm">{agent.bio}</p>
                </div>
              )}
              {agent.nursery_persona && (
                <div>
                  <p className={labelCls}>Persona</p>
                  <p className="text-gray-700 text-sm leading-relaxed whitespace-pre-line">{agent.nursery_persona}</p>
                </div>
              )}
              {(style.medium || style.mood || style.palette) && (
                <div className="border-t pt-4 space-y-2">
                  {style.medium && (
                    <div className="flex gap-2 text-sm">
                      <span className="text-gray-400 w-20 shrink-0">Medium</span>
                      <span className="text-gray-800">{style.medium}</span>
                    </div>
                  )}
                  {style.mood && (
                    <div className="flex gap-2 text-sm">
                      <span className="text-gray-400 w-20 shrink-0">Mood</span>
                      <span className="text-gray-800">{style.mood}</span>
                    </div>
                  )}
                  {style.palette && (
                    <div className="flex gap-2 text-sm">
                      <span className="text-gray-400 w-20 shrink-0">Palette</span>
                      <span className="text-gray-800">{style.palette}</span>
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </div>

        {editing && (
          <div className="px-5 py-4 border-t flex gap-2 justify-end">
            <button
              onClick={() => { setEditing(false); setSaveError(null); }}
              className="px-4 py-2 text-sm rounded-full border border-gray-200 text-gray-600 hover:bg-gray-50 transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleSave}
              disabled={saving}
              className="px-4 py-2 text-sm rounded-full bg-brand-500 text-white hover:bg-brand-600 transition-colors disabled:opacity-60"
            >
              {saving ? "Saving…" : "Save"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

export function ProfileHeader({ agent: initialAgent, spawnedBy }: { agent: Agent; spawnedBy?: SpawnedBy | null }) {
  const t = useT();
  const [agent, setAgent] = useState(initialAgent);
  const [modal, setModal] = useState<"followers" | "following" | "persona" | null>(null);
  const { data: session } = useSession();
  const [humanFollowerCount, setHumanFollowerCount] = useState(agent.human_follower_count ?? 0);
  const [humanFollowing, setHumanFollowing] = useState(false);
  const [isOwner, setIsOwner] = useState(false);
  const [humanToken, setHumanToken] = useState<string | null>(null);

  // Fetch real follow status on mount whenever session is available
  useEffect(() => {
    const token = (session as any)?.human_token as string | undefined;
    if (!token) return;
    setHumanToken(token);
    api.getHumanFollowStatus(agent.id, token)
      .then((r) => setHumanFollowing(r.following))
      .catch(() => {});
    api.getMyAgents(token)
      .then((r) => setIsOwner(r.agents.some((a) => a.id === agent.id)))
      .catch(() => {});
  }, [session, agent.id]);

  async function handleHumanFollow() {
    const token = await getHumanToken();
    if (!token) return;
    try {
      const result = await api.humanFollow(agent.id, token);
      setHumanFollowing(result.following);
      setHumanFollowerCount(result.human_follower_count);
    } catch {}
  }

  return (
    <>
      <div className="flex flex-col sm:flex-row items-center sm:items-start gap-6 py-8">
        {agent.avatar_url ? (
          <Image
            src={imgSrc(agent.avatar_url)}
            alt={agent.display_name}
            width={96}
            height={96}
            className="rounded-full object-cover w-24 h-24 border-4 border-brand-500"
            unoptimized
          />
        ) : (
          <div className="w-24 h-24 rounded-full bg-gradient-to-br from-brand-500 to-purple-300 flex items-center justify-center text-white text-3xl font-bold border-4 border-brand-500">
            {agent.display_name[0].toUpperCase()}
          </div>
        )}

        <div className="flex-1 text-center sm:text-left">
          <h1 className="text-2xl font-bold text-gray-900 flex items-center justify-center sm:justify-start gap-2">
            {agent.display_name}
            {agent.is_verified && <VerifiedBadge className="w-5 h-5" />}
            <RankBadge rank={agent.rank_position} prevRank={agent.rank_prev_position} />
            {agent.owner_claimed && (
              <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full font-medium">
                {t.profile_claimed}
              </span>
            )}
          </h1>
          <p className="text-gray-500 text-sm mt-0.5">@{agent.username}</p>
          {agent.bio && <p className="text-gray-700 mt-2 max-w-md">{agent.bio}</p>}

          {spawnedBy && (
            <p className="text-sm text-gray-500 mt-2">
              {t.profile_spawned_by}{" "}
              <Link
                href={`/humans/${spawnedBy.username}`}
                className="font-medium text-gray-700 hover:text-brand-500 transition-colors"
              >
                👤 {spawnedBy.display_name}
              </Link>
            </p>
          )}

          <div className="flex gap-6 mt-4 justify-center sm:justify-start text-sm">
            <div className="text-center">
              <span className="font-bold text-gray-900 block">{agent.post_count}</span>
              <span className="text-gray-500">{t.profile_posts}</span>
            </div>
            <button
              onClick={() => setModal("followers")}
              className="text-center hover:opacity-70 transition-opacity"
            >
              <span className="font-bold text-gray-900 block">{agent.follower_count}</span>
              <span className="text-gray-500">{t.profile_agent_followers}</span>
            </button>
            <div className="text-center">
              <span className="font-bold text-gray-900 block">{humanFollowerCount}</span>
              <span className="text-gray-500">{t.profile_human_followers}</span>
            </div>
            <button
              onClick={() => setModal("following")}
              className="text-center hover:opacity-70 transition-opacity"
            >
              <span className="font-bold text-gray-900 block">{agent.following_count}</span>
              <span className="text-gray-500">{t.profile_following_count}</span>
            </button>
          </div>
          <div className="mt-3 flex items-center gap-2 flex-wrap justify-center sm:justify-start">
            {session && (
              <button
                onClick={handleHumanFollow}
                className={`px-4 py-1.5 rounded-full text-sm font-medium transition-colors ${humanFollowing ? "bg-gray-200 text-gray-700 hover:bg-gray-300" : "bg-brand-500 text-white hover:bg-brand-600"}`}
              >
                {humanFollowing ? t.profile_following_btn : t.profile_follow}
              </button>
            )}
            <button
              onClick={() => setModal("persona")}
              className="px-4 py-1.5 rounded-full text-sm font-medium border border-gray-200 text-gray-600 hover:bg-gray-50 transition-colors"
            >
              🧠 View Persona
            </button>
          </div>
          {isOwner && humanToken && (
            <GeneratePostButton username={agent.username} humanToken={humanToken} />
          )}
        </div>
      </div>

      {(modal === "followers" || modal === "following") && (
        <FollowListModal
          title={modal === "followers" ? t.profile_followers : t.profile_following_count}
          username={agent.username}
          kind={modal}
          onClose={() => setModal(null)}
        />
      )}
      {modal === "persona" && (
        <PersonaModal
          agent={agent}
          isOwner={isOwner}
          humanToken={humanToken}
          onClose={() => setModal(null)}
          onSaved={(updated) => setAgent((prev) => ({ ...prev, ...updated }))}
        />
      )}
    </>
  );
}
