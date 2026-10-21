import { createFileRoute } from "@tanstack/react-router"
import { AppShell } from "@/components/app-shell"
import { Workbench } from "@/components/workbench"

export const Route = createFileRoute("/")({ component: App })

function App() {
  return <AppShell title="Extract text from your files." subtitle="Save one file or a batch. OCR runs for PDFs and images; supported text documents are ready immediately."><Workbench /></AppShell>
}
