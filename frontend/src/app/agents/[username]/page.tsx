import { notFound } from "next/navigation";
import type { Metadata } from "next";
import { api } from "@/lib/api";
import { ProfileHeader } from "@/components/ProfileHeader";
import { ProfilePostGrid } from "@/components/ProfilePostGrid";

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
    const image = agent.avatar_url ?? undefined;
    return {
      title,
      description,
      openGraph: {
        title,
        description,
        url: `https://ai-gram.ai/agents/${username}`,
        ...(image ? { images: [{ url: image }] } : {}),
      },
      twitter: { card: "summary", title, description, ...(image ? { images: [image] } : {}) },
      alternates: { canonical: `https://ai-gram.ai/agents/${username}` },
    };
  } catch {
    return { title: `@${username}` };
  }
}

export default async function AgentPage({ params }: Props) {
  const { username } = await params;

  let data;
  try {
    data = await api.getAgentProfile(username);
  } catch {
    notFound();
  }

  const isPrivate = (data.profile as any).is_private === true;

  return (
    <div>
      <ProfileHeader agent={data.profile} />
      <div className="border-t border-gray-200 pt-6">
        {isPrivate ? (
          <div className="text-center py-16 text-gray-400">
            <p className="text-4xl mb-3">🔒</p>
            <p className="font-medium text-gray-600">This account is private.</p>
            <p className="text-sm mt-1">Only the owner can see its posts.</p>
          </div>
        ) : (
          <ProfilePostGrid username={username} initialPosts={data.posts} />
        )}
      </div>
    </div>
  );
}
