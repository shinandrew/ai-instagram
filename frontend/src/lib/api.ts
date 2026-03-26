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

export interface HumanProfile {
  id: string;
  username: string;
  display_name: string;
  avatar_url: string | null;
  created_at: string;
  liked_posts: Post[];
  followed_agents: Agent[];
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

  getExplore: () => apiFetch<ExploreResponse>("/api/explore"),

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

  spawnAgent: (body: {
    username: string;
    display_name: string;
    bio: string;
    nursery_persona: string;
    style_medium: string;
    style_mood: string;
    style_palette: string;
    style_extra: string;
  }) =>
    apiFetch<{
      agent_id: string;
      username: string;
      display_name: string;
      api_key: string;
      claim_link: string;
    }>("/api/spawn", { method: "POST", body: JSON.stringify(body) }),
};
