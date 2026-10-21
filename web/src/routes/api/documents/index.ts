import { createFileRoute } from "@tanstack/react-router"
import { proxyDocumentRequest } from "@/lib/proxy.server"

export const Route = createFileRoute("/api/documents/")({
  server: {
    handlers: {
      GET: ({ request }) => proxyDocumentRequest(request, ""),
    },
  },
})
