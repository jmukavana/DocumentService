import { createFileRoute } from "@tanstack/react-router"
import { useMutation } from "@tanstack/react-query"
import { useState, type FormEvent } from "react"
import { Check, Clipboard, Code2, KeyRound, Network, Plus } from "lucide-react"
import { AppShell } from "@/components/app-shell"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"

type CreatedCustomer = { id: string; name: string; email: string }
type CreatedKey = { id: string; token: string; key_prefix: string }

export const Route = createFileRoute("/integrations")({ component: IntegrationsRoute })

function IntegrationsRoute() {
  return <AppShell title="Integrations" subtitle="Issue customer access and connect the REST API or MCP tools."><Integrations /></AppShell>
}

function Integrations() {
  const [name, setName] = useState("")
  const [email, setEmail] = useState("")
  const [limit, setLimit] = useState("1000")
  const [issued, setIssued] = useState<{ customer: CreatedCustomer; key: CreatedKey } | null>(null)
  const [copied, setCopied] = useState(false)
  const provision = useMutation({
    mutationFn: async () => {
      const customerResponse = await fetch("/api/admin/customers", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name, email, monthly_request_limit: Number(limit) }) })
      const customer = await customerResponse.json() as CreatedCustomer & { detail?: string }
      if (!customerResponse.ok) throw new Error(customer.detail || "Could not create customer")
      const keyResponse = await fetch(`/api/admin/customers/${customer.id}/keys`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: "primary" }) })
      const key = await keyResponse.json() as CreatedKey & { detail?: string }
      if (!keyResponse.ok) throw new Error(key.detail || "Customer created, but API key issuance failed. Use the administration API to issue a key.")
      return { customer, key }
    },
    onSuccess: data => { setIssued(data); setName(""); setEmail("") },
  })
  const submit = (event: FormEvent) => { event.preventDefault(); setIssued(null); provision.mutate() }

  return <div className="integrations-layout"><section className="integration-panel"><div className="section-heading"><div><p className="section-kicker">CUSTOMER ACCESS</p><h2>Provision a customer</h2></div><KeyRound size={20} /></div><p className="panel-intro">Create an account and issue a scoped key for the extraction API. The full key appears once.</p><form onSubmit={submit} className="provision-form"><label htmlFor="customer-name">Organization</label><Input id="customer-name" value={name} onChange={event => setName(event.target.value)} maxLength={200} required placeholder="Acme Operations" /><label htmlFor="customer-email">Contact email</label><Input id="customer-email" type="email" value={email} onChange={event => setEmail(event.target.value)} required placeholder="ops@acme.example" /><label htmlFor="customer-limit">Monthly request limit</label><Input id="customer-limit" type="number" min="0" value={limit} onChange={event => setLimit(event.target.value)} required /><Button type="submit" disabled={provision.isPending}><Plus size={16} />{provision.isPending ? "Creating…" : "Create customer and key"}</Button>{provision.error && <p className="form-error" role="alert">{provision.error.message}</p>}</form>{issued && <div className="issued-key" role="status"><div><Badge>Issued</Badge><strong>{issued.customer.name}</strong><small>Copy this key now. It cannot be shown again.</small></div><code>{issued.key.token}</code><Button variant="outline" size="sm" onClick={async () => { await navigator.clipboard.writeText(issued.key.token); setCopied(true) }}>{copied ? <Check size={15} /> : <Clipboard size={15} />}{copied ? "Copied" : "Copy key"}</Button></div>}</section><section className="integration-panel"><div className="section-heading"><div><p className="section-kicker">DEVELOPER CHANNELS</p><h2>Connect your tools</h2></div><Network size={20} /></div><div className="endpoint-list"><div><span className="endpoint-icon"><Code2 size={18} /></span><div><strong>REST API</strong><p>Single extraction, bulk extraction, usage and capabilities.</p><code>POST /api/v1/ocr/extract</code><code>POST /api/v1/ocr/bulk</code></div></div><div><span className="endpoint-icon"><Network size={18} /></span><div><strong>Hosted MCP</strong><p>Streamable HTTP endpoint with the same bearer key and quota.</p><code>/mcp/</code><small>Tools: extract_text, extract_bulk, get_ocr_usage, get_capabilities</small></div></div><div><span className="endpoint-icon"><KeyRound size={18} /></span><div><strong>Authentication</strong><p>Send the issued token in the Authorization header over HTTPS.</p><code>Authorization: Bearer ocr_...</code></div></div></div></section></div>
}
