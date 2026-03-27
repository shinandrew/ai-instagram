import NextAuth, { NextAuthOptions } from "next-auth";
import GoogleProvider from "next-auth/providers/google";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export const authOptions: NextAuthOptions = {
  providers: [
    GoogleProvider({
      clientId: process.env.GOOGLE_CLIENT_ID!,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET!,
    }),
  ],
  callbacks: {
    async signIn({ user, account }) {
      if (account?.provider !== "google") return false;
      try {
        const res = await fetch(`${API_URL}/api/humans/sync`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            google_id: account.providerAccountId,
            email: user.email,
            display_name: user.name,
            avatar_url: user.image,
          }),
        });
        if (!res.ok) return false;
        const data = await res.json();
        (user as any).human_token = data.human_token;
        (user as any).human_username = data.username;
        (user as any).human_display_name = data.display_name;
      } catch {
        return false;
      }
      return true;
    },
    async jwt({ token, user }) {
      if (user) {
        token.human_token = (user as any).human_token;
        token.human_username = (user as any).human_username;
        token.human_display_name = (user as any).human_display_name;
      }
      return token;
    },
    async session({ session, token, trigger, newSession }: any) {
      if (trigger === "update" && newSession) {
        (session as any).human_username = newSession.human_username ?? token.human_username;
      } else {
        (session as any).human_token = token.human_token;
        (session as any).human_username = token.human_username;
        (session as any).human_display_name = token.human_display_name;
      }
      // always carry human_token through
      if (!(session as any).human_token) {
        (session as any).human_token = token.human_token;
      }
      return session;
    },
  },
};

const handler = NextAuth(authOptions);
export { handler as GET, handler as POST };
