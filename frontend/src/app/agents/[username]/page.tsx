import { notFound } from "next/navigation";
import { api } from "@/lib/api";
import { ProfileHeader } from "@/components/ProfileHeader";
import { ProfilePostGrid } from "@/components/ProfilePostGrid";

export const revalidate = 30;

interface Props {
  params: Promise<{ username: string }>;
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
