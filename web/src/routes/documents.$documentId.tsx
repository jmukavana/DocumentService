import { Link, createFileRoute, useNavigate } from "@tanstack/react-router"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ArrowLeft, Download, FileText, RotateCw, Trash2 } from "lucide-react"
import { AppShell } from "@/components/app-shell"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { api, formatBytes, formatConfidence, formatDate, statusLabel, type Document } from "@/lib/api"

type OcrResult = { extracted_text: string | null; language: string; confidence: number | null; processed_at: string | null }
type Version = { id: string; version_no: number; size_bytes: number; created_at: string; change_note: string | null }

export const Route = createFileRoute("/documents/$documentId")({ component: DocumentRoute })

function DocumentRoute() {
  const { documentId } = Route.useParams()
  return <AppShell title="Document details." subtitle="Review the file, extracted text, and version history."><Detail id={documentId} /></AppShell>
}

function Detail({ id }: { id: string }) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const document = useQuery({ queryKey: ["document", id], queryFn: () => api<Document>(id), refetchInterval: query => query.state.data?.status === "ocr_pending" ? 4_000 : false })
  const ocr = useQuery({ queryKey: ["ocr", id], queryFn: () => api<OcrResult>(`${id}/ocr`), enabled: document.data?.status === "ocr_done" })
  const versions = useQuery({ queryKey: ["versions", id], queryFn: () => api<Version[]>(`${id}/versions`) })
  const retry = useMutation({ mutationFn: () => api<{ status: string }>(`${id}/extract`, { method: "POST" }), onSuccess: () => queryClient.invalidateQueries({ queryKey: ["document", id] }) })
  const remove = useMutation({ mutationFn: () => api<void>(id, { method: "DELETE" }), onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["documents"] }); queryClient.removeQueries({ queryKey: ["document", id] }); navigate({ to: "/documents" }) } })

  return <div className="detail-layout"><Link to="/documents" className="back-link"><ArrowLeft size={16} /> Back to library</Link>{document.isPending ? <Skeleton className="h-80 w-full" /> : document.isError ? <div className="feedback error" role="alert">{document.error.message}<Button onClick={() => document.refetch()}>Retry</Button></div> : <><section className="detail-main"><div className="detail-title"><span className="file-glyph large"><FileText size={23} /></span><div><h2>{document.data.filename}</h2><p>{document.data.mime_type}</p></div><Badge variant="outline" className={`status-${document.data.status}`}>{statusLabel(document.data.status)}</Badge></div><div className="detail-actions"><Button asChild variant="outline"><a href={`/api/documents/${id}/download`}><Download size={16} /> Download</a></Button>{(document.data.status === "ocr_failed" || document.data.status === "ready") && <Button variant="outline" disabled={retry.isPending} onClick={() => retry.mutate()}><RotateCw size={16} /> {document.data.status === "ready" ? "Extract text" : "Retry OCR"}</Button>}<Button variant="destructive" disabled={remove.isPending || document.data.status === "deleted"} onClick={() => { if (window.confirm(`Delete ${document.data.filename}?`)) remove.mutate() }}><Trash2 size={16} /> Delete</Button></div>{(retry.error || remove.error) && <p className="form-error" role="alert">{(retry.error || remove.error)?.message}</p>}<div className="metadata-grid"><div><span>Added</span><strong>{formatDate(document.data.created_at)}</strong></div><div><span>Original size</span><strong>{formatBytes(document.data.original_size_bytes)}</strong></div><div><span>Stored size</span><strong>{formatBytes(document.data.size_bytes)}</strong></div><div><span>Department</span><strong>{document.data.department_id || "—"}</strong></div></div></section><section className="detail-section"><div className="section-heading"><div><p className="section-kicker">CONTENT</p><h2>Extracted text</h2></div></div>{document.data.status === "ocr_pending" ? <p className="panel-message">OCR is processing. This view will refresh automatically.</p> : document.data.status === "ocr_failed" ? <p className="panel-message error-text">OCR did not complete. Retry the job above.</p> : document.data.status === "ocr_done" ? ocr.isPending ? <p className="panel-message">Loading text…</p> : ocr.isError ? <p className="panel-message error-text">{ocr.error.message} <button onClick={() => ocr.refetch()}>Retry</button></p> : <><p className="ocr-meta">{ocr.data?.language.toUpperCase()} · {ocr.data?.processed_at ? formatDate(ocr.data.processed_at) : "Processed"} · Confidence {formatConfidence(ocr.data?.confidence)}</p><pre className="text-output">{ocr.data?.extracted_text || "No text detected."}</pre></> : <p className="panel-message">This file is saved. Use Extract text to process a supported stored format.</p>}</section><section className="detail-section"><div className="section-heading"><div><p className="section-kicker">HISTORY</p><h2>Versions</h2></div></div>{versions.isPending ? <p className="panel-message">Loading versions…</p> : versions.isError ? <p className="panel-message error-text">{versions.error.message}</p> : versions.data?.length ? versions.data.map(version => <div className="version-row" key={version.id}><span>v{version.version_no}</span><strong>{formatDate(version.created_at)}</strong><small>{formatBytes(version.size_bytes)}</small><small>{version.change_note || "—"}</small></div>) : <p className="panel-message">No additional versions yet.</p>}</section></>}</div>
}
