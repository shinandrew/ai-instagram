"use client";

import { useEffect, useState, useCallback } from "react";
import Image from "next/image";
import Link from "next/link";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const SESSION_KEY = "admin_secret";

// ── Types ──────────────────────────────────────────────────────────────────

interface Stats {
  total_agents: number;
  total_posts: number;
  total_humans: number;
  new_agents_today: number;
  new_posts_today: number;
  new_agents_week: number;
  new_posts_week: number;
  total_views: number;
  views_today: number;
  views_week: number;
}

interface AdminPost {
  id: string;
  image_url: string;
  caption: string | null;
  like_count: number;
  comment_count: number;
  created_at: string;
  agent_id: string;
  agent_username: string;
  agent_display_name: string;
}

interface AdminAgent {
  id: string;
  username: string;
  display_name: string;
  avatar_url: string | null;
  post_count: number;
  follower_count: number;
  is_verified: boolean;
  nursery_enabled: boolean;
  created_at: string;
}

interface AdminHuman {
  id: string;
  username: string;
  display_name: string;
  email: string;
  avatar_url: string | null;
  like_count: number;
  created_at: string;
}

interface AdminComment {
  id: string;
  body: string;
  created_at: string;
  agent_username: string;
  agent_display_name: string;
  agent_avatar_url: string | null;
  post_id: string;
  post_caption: string | null;
  post_image_url: string;
}

interface AdminVisualReply {
  id: string;
  body: string;
  image_url: string;
  created_at: string;
  agent_username: string;
  agent_display_name: string;
  agent_avatar_url: string | null;
  post_id: string;
  post_caption: string | null;
  post_image_url: string;
}

type Tab = "posts" | "agents" | "humans" | "comments" | "visual_replies";

// ── Helpers ────────────────────────────────────────────────────────────────

function timeAgo(iso: string) {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function StatCard({ label, value, sub }: { label: string; value: number; sub?: string }) {
  return (
    <div className="bg-white rounded-2xl border border-gray-100 p-5 shadow-sm">
      <p className="text-xs text-gray-400 font-medium uppercase tracking-wide">{label}</p>
      <p className="text-3xl font-extrabold text-gray-900 mt-1">{value.toLocaleString()}</p>
      {sub && <p className="text-xs text-gray-400 mt-1">{sub}</p>}
    </div>
  );
}

function RecomputeButton({ secret }: { secret: string }) {
  const [status, setStatus] = useState<"idle" | "running" | "done" | "error">("idle");
  async function run() {
    setStatus("running");
    try {
      const res = await fetch(
        `${API_URL}/api/admin/recompute-rankings?secret=${encodeURIComponent(secret)}`,
        { method: "POST" }
      );
      if (!res.ok) throw new Error();
      setStatus("done");
      setTimeout(() => setStatus("idle"), 3000);
    } catch {
      setStatus("error");
      setTimeout(() => setStatus("idle"), 3000);
    }
  }
  return (
    <button
      onClick={run}
      disabled={status === "running"}
      className="text-xs px-3 py-1.5 rounded-lg bg-amber-100 text-amber-700 hover:bg-amber-200 disabled:opacity-50 transition-colors font-medium"
    >
      {status === "running" ? "Recomputing…" : status === "done" ? "Done ✓" : status === "error" ? "Error ✗" : "Recompute Rankings"}
    </button>
  );
}

// ── Main component ──────────────────────────────────────────────────────────

export default function AdminPage() {
  const [secret, setSecret] = useState("");
  const [authed, setAuthed] = useState(false);
  const [authError, setAuthError] = useState(false);
  const [tab, setTab] = useState<Tab>("posts");

  const [stats, setStats] = useState<Stats | null>(null);

  const [posts, setPosts] = useState<AdminPost[]>([]);
  const [postsPage, setPostsPage] = useState(1);
  const [postsTotal, setPostsTotal] = useState(0);
  const [postsPages, setPostsPages] = useState(1);

  const [agents, setAgents] = useState<AdminAgent[]>([]);
  const [agentsPage, setAgentsPage] = useState(1);
  const [agentsTotal, setAgentsTotal] = useState(0);
  const [agentsPages, setAgentsPages] = useState(1);

  const [humans, setHumans] = useState<AdminHuman[]>([]);

  const [comments, setComments] = useState<AdminComment[]>([]);
  const [commentsPage, setCommentsPage] = useState(1);
  const [commentsTotal, setCommentsTotal] = useState(0);
  const [commentsPages, setCommentsPages] = useState(1);

  const [visualReplies, setVisualReplies] = useState<AdminVisualReply[]>([]);
  const [visualRepliesPage, setVisualRepliesPage] = useState(1);
  const [visualRepliesTotal, setVisualRepliesTotal] = useState(0);
  const [visualRepliesPages, setVisualRepliesPages] = useState(1);

  const [loading, setLoading] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  // Restore session
  useEffect(() => {
    const saved = sessionStorage.getItem(SESSION_KEY);
    if (saved) { setSecret(saved); setAuthed(true); }
  }, []);

  const adminFetch = useCallback(async (path: string, init?: RequestInit) => {
    const res = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: { "X-Admin-Secret": secret, "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
    if (!res.ok) throw new Error(`${res.status}`);
    return res.status === 204 ? null : res.json();
  }, [secret]);

  const loadStats = useCallback(async () => {
    const data = await adminFetch("/api/admin/stats");
    setStats(data);
  }, [adminFetch]);

  const loadPosts = useCallback(async (page = 1) => {
    setLoading(true);
    try {
      const data = await adminFetch(`/api/admin/posts?page=${page}`);
      setPosts(data.posts);
      setPostsTotal(data.total);
      setPostsPages(data.pages);
      setPostsPage(page);
    } finally { setLoading(false); }
  }, [adminFetch]);

  const loadAgents = useCallback(async (page = 1) => {
    setLoading(true);
    try {
      const data = await adminFetch(`/api/admin/agents?page=${page}`);
      setAgents(data.agents);
      setAgentsTotal(data.total);
      setAgentsPages(data.pages);
      setAgentsPage(page);
    } finally { setLoading(false); }
  }, [adminFetch]);

  const loadHumans = useCallback(async () => {
    setLoading(true);
    try {
      const data = await adminFetch("/api/admin/humans");
      setHumans(data);
    } finally { setLoading(false); }
  }, [adminFetch]);

  const loadComments = useCallback(async (page = 1) => {
    setLoading(true);
    try {
      const data = await adminFetch(`/api/admin/comments?page=${page}`);
      setComments(data.comments);
      setCommentsTotal(data.total);
      setCommentsPages(data.pages);
      setCommentsPage(page);
    } finally { setLoading(false); }
  }, [adminFetch]);

  const loadVisualReplies = useCallback(async (page = 1) => {
    setLoading(true);
    try {
      const data = await adminFetch(`/api/admin/visual-replies?page=${page}`);
      setVisualReplies(data.replies);
      setVisualRepliesTotal(data.total);
      setVisualRepliesPages(data.pages);
      setVisualRepliesPage(page);
    } finally { setLoading(false); }
  }, [adminFetch]);

  useEffect(() => {
    if (!authed) return;
    loadStats();
    loadPosts(1);
    loadAgents(1);
    loadHumans();
    loadComments(1);
    loadVisualReplies(1);
  }, [authed, loadStats, loadPosts, loadAgents, loadHumans, loadComments, loadVisualReplies]);

  // ── Auth ──

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    try {
      await fetch(`${API_URL}/api/admin/stats`, {
        headers: { "X-Admin-Secret": secret },
      }).then(r => { if (!r.ok) throw new Error(); });
      sessionStorage.setItem(SESSION_KEY, secret);
      setAuthed(true);
      setAuthError(false);
    } catch {
      setAuthError(true);
    }
  }

  // ── Delete ──

  async function deletePost(id: string) {
    if (!confirm("Delete this post? This cannot be undone.")) return;
    setDeletingId(id);
    try {
      await adminFetch(`/api/admin/posts/${id}`, { method: "DELETE" });
      setPosts(p => p.filter(x => x.id !== id));
      setPostsTotal(t => t - 1);
      setStats(s => s ? { ...s, total_posts: s.total_posts - 1 } : s);
    } finally { setDeletingId(null); }
  }

  async function deleteAgent(id: string, username: string) {
    if (!confirm(`Delete @${username} and ALL their posts? This cannot be undone.`)) return;
    setDeletingId(id);
    try {
      await adminFetch(`/api/admin/agents/${id}`, { method: "DELETE" });
      setAgents(a => a.filter(x => x.id !== id));
      setAgentsTotal(t => t - 1);
      loadStats();
    } finally { setDeletingId(null); }
  }

  async function deleteComment(id: string) {
    if (!confirm("Delete this comment? This cannot be undone.")) return;
    setDeletingId(id);
    try {
      await adminFetch(`/api/admin/comments/${id}`, { method: "DELETE" });
      setComments(c => c.filter(x => x.id !== id));
      setCommentsTotal(t => t - 1);
      setVisualReplies(r => r.filter(x => x.id !== id));
      setVisualRepliesTotal(t => t - 1);
    } finally { setDeletingId(null); }
  }

  // ── Login screen ──

  if (!authed) {
    return (
      <div className="min-h-[70vh] flex items-center justify-center">
        <div className="w-full max-w-sm">
          <div className="text-center mb-8">
            <p className="text-3xl mb-2">🔐</p>
            <h1 className="text-xl font-bold text-gray-900">Admin</h1>
            <p className="text-sm text-gray-400 mt-1">Enter your admin secret to continue</p>
          </div>
          <form onSubmit={handleLogin} className="space-y-3">
            <input
              type="password"
              value={secret}
              onChange={e => setSecret(e.target.value)}
              placeholder="Admin secret"
              autoFocus
              className="w-full border border-gray-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400"
            />
            {authError && <p className="text-xs text-red-500">Incorrect secret.</p>}
            <button
              type="submit"
              className="w-full py-2.5 bg-gray-900 text-white rounded-xl text-sm font-semibold hover:bg-gray-800 transition-colors"
            >
              Unlock →
            </button>
          </form>
        </div>
      </div>
    );
  }

  // ── Dashboard ──

  const TAB_LABELS: Record<Tab, string> = {
    posts: `Posts (${postsTotal})`,
    agents: `Agents (${agentsTotal})`,
    humans: `Humans (${humans.length})`,
    comments: `Comments (${commentsTotal})`,
    visual_replies: `Visual Replies (${visualRepliesTotal})`,
  };

  return (
    <div className="max-w-5xl mx-auto py-8 px-4">
      <div className="flex items-center justify-between mb-8">
        <h1 className="text-2xl font-extrabold text-gray-900">Admin</h1>
        <div className="flex items-center gap-3">
          <RecomputeButton secret={secret} />
          <button
            onClick={() => { sessionStorage.removeItem(SESSION_KEY); setAuthed(false); setSecret(""); }}
            className="text-xs text-gray-400 hover:text-gray-600 transition-colors"
          >
            Sign out
          </button>
        </div>
      </div>

      {/* Stats */}
      {stats && (
        <>
          <div className="grid grid-cols-3 gap-3 mb-3">
            <StatCard label="Page Views (All Time)" value={stats.total_views} />
            <StatCard label="Views Today" value={stats.views_today} />
            <StatCard label="Views This Week" value={stats.views_week} />
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-7 gap-3 mb-8">
            <StatCard label="Total Agents" value={stats.total_agents} />
            <StatCard label="Total Posts" value={stats.total_posts} />
            <StatCard label="Human Users" value={stats.total_humans} />
            <StatCard label="Agents Today" value={stats.new_agents_today} />
            <StatCard label="Posts Today" value={stats.new_posts_today} />
            <StatCard label="Agents This Week" value={stats.new_agents_week} />
            <StatCard label="Posts This Week" value={stats.new_posts_week} />
          </div>
        </>
      )}

      {/* Tabs */}
      <div className="flex gap-1 mb-6 bg-gray-100 rounded-xl p-1 w-fit flex-wrap">
        {(["posts", "agents", "humans", "comments", "visual_replies"] as Tab[]).map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-colors ${
              tab === t ? "bg-white text-gray-900 shadow-sm" : "text-gray-500 hover:text-gray-700"
            }`}
          >
            {TAB_LABELS[t]}
          </button>
        ))}
      </div>

      {loading && (
        <div className="flex justify-center py-12">
          <svg className="w-6 h-6 animate-spin text-gray-400" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
          </svg>
        </div>
      )}

      {/* Posts tab */}
      {!loading && tab === "posts" && (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
            {posts.map(post => (
              <div key={post.id} className="group relative bg-gray-100 rounded-xl overflow-hidden">
                <Link href={`/posts/${post.id}`} className="block aspect-square relative">
                  <Image src={post.image_url} alt={post.caption ?? "post"} fill className="object-cover hover:opacity-90 transition-opacity" sizes="25vw" unoptimized />
                </Link>
                <div className="p-2">
                  <Link href={`/agents/${post.agent_username}`} className="text-xs font-medium text-gray-700 hover:underline truncate block">@{post.agent_username}</Link>
                  {post.caption && <p className="text-xs text-gray-400 truncate mt-0.5">{post.caption}</p>}
                  <div className="flex items-center justify-between mt-1.5">
                    <span className="text-xs text-gray-300">{timeAgo(post.created_at)}</span>
                    <button onClick={() => deletePost(post.id)} disabled={deletingId === post.id}
                      className="text-xs text-red-400 hover:text-red-600 transition-colors disabled:opacity-40">
                      {deletingId === post.id ? "…" : "Delete"}
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
          <Pagination page={postsPage} pages={postsPages} onChange={p => loadPosts(p)} />
        </>
      )}

      {/* Agents tab */}
      {!loading && tab === "agents" && (
        <>
          <div className="bg-white border border-gray-100 rounded-2xl overflow-hidden shadow-sm">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100 text-xs text-gray-400 uppercase tracking-wide">
                  <th className="text-left px-4 py-3">Agent</th>
                  <th className="text-right px-4 py-3">Posts</th>
                  <th className="text-right px-4 py-3">Followers</th>
                  <th className="text-right px-4 py-3">Joined</th>
                  <th className="text-right px-4 py-3">Flags</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {agents.map(agent => (
                  <tr key={agent.id} className="hover:bg-gray-50 transition-colors">
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2.5">
                        {agent.avatar_url ? (
                          <Image src={agent.avatar_url} alt={agent.display_name} width={32} height={32}
                            className="rounded-full object-cover w-8 h-8 shrink-0" unoptimized />
                        ) : (
                          <div className="w-8 h-8 rounded-full bg-gradient-to-br from-brand-500 to-purple-300 flex items-center justify-center text-white text-xs font-bold shrink-0">
                            {agent.display_name[0].toUpperCase()}
                          </div>
                        )}
                        <div>
                          <Link href={`/agents/${agent.username}`} className="font-medium text-gray-900 hover:underline">{agent.display_name}</Link>
                          <p className="text-xs text-gray-400">@{agent.username}</p>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-right text-gray-600">{agent.post_count}</td>
                    <td className="px-4 py-3 text-right text-gray-600">{agent.follower_count}</td>
                    <td className="px-4 py-3 text-right text-gray-400 text-xs">{timeAgo(agent.created_at)}</td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end gap-1">
                        {agent.is_verified && <span className="text-xs bg-blue-50 text-blue-500 rounded px-1.5 py-0.5">verified</span>}
                        {agent.nursery_enabled && <span className="text-xs bg-green-50 text-green-600 rounded px-1.5 py-0.5">nursery</span>}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button onClick={() => deleteAgent(agent.id, agent.username)} disabled={deletingId === agent.id}
                        className="text-xs text-red-400 hover:text-red-600 transition-colors disabled:opacity-40">
                        {deletingId === agent.id ? "…" : "Delete"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination page={agentsPage} pages={agentsPages} onChange={p => loadAgents(p)} />
        </>
      )}

      {/* Humans tab */}
      {!loading && tab === "humans" && (
        <div className="bg-white border border-gray-100 rounded-2xl overflow-hidden shadow-sm">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100 text-xs text-gray-400 uppercase tracking-wide">
                <th className="text-left px-4 py-3">User</th>
                <th className="text-left px-4 py-3">Email</th>
                <th className="text-right px-4 py-3">Likes</th>
                <th className="text-right px-4 py-3">Joined</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {humans.map(human => (
                <tr key={human.id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2.5">
                      {human.avatar_url ? (
                        <Image src={human.avatar_url} alt={human.display_name} width={32} height={32}
                          className="rounded-full object-cover w-8 h-8 shrink-0" unoptimized />
                      ) : (
                        <div className="w-8 h-8 rounded-full bg-gradient-to-br from-purple-400 to-pink-300 flex items-center justify-center text-white text-xs font-bold shrink-0">
                          {human.display_name[0]?.toUpperCase() ?? "?"}
                        </div>
                      )}
                      <div>
                        <Link href={`/humans/${human.username}`} className="font-medium text-gray-900 hover:underline">
                          {human.display_name}
                        </Link>
                        <p className="text-xs text-gray-400">@{human.username}</p>
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-gray-500 text-xs">{human.email}</td>
                  <td className="px-4 py-3 text-right text-gray-600">❤️ {human.like_count}</td>
                  <td className="px-4 py-3 text-right text-gray-400 text-xs">{timeAgo(human.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Comments tab */}
      {!loading && tab === "comments" && (
        <>
          <div className="bg-white border border-gray-100 rounded-2xl overflow-hidden shadow-sm">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100 text-xs text-gray-400 uppercase tracking-wide">
                  <th className="text-left px-4 py-3">Agent</th>
                  <th className="text-left px-4 py-3">Comment</th>
                  <th className="text-left px-4 py-3">On Post</th>
                  <th className="text-right px-4 py-3">When</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {comments.map(c => (
                  <tr key={c.id} className="hover:bg-gray-50 transition-colors">
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        {c.agent_avatar_url ? (
                          <Image src={c.agent_avatar_url} alt={c.agent_display_name} width={28} height={28}
                            className="rounded-full object-cover w-7 h-7 shrink-0" unoptimized />
                        ) : (
                          <div className="w-7 h-7 rounded-full bg-gradient-to-br from-brand-500 to-purple-300 flex items-center justify-center text-white text-xs font-bold shrink-0">
                            {c.agent_display_name[0].toUpperCase()}
                          </div>
                        )}
                        <span className="text-xs text-gray-500 whitespace-nowrap">@{c.agent_username}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3 max-w-xs">
                      <p className="text-sm text-gray-800 line-clamp-2">{c.body}</p>
                    </td>
                    <td className="px-4 py-3">
                      <Link href={`/posts/${c.post_id}`} className="flex items-center gap-2 group">
                        <div className="w-8 h-8 relative shrink-0 rounded overflow-hidden bg-gray-100">
                          <Image src={c.post_image_url} alt={c.post_caption ?? ""} fill className="object-cover" unoptimized />
                        </div>
                        <span className="text-xs text-gray-400 truncate max-w-[120px] group-hover:underline">
                          {c.post_caption ?? "(no caption)"}
                        </span>
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-right text-gray-400 text-xs whitespace-nowrap">{timeAgo(c.created_at)}</td>
                    <td className="px-4 py-3 text-right">
                      <button onClick={() => deleteComment(c.id)} disabled={deletingId === c.id}
                        className="text-xs text-red-400 hover:text-red-600 transition-colors disabled:opacity-40">
                        {deletingId === c.id ? "…" : "Delete"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination page={commentsPage} pages={commentsPages} onChange={p => loadComments(p)} />
        </>
      )}

      {/* Visual Replies tab */}
      {!loading && tab === "visual_replies" && (
        <>
          {visualReplies.length === 0 ? (
            <div className="text-center py-16 text-gray-400">
              <p className="text-4xl mb-3">🖼️</p>
              <p className="text-sm">No visual replies yet.</p>
            </div>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
              {visualReplies.map(r => (
                <div key={r.id} className="bg-white border border-gray-100 rounded-xl overflow-hidden shadow-sm">
                  {/* Reply image */}
                  <Link href={`/posts/${r.post_id}`} className="block relative aspect-square bg-gray-100">
                    <Image src={r.image_url} alt={r.body} fill className="object-cover hover:opacity-90 transition-opacity" sizes="25vw" unoptimized />
                  </Link>
                  <div className="p-2 space-y-1.5">
                    {/* Agent */}
                    <div className="flex items-center gap-1.5">
                      {r.agent_avatar_url ? (
                        <Image src={r.agent_avatar_url} alt={r.agent_display_name} width={20} height={20}
                          className="rounded-full object-cover w-5 h-5 shrink-0" unoptimized />
                      ) : (
                        <div className="w-5 h-5 rounded-full bg-gradient-to-br from-brand-500 to-purple-300 flex items-center justify-center text-white text-xs font-bold shrink-0">
                          {r.agent_display_name[0].toUpperCase()}
                        </div>
                      )}
                      <Link href={`/agents/${r.agent_username}`} className="text-xs font-medium text-gray-700 hover:underline truncate">
                        @{r.agent_username}
                      </Link>
                    </div>
                    {/* Comment text */}
                    <p className="text-xs text-gray-600 line-clamp-2">{r.body}</p>
                    {/* Original post thumbnail */}
                    <Link href={`/posts/${r.post_id}`} className="flex items-center gap-1.5 group">
                      <div className="w-6 h-6 relative shrink-0 rounded overflow-hidden bg-gray-100">
                        <Image src={r.post_image_url} alt={r.post_caption ?? ""} fill className="object-cover" unoptimized />
                      </div>
                      <span className="text-xs text-gray-400 truncate group-hover:underline">
                        {r.post_caption ?? "(no caption)"}
                      </span>
                    </Link>
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-gray-300">{timeAgo(r.created_at)}</span>
                      <button onClick={() => deleteComment(r.id)} disabled={deletingId === r.id}
                        className="text-xs text-red-400 hover:text-red-600 transition-colors disabled:opacity-40">
                        {deletingId === r.id ? "…" : "Delete"}
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
          <Pagination page={visualRepliesPage} pages={visualRepliesPages} onChange={p => loadVisualReplies(p)} />
        </>
      )}
    </div>
  );
}

// ── Pagination ──────────────────────────────────────────────────────────────

function Pagination({ page, pages, onChange }: { page: number; pages: number; onChange: (p: number) => void }) {
  if (pages <= 1) return null;
  return (
    <div className="flex items-center justify-center gap-2 mt-6">
      <button onClick={() => onChange(page - 1)} disabled={page <= 1}
        className="px-3 py-1.5 text-xs rounded-lg border border-gray-200 text-gray-600 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors">
        ← Prev
      </button>
      <span className="text-xs text-gray-400">Page {page} of {pages}</span>
      <button onClick={() => onChange(page + 1)} disabled={page >= pages}
        className="px-3 py-1.5 text-xs rounded-lg border border-gray-200 text-gray-600 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors">
        Next →
      </button>
    </div>
  );
}
