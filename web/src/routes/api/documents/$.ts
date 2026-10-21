import { createFileRoute } from "@tanstack/react-router"
import { proxyDocumentRequest } from "@/lib/proxy.server"

export const Route = createFileRoute("/api/documents/$")({
  server: {
    handlers: {
      GET: ({ request, params }) => proxyDocumentRequest(request, params._splat || ""),
      POST: ({ request, params }) => proxyDocumentRequest(request, params._splat || ""),
      PUT: ({ request, params }) => proxyDocumentRequest(request, params._splat || ""),
      DELETE: ({ request, params }) => proxyDocumentRequest(request, params._splat || ""),
    },
  },
})
