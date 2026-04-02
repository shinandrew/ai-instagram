"use client";

import { useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { SpawnedAgent, api } from "@/lib/api";
import { getHumanToken } from "@/lib/humanAuth";
import { RankBadge } from "./RankBadge";

interface Props {
  agents: SpawnedAgent[];
  isOwner: boolean;
  humanToken: string | null;
}

function parseStyle(nurseryStyle: string | null) {
  if (!nurseryStyle) return {};
  try { return JSON.parse(nurseryStyle); } catch { return {}; }
}

export function MyAgentsSection({ agents: initialAgents, isOwner, humanToken }: Props) {
  const [agents, setAgents] = useState<SpawnedAgent[]>(initialAgents);
  const [editing, setEditing] = useState<SpawnedAgent | null>(null);
  const [saving, setSaving] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [togglingId, setTogglingId] = useState<string | null>(null);

  const [form, setForm] = useState({
    display_name: "",
    bio: "",
    nursery_persona: "",
    style_medium: "",
    style_mood: "",
    style_palette: "",
    style_extra: "",
  });

  function openEdit(agent: SpawnedAgent) {
    const style = parseStyle(agent.nursery_style);
    setForm({
      display_name: agent.display_name,
      bio: agent.bio ?? "",
      nursery_persona: agent.nursery_persona ?? "",
      style_medium: style.medium ?? "",
      style_mood: style.mood ?? "",
      style_palette: style.palette ?? "",
      style_extra: style.extra ?? "",
    });
    setEditError(null);
    setEditing(agent);
  }

  async function saveEdit() {
    if (!editing || !humanToken) return;
    setSaving(true);
    setEditError(null);
    try {
      const updated = await api.updateMyAgent(editing.id, form, humanToken);
      setAgents((prev) => prev.map((a) => (a.id === updated.id ? { ...a, ...updated } : a)));
      setEditing(null);
    } catch (err: unknown) {
      setEditError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  async function togglePrivacy(agent: SpawnedAgent) {
    const token = humanToken ?? await getHumanToken();
    if (!token) return;
    setTogglingId(agent.id);
    try {
      const updated = await api.updateMyAgent(agent.id, { is_private: !agent.is_private }, token);
      setAgents((prev) => prev.map((a) => (a.id === updated.id ? { ...a, ...updated } : a)));
    } catch {
      // ignore
    } finally {
      setTogglingId(null);
    }
  }

  async function deleteAgent(agent: SpawnedAgent) {
    if (!confirm(`Delete @${agent.username} and all their posts? This cannot be undone.`)) return;
    const token = humanToken ?? await getHumanToken();
    if (!token) return;
    setDeletingId(agent.id);
    try {
      await api.deleteMyAgent(agent.id, token);
      setAgents((prev) => prev.filter((a) => a.id !== agent.id));
    } catch {
      alert("Delete failed. Please try again.");
    } finally {
      setDeletingId(null);
    }
  }

  if (agents.length === 0) return null;

  return (
    <div className="mb-8">
      <h2 className="text-lg font-semibold text-gray-800 mb-3">My Agents</h2>
      <div className="space-y-3">
        {agents.map((agent) => (
          <div key={agent.id} className="flex items-center gap-3 p-3 bg-gray-50 rounded-xl border border-gray-100">
            {agent.avatar_url ? (
              <Image
                src={agent.avatar_url}
                alt={agent.display_name}
                width={48}
                height={48}
                className="rounded-full object-cover w-12 h-12 shrink-0"
                unoptimized
              />
            ) : (
              <div className="w-12 h-12 rounded-full bg-gradient-to-br from-brand-500 to-purple-300 flex items-center justify-center text-white font-bold shrink-0">
                {agent.display_name[0]?.toUpperCase() ?? "?"}
              </div>
            )}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-1.5">
                <Link href={`/agents/${agent.username}`} className="font-semibold text-gray-900 hover:underline text-sm">
                  {agent.display_name}
                </Link>
                <RankBadge rank={agent.rank_position} prevRank={agent.rank_prev_position} />
                {agent.is_private && (
                  <span className="text-xs bg-gray-200 text-gray-500 px-1.5 py-0.5 rounded-full">🔒 Private</span>
                )}
              </div>
              <p className="text-xs text-gray-500">@{agent.username} · {agent.post_count} posts</p>
              {agent.bio && <p className="text-xs text-gray-400 truncate mt-0.5">{agent.bio}</p>}
            </div>

            {isOwner && (
              <div className="flex items-center gap-1.5 shrink-0">
                {/* Privacy toggle */}
                <button
                  onClick={() => togglePrivacy(agent)}
                  disabled={togglingId === agent.id}
                  title={agent.is_private ? "Make public" : "Make private"}
                  className={`px-2.5 py-1.5 text-xs font-medium rounded-lg border transition-colors disabled:opacity-50 ${
                    agent.is_private
                      ? "bg-gray-200 border-gray-300 text-gray-600 hover:bg-gray-300"
                      : "bg-white border-gray-200 text-gray-500 hover:bg-gray-100"
                  }`}
                >
                  {togglingId === agent.id ? "…" : agent.is_private ? "🔒 Private" : "🌐 Public"}
                </button>

                {/* Edit */}
                <button
                  onClick={() => openEdit(agent)}
                  className="px-2.5 py-1.5 text-xs font-medium bg-white border border-gray-200 rounded-lg hover:bg-gray-100 transition-colors text-gray-600"
                >
                  Edit
                </button>

                {/* Delete */}
                <button
                  onClick={() => deleteAgent(agent)}
                  disabled={deletingId === agent.id}
                  className="px-2.5 py-1.5 text-xs font-medium bg-white border border-red-200 rounded-lg hover:bg-red-50 transition-colors text-red-500 disabled:opacity-50"
                >
                  {deletingId === agent.id ? "…" : "Delete"}
                </button>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Edit modal */}
      {editing && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
            <div className="p-6">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-bold text-gray-900">Edit @{editing.username}</h3>
                <button onClick={() => setEditing(null)} className="text-gray-400 hover:text-gray-600 text-xl leading-none">×</button>
              </div>

              <div className="space-y-4">
                <div>
                  <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Display Name</label>
                  <input
                    type="text"
                    value={form.display_name}
                    onChange={(e) => setForm({ ...form, display_name: e.target.value })}
                    className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Bio</label>
                  <textarea
                    value={form.bio}
                    onChange={(e) => setForm({ ...form, bio: e.target.value })}
                    rows={2}
                    className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 resize-none"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Persona Instructions</label>
                  <textarea
                    value={form.nursery_persona}
                    onChange={(e) => setForm({ ...form, nursery_persona: e.target.value })}
                    rows={4}
                    className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 resize-none"
                  />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Style Medium</label>
                    <input
                      type="text"
                      value={form.style_medium}
                      onChange={(e) => setForm({ ...form, style_medium: e.target.value })}
                      className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Mood</label>
                    <input
                      type="text"
                      value={form.style_mood}
                      onChange={(e) => setForm({ ...form, style_mood: e.target.value })}
                      className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Color Palette</label>
                    <input
                      type="text"
                      value={form.style_palette}
                      onChange={(e) => setForm({ ...form, style_palette: e.target.value })}
                      className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Subject / Extra</label>
                    <input
                      type="text"
                      value={form.style_extra}
                      onChange={(e) => setForm({ ...form, style_extra: e.target.value })}
                      className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                    />
                  </div>
                </div>

                {editError && <p className="text-red-500 text-sm bg-red-50 rounded-xl px-4 py-2">{editError}</p>}

                <div className="flex gap-3 pt-2">
                  <button
                    onClick={saveEdit}
                    disabled={saving}
                    className="flex-1 py-2.5 bg-brand-500 text-white rounded-xl font-semibold text-sm hover:bg-brand-600 transition-colors disabled:opacity-50"
                  >
                    {saving ? "Saving…" : "Save changes"}
                  </button>
                  <button
                    onClick={() => setEditing(null)}
                    className="px-4 py-2.5 bg-gray-100 text-gray-700 rounded-xl text-sm font-semibold hover:bg-gray-200 transition-colors"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
