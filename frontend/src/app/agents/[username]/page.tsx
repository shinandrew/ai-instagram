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

  return (
    <div>
      <ProfileHeader agent={data.profile} />
      <div className="border-t border-gray-200 pt-6">
        <ProfilePostGrid username={username} initialPosts={data.posts} />
      </div>
    </div>
  );
}
