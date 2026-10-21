import { createFileRoute } from "@tanstack/react-router"
import { proxyAdminRequest } from "@/lib/proxy.server"

export const Route = createFileRoute("/api/admin/$")({
  server: {
    handlers: {
      GET: ({ request, params }) => proxyAdminRequest(request, params._splat || ""),
      POST: ({ request, params }) => proxyAdminRequest(request, params._splat || ""),
      PATCH: ({ request, params }) => proxyAdminRequest(request, params._splat || ""),
      DELETE: ({ request, params }) => proxyAdminRequest(request, params._splat || ""),
    },
  },
})
