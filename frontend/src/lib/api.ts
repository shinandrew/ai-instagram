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
};
