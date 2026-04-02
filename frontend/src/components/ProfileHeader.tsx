"use client";

import { useState, useEffect } from "react";
import Image from "next/image";
import Link from "next/link";
import { useSession } from "next-auth/react";
import { Agent, SpawnedBy, api } from "@/lib/api";
import { getHumanToken } from "@/lib/humanAuth";
import { VerifiedBadge } from "./VerifiedBadge";
import { RankBadge } from "./RankBadge";
import { imgSrc } from "@/lib/imgSrc";

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
            <p className="text-center text-gray-500 py-8 text-sm">Failed to load.</p>
          )}
          {!error && agents === null && (
            <p className="text-center text-gray-400 py-8 text-sm">Loading…</p>
          )}
          {agents && agents.length === 0 && (
            <p className="text-center text-gray-400 py-8 text-sm">None yet.</p>
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

export function ProfileHeader({ agent, spawnedBy }: { agent: Agent; spawnedBy?: SpawnedBy | null }) {
  const [modal, setModal] = useState<"followers" | "following" | null>(null);
  const { data: session } = useSession();
  const [humanFollowerCount, setHumanFollowerCount] = useState(agent.human_follower_count ?? 0);
  const [humanFollowing, setHumanFollowing] = useState(false);

  // Fetch real follow status on mount whenever session is available
  useEffect(() => {
    const token = (session as any)?.human_token as string | undefined;
    if (!token) return;
    api.getHumanFollowStatus(agent.id, token)
      .then((r) => setHumanFollowing(r.following))
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
                Claimed
              </span>
            )}
          </h1>
          <p className="text-gray-500 text-sm mt-0.5">@{agent.username}</p>
          {agent.bio && <p className="text-gray-700 mt-2 max-w-md">{agent.bio}</p>}

          {spawnedBy && (
            <p className="text-sm text-gray-500 mt-2">
              Spawned by{" "}
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
              <span className="text-gray-500">posts</span>
            </div>
            <button
              onClick={() => setModal("followers")}
              className="text-center hover:opacity-70 transition-opacity"
            >
              <span className="font-bold text-gray-900 block">{agent.follower_count}</span>
              <span className="text-gray-500">agent followers</span>
            </button>
            <div className="text-center">
              <span className="font-bold text-gray-900 block">{humanFollowerCount}</span>
              <span className="text-gray-500">human followers</span>
            </div>
            <button
              onClick={() => setModal("following")}
              className="text-center hover:opacity-70 transition-opacity"
            >
              <span className="font-bold text-gray-900 block">{agent.following_count}</span>
              <span className="text-gray-500">following</span>
            </button>
          </div>
          {session && (
            <button
              onClick={handleHumanFollow}
              className={`mt-3 px-4 py-1.5 rounded-full text-sm font-medium transition-colors ${humanFollowing ? "bg-gray-200 text-gray-700 hover:bg-gray-300" : "bg-brand-500 text-white hover:bg-brand-600"}`}
            >
              {humanFollowing ? "Following" : "Follow"}
            </button>
          )}
        </div>
      </div>

      {modal && (
        <FollowListModal
          title={modal === "followers" ? "Followers" : "Following"}
          username={agent.username}
          kind={modal}
          onClose={() => setModal(null)}
        />
      )}
    </>
  );
}
