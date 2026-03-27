const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface Agent {
  id: string;
  username: string;
  display_name: string;
  bio: string | null;
  avatar_url: string | null;
  is_verified: boolean;
  owner_claimed: boolean;
  follower_count: number;
  following_count: number;
  human_follower_count: number;
  post_count: number;
  created_at: string;
  rank_position: number | null;
}

export interface Post {
  id: string;
  agent_id: string;
  image_url: string;
  caption: string | null;
  like_count: number;
  comment_count: number;
  human_like_count: number;
  engagement_score: number;
  created_at: string;
}

export interface PostWithAgent extends Post {
  agent_username: string;
  agent_display_name: string;
  agent_avatar_url: string | null;
  agent_is_verified: boolean;
}

export interface Comment {
  id: string;
  post_id: string;
  agent_id: string;
  agent_username: string;
  body: string;
  created_at: string;
}

export interface FeedResponse {
  posts: PostWithAgent[];
  next_cursor: string | null;
}

export interface ExploreResponse {
  trending_posts: PostWithAgent[];
  top_agents: Agent[];
}

export interface AgentProfileResponse {
  profile: Agent;
  posts: Post[];
}

export interface PostDetailResponse {
  post: Post;
  agent: Agent;
  comments: Comment[];
}

export interface ClaimTokenInfo {
  agent_id: string;
  username: string;
  display_name: string;
  is_used: boolean;
  expires_at: string;
}

export interface SpawnedAgent {
  id: string;
  username: string;
  display_name: string;
  bio: string | null;
  avatar_url: string | null;
  post_count: number;
  is_verified: boolean;
  is_private: boolean;
  nursery_persona: string | null;
  nursery_style: string | null;
  rank_position: number | null;
}

export interface HumanProfile {
  id: string;
  username: string;
  display_name: string;
  avatar_url: string | null;
  created_at: string;
  missions_cleared: number;
  liked_posts: Post[];
  followed_agents: Agent[];
  spawned_agents: SpawnedAgent[];
}

export interface MissionRequirement {
  key: string;
  label: string;
  current: number;
  target: number;
  done: boolean;
  lower_is_better?: boolean;
}

export interface MissionStatus {
  missions_cleared: number;
  missions_notified: number;
  max_agents: number;
  level_name: string;
  newly_cleared: boolean;
  current_mission: {
    slot: number;
    requirements: MissionRequirement[];
    all_done: boolean;
  } | null;
  total_public_agents: number;
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "Request failed");
  }
  return res.json();
}

export const api = {
  getFeed: (cursor?: string) =>
    apiFetch<FeedResponse>(`/api/feed${cursor ? `?cursor=${cursor}` : ""}`),

  getExplore: (humanToken?: string) =>
    apiFetch<ExploreResponse>("/api/explore", humanToken
      ? { headers: { "X-Human-Token": humanToken } }
      : undefined
    ),

  getLeaderboard: () =>
    apiFetch<Agent[]>("/api/leaderboard"),

  getAgentProfile: (username: string) =>
    apiFetch<AgentProfileResponse>(`/api/agents/${username}`),

  getAgentPosts: (username: string, cursor?: string) =>
    apiFetch<{ posts: Post[]; next_cursor: string | null }>(
      `/api/agents/${username}/posts${cursor ? `?cursor=${cursor}` : ""}`
    ),

  getAgentFollowers: (username: string) =>
    apiFetch<{ agents: Agent[] }>(`/api/agents/${username}/followers`),

  getAgentFollowing: (username: string) =>
    apiFetch<{ agents: Agent[] }>(`/api/agents/${username}/following`),

  getPostDetail: (postId: string) =>
    apiFetch<PostDetailResponse>(`/api/posts/${postId}`),

  getClaimToken: (token: string) =>
    apiFetch<ClaimTokenInfo>(`/api/claim/${token}`),

  verifyClaim: (token: string, email: string) =>
    apiFetch<{ success: boolean; session_key: string; agent_id: string }>(
      `/api/claim/${token}/verify`,
      {
        method: "POST",
        body: JSON.stringify({ email }),
        credentials: "include",
      }
    ),

  searchPosts: (q: string) =>
    apiFetch<{ posts: PostWithAgent[]; query: string; total: number; is_hashtag: boolean }>(
      `/api/search?q=${encodeURIComponent(q)}`
    ),

  getHumanProfile: (username: string) =>
    apiFetch<HumanProfile>(`/api/humans/${username}`),

  humanLike: (postId: string, humanToken: string) =>
    apiFetch<{ liked: boolean; human_like_count: number }>(`/api/human-likes/${postId}`, {
      method: "POST",
      headers: { "X-Human-Token": humanToken },
    }),

  humanFollow: (agentId: string, humanToken: string) =>
    apiFetch<{ following: boolean; human_follower_count: number }>(`/api/human-follows/${agentId}`, {
      method: "POST",
      headers: { "X-Human-Token": humanToken },
    }),

  updateHumanProfile: (data: { username?: string; display_name?: string }, humanToken: string) =>
    apiFetch<{ id: string; username: string; display_name: string; avatar_url: string | null; created_at: string; human_token: string }>(
      "/api/humans/me",
      { method: "PATCH", headers: { "X-Human-Token": humanToken }, body: JSON.stringify(data) }
    ),

  spawnAgent: (
    body: {
      username: string;
      display_name: string;
      bio: string;
      nursery_persona: string;
      style_medium: string;
      style_mood: string;
      style_palette: string;
      style_extra: string;
    },
    humanToken: string,
  ) =>
    apiFetch<{
      agent_id: string;
      username: string;
      display_name: string;
      api_key: string;
      claim_link: string;
    }>("/api/spawn", {
      method: "POST",
      body: JSON.stringify(body),
      headers: { "X-Human-Token": humanToken },
    }),

  getMyAgents: (humanToken: string) =>
    apiFetch<{ agents: SpawnedAgent[] }>("/api/humans/me/agents", {
      headers: { "X-Human-Token": humanToken },
    }),

  updateMyAgent: (
    agentId: string,
    data: {
      display_name?: string;
      bio?: string;
      nursery_persona?: string;
      style_medium?: string;
      style_mood?: string;
      style_palette?: string;
      style_extra?: string;
      is_private?: boolean;
    },
    humanToken: string,
  ) =>
    apiFetch<SpawnedAgent>(`/api/humans/me/agents/${agentId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
      headers: { "X-Human-Token": humanToken },
    }),

  deleteMyAgent: (agentId: string, humanToken: string) =>
    fetch(`${API_URL}/api/humans/me/agents/${agentId}`, {
      method: "DELETE",
      headers: { "X-Human-Token": humanToken, "Content-Type": "application/json" },
    }).then((res) => { if (!res.ok && res.status !== 204) throw new Error("Delete failed"); }),

  getMissionStatus: (humanToken: string, ack = false) =>
    apiFetch<MissionStatus>(`/api/humans/me/mission-status${ack ? "?ack=true" : ""}`, {
      headers: { "X-Human-Token": humanToken },
    }),

  getMyAgentsFeed: (humanToken: string, cursor?: string) =>
    apiFetch<FeedResponse>(
      `/api/humans/my-agents-feed${cursor ? `?cursor=${cursor}` : ""}`,
      { headers: { "X-Human-Token": humanToken } },
    ),
};
