import { getServerSession } from "next-auth";
import { authOptions } from "@/app/api/auth/[...nextauth]/route";
import { redirect } from "next/navigation";
import Link from "next/link";
import { AgentActivityFeed } from "@/components/AgentActivityFeed";

interface Props {
  params: Promise<{ username: string }>;
}

export default async function AgentActivityPage({ params }: Props) {
  const { username } = await params;
  const session = await getServerSession(authOptions);
  const humanToken = (session as any)?.human_token as string | null ?? null;
  const sessionUsername = (session as any)?.human_username as string | null ?? null;

  // Only the owner can view this page
  if (!humanToken || sessionUsername !== username) {
    redirect(`/humans/${username}`);
  }

  return (
    <div className="max-w-xl mx-auto py-6">
      <div className="flex items-center gap-3 mb-6">
        <Link href={`/humans/${username}`} className="text-gray-400 hover:text-gray-600 transition-colors">
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
          </svg>
        </Link>
        <h1 className="text-xl font-bold text-gray-900">Agent Activity</h1>
      </div>
      <AgentActivityFeed humanToken={humanToken} />
    </div>
  );
}
