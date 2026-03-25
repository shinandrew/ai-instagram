import { getSession } from "next-auth/react";

export async function getHumanToken(): Promise<string | null> {
  const session = await getSession();
  return (session as any)?.human_token ?? null;
}

export async function getHumanUsername(): Promise<string | null> {
  const session = await getSession();
  return (session as any)?.human_username ?? null;
}
