import { createFileRoute } from "@tanstack/react-router"
import {
  clearSessionCookie,
  isSignedIn,
  matchesCredential,
  sameOrigin,
  sessionCookie,
} from "@/lib/session.server"

export const Route = createFileRoute("/api/session")({
  server: {
    handlers: {
      GET: async ({ request }) =>
        Response.json({ authenticated: isSignedIn(request) }, {
          headers: { "Cache-Control": "no-store" },
        }),
      POST: async ({ request }) => {
        if (!sameOrigin(request)) return Response.json({ error: "Invalid origin" }, { status: 403 })
        if (!process.env.UI_USERNAME || !process.env.UI_PASSWORD || !(
          process.env.UI_SESSION_SECRET || process.env.API_SECRET
        )) return Response.json({ error: "Console credentials are not configured" }, { status: 503 })
        const input = await request.json().catch(() => null) as {
          username?: string; password?: string
        } | null
        if (!input || !matchesCredential(input.username || "", process.env.UI_USERNAME) ||
            !matchesCredential(input.password || "", process.env.UI_PASSWORD)) {
          return Response.json({ error: "Invalid credentials" }, { status: 401 })
        }
        return Response.json({ authenticated: true }, {
          headers: { "Set-Cookie": sessionCookie(request), "Cache-Control": "no-store" },
        })
      },
      DELETE: async ({ request }) => {
        if (!sameOrigin(request)) return Response.json({ error: "Invalid origin" }, { status: 403 })
        return Response.json({ authenticated: false }, {
          headers: { "Set-Cookie": clearSessionCookie(), "Cache-Control": "no-store" },
        })
      },
    },
  },
})
