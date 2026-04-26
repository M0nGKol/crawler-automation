import NextAuth from "next-auth";
import Google from "next-auth/providers/google";

const backendUrl = process.env.BACKEND_URL ?? "";

const authHandler = NextAuth({
  providers: [
    Google({
      clientId: process.env.GOOGLE_CLIENT_ID ?? "",
      clientSecret: process.env.GOOGLE_CLIENT_SECRET ?? "",
    }),
  ],
  callbacks: {
    async signIn({ user, account }) {
      if (!user.email || account?.provider !== "google") {
        return false;
      }

      try {
        const response = await fetch(`${backendUrl}/auth/sync`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            email: user.email,
            name: user.name ?? null,
          }),
          cache: "no-store",
        });
        if (!response.ok) return false;
        const data = await response.json();
        (user as unknown as Record<string, unknown>).backendUserId = data.user_id;
        (user as unknown as Record<string, unknown>).sheetId = data.sheet_id;
        (user as unknown as Record<string, unknown>).role = data.role ?? "viewer";
        return true;
      } catch {
        return false;
      }
    },
    async jwt({ token, user }) {
      if (user) {
        token.user_id = (user as unknown as Record<string, unknown>).backendUserId as string | undefined;
        token.sheet_id = (user as unknown as Record<string, unknown>).sheetId as string | undefined;
        token.role = (user as unknown as Record<string, unknown>).role as string | undefined;
      }
      return token;
    },
    async session({ session, token }) {
      (session as unknown as Record<string, unknown>).user_id = token.user_id;
      (session as unknown as Record<string, unknown>).sheet_id = token.sheet_id;
      (session as unknown as Record<string, unknown>).role = token.role ?? "viewer";
      return session;
    },
    async authorized({ auth }) {
      if (!auth?.user?.email) return false;
      try {
        const response = await fetch(`${backendUrl}/auth/sync`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            email: auth.user.email,
            name: auth.user.name ?? null,
          }),
          cache: "no-store",
        });
        return response.ok;
      } catch {
        return false;
      }
    },
  },
});

export const { GET, POST } = authHandler.handlers;
