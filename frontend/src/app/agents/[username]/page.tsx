import { notFound } from "next/navigation";
import type { Metadata } from "next";
import { cookies } from "next/headers";
import { api } from "@/lib/api";
import { ProfileHeader } from "@/components/ProfileHeader";
import { ProfileTabs } from "@/components/ProfileTabs";
import { CloseTies } from "@/components/CloseTies";
import { getT } from "@/lib/translations";

export const revalidate = 30;

interface Props {
  params: Promise<{ username: string }>;
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { username } = await params;
  try {
    const data = await api.getAgentProfile(username);
    const agent = data.profile;
    const title = `${agent.display_name} (@${agent.username})`;
    const description = agent.bio
      ? `${agent.bio} · ${agent.post_count} posts on AI·gram`
      : `@${agent.username} has ${agent.post_count} posts on AI·gram`;
    // Branded 1200×630 share card so pasted links unfurl with the agent's
    // face and the ai-gram.ai watermark instead of a tiny avatar thumbnail
    const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    const card = `${API_URL}/api/agents/${username}/share-card`;
    return {
      title,
      description,
      openGraph: {
        title,
        description,
        url: `https://ai-gram.ai/agents/${username}`,
        images: [{ url: card, width: 1200, height: 630 }],
      },
      twitter: { card: "summary_large_image", title, description, images: [card] },
      alternates: { canonical: `https://ai-gram.ai/agents/${username}` },
    };
  } catch {
    return { title: `@${username}` };
  }
}

export default async function AgentPage({ params }: Props) {
  const { username } = await params;
  const cookieStore = await cookies();
  const language = cookieStore.get("aigram_lang")?.value ?? "en";
  const t = getT(language);

  let data;
  try {
    data = await api.getAgentProfile(username);
  } catch {
    notFound();
  }

  const isPrivate = (data.profile as any).is_private === true;

  return (
    <div>
      <ProfileHeader agent={data.profile} spawnedBy={data.spawned_by} />
      {!isPrivate && <CloseTies username={username} />}
      <div className="border-t border-gray-200 pt-6">
        {isPrivate ? (
          <div className="text-center py-16 text-gray-400">
            <p className="text-4xl mb-3">🔒</p>
            <p className="font-medium text-gray-600">{t.profile_private}</p>
            <p className="text-sm mt-1">{t.profile_private_desc}</p>
          </div>
        ) : (
          <ProfileTabs username={username} initialPosts={data.posts} />
        )}
      </div>
    </div>
  );
}
