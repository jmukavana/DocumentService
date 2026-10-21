import { Link } from "@tanstack/react-router"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useRef, useState, type DragEvent } from "react"
import {
  ArrowRight, Check, Clipboard, CloudUpload, FileCheck2, FileText,
  LoaderCircle, ScanText, X,
} from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  api, formatBytes, formatConfidence, formatDate, statusLabel,
  type BulkResponse, type DirectResult, type Document, type DocumentList,
} from "@/lib/api"

type StoredOcr = { extracted_text: string | null; language: string; confidence: number | null }

export function Workbench() {
  const [files, setFiles] = useState<File[]>([])
  const [dragging, setDragging] = useState(false)
  const [copied, setCopied] = useState(false)
  const [direct, setDirect] = useState<DirectResult | null>(null)
  const [saved, setSaved] = useState<BulkResponse | null>(null)
  const picker = useRef<HTMLInputElement>(null)
  const queryClient = useQueryClient()

  const recent = useQuery({
    queryKey: ["documents", "recent"],
    queryFn: () => api<DocumentList>("?page_size=5"),
    refetchInterval: query => query.state.data?.items.some(item => item.status === "ocr_pending")
      ? 5_000 : false,
  })
  const savedId = saved?.items.length === 1 ? saved.items[0].document_id : undefined
  const storedDocument = useQuery({
    queryKey: ["document", savedId],
    queryFn: () => api<Document>(savedId!),
    enabled: Boolean(savedId),
    refetchInterval: query => query.state.data?.status === "ocr_pending" ? 4_000 : false,
  })
  const storedOcr = useQuery({
    queryKey: ["ocr", savedId],
    queryFn: () => api<StoredOcr>(`${savedId}/ocr`),
    enabled: Boolean(savedId && storedDocument.data?.status === "ocr_done"),
  })

  const save = useMutation({
    mutationFn: async (items: File[]) => {
      if (items.length === 1) {
        const form = new FormData()
        form.append("file", items[0])
        const document = await api<Document>("upload", { method: "POST", body: form })
        return {
          accepted: 1, skipped: 0, failed: 0,
          items: [{ filename: document.filename, status: "accepted",
            document_id: document.id, document_status: document.status }],
        } satisfies BulkResponse
      }
      const form = new FormData()
      for (const file of items) form.append("files", file)
      return api<BulkResponse>("bulk-upload", { method: "POST", body: form })
    },
    onSuccess: data => {
      setSaved(data)
      setDirect(null)
      queryClient.invalidateQueries({ queryKey: ["documents"] })
    },
  })
  const extractOnly = useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData()
      form.append("file", file)
      return api<DirectResult>("ocr/upload", { method: "POST", body: form })
    },
    onSuccess: data => { setDirect(data); setSaved(null) },
  })
  const retryStored = useMutation({
    mutationFn: () => api<{ status: string }>(`${savedId}/extract`, { method: "POST" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["document", savedId] }),
  })

  const busy = save.isPending || extractOnly.isPending
  const error = save.error || extractOnly.error || retryStored.error
  const addFiles = (incoming: FileList | File[]) => {
    setFiles(current => [...current, ...Array.from(incoming)].slice(0, 20))
    setSaved(null)
    setDirect(null)
    setCopied(false)
  }
  const drop = (event: DragEvent) => {
    event.preventDefault()
    setDragging(false)
    addFiles(event.dataTransfer.files)
  }
  const copy = async (text: string) => {
    await navigator.clipboard.writeText(text)
    setCopied(true)
  }

  return <div className="workbench-layout">
    <section className="work-panel" aria-labelledby="upload-title">
      <div className="section-heading"><div><p className="section-kicker">01 / ADD FILES</p><h2 id="upload-title">Save and extract</h2></div><Badge variant="outline">Up to 20 files</Badge></div>
      <p className="panel-intro">Save files to your library. OCR starts automatically for PDFs and images; text from supported documents is available immediately.</p>
      <div className={`dropzone ${dragging ? "is-dragging" : ""}`} onDragOver={event => { event.preventDefault(); setDragging(true) }} onDragLeave={() => setDragging(false)} onDrop={drop}>
        <input ref={picker} type="file" multiple className="sr-only" id="file-input" onChange={event => { if (event.target.files) addFiles(event.target.files); event.target.value = "" }} />
        <div className="drop-icon"><CloudUpload size={24} strokeWidth={1.7} /></div>
        <p className="drop-title">Drop files here</p>
        <p className="drop-subtitle">Any file type can be stored · up to 100 MB per file</p>
        <Button variant="outline" onClick={() => picker.current?.click()}>Choose files</Button>
      </div>
      {files.length > 0 && <div className="selected-files" aria-label="Selected files">{files.map((file, index) => <div className="selected-file" key={`${file.name}-${index}`}><FileText size={17} /><span title={file.name}>{file.name}</span><small>{formatBytes(file.size)}</small><button type="button" aria-label={`Remove ${file.name}`} onClick={() => setFiles(items => items.filter((_, i) => i !== index))}><X size={15} /></button></div>)}</div>}
      <div className="upload-actions"><p>{files.length === 1 ? "The saved file will appear in your library." : "Batch uploads are saved individually, with status for each file."}</p><div className="upload-buttons"><Button variant="outline" disabled={files.length !== 1 || busy} onClick={() => extractOnly.mutate(files[0])}>Extract only</Button><Button size="lg" disabled={!files.length || busy} onClick={() => save.mutate(files)}>{busy ? <><LoaderCircle className="animate-spin" /> Processing…</> : <>Save &amp; extract <ArrowRight /></>}</Button></div></div>
      {error && <div className="feedback error" role="alert">{error.message}</div>}
    </section>

    <section className="result-panel" aria-live="polite">
      <div className="section-heading"><div><p className="section-kicker">02 / RESULT</p><h2>{saved ? "Saved files" : "Extracted text"}</h2></div>{(direct || saved) && <Badge variant="outline"><Check size={12} /> {saved ? "Saved" : "Complete"}</Badge>}</div>
      {direct ? <div className="result-content"><div className="result-meta"><span>{direct.filename}</span><span>{direct.page_count} {direct.page_count === 1 ? "page" : "pages"}</span><span>{direct.language.toUpperCase()}</span><span>Confidence {formatConfidence(direct.confidence)}</span></div><div className="result-toolbar"><strong>Text</strong><Button size="sm" variant="ghost" onClick={() => copy(direct.extracted_text)}>{copied ? <Check /> : <Clipboard />}{copied ? "Copied" : "Copy"}</Button></div><pre className="text-output">{direct.extracted_text || "No text was detected in this file."}</pre></div> : saved ? <div className="bulk-results"><div className="bulk-summary"><strong>{saved.accepted} saved</strong><span>{saved.skipped} duplicate</span><span>{saved.failed} failed</span></div>{saved.items.map((item, index) => <div className="bulk-row" key={`${item.filename}-${index}`}><FileCheck2 size={17} /><div><strong>{item.filename}</strong><small>{item.error || (item.document_id === savedId && storedDocument.data ? statusLabel(storedDocument.data.status) : statusLabel(item.document_status || item.status))}</small></div>{item.document_id && <Link to="/documents/$documentId" params={{ documentId: item.document_id }} aria-label={`Open ${item.filename}`}><ArrowRight size={16} /></Link>}</div>)}{savedId && storedDocument.data?.status === "ocr_pending" && <p className="panel-message">OCR is processing. This result updates automatically.</p>}{savedId && storedDocument.data?.status === "ocr_failed" && <div className="result-toolbar"><span>OCR failed.</span><Button variant="outline" size="sm" disabled={retryStored.isPending} onClick={() => retryStored.mutate()}>Retry OCR</Button></div>}{savedId && storedDocument.data?.status === "ready" && <div className="result-toolbar"><span>Stored without extracted text.</span><Button variant="outline" size="sm" disabled={retryStored.isPending} onClick={() => retryStored.mutate()}>Try extraction</Button></div>}{savedId && storedDocument.data?.status === "ocr_done" && (storedOcr.isPending ? <p className="panel-message">Loading extracted text…</p> : storedOcr.isError ? <p className="panel-message error-text">{storedOcr.error.message}</p> : <><div className="result-toolbar"><strong>Text · Confidence {formatConfidence(storedOcr.data?.confidence)}</strong><Button size="sm" variant="ghost" onClick={() => copy(storedOcr.data?.extracted_text || "")}>{copied ? <Check /> : <Clipboard />}{copied ? "Copied" : "Copy"}</Button></div><pre className="text-output">{storedOcr.data?.extracted_text || "No text was detected in this file."}</pre></>)}</div> : <div className="result-empty"><div><ScanText size={27} strokeWidth={1.5} /></div><strong>Ready for your files</strong><p>Saved files and extraction results appear here.</p></div>}
    </section>

    <section className="recent-panel"><div className="section-heading"><div><p className="section-kicker">LIBRARY</p><h2>Latest documents</h2></div><Button asChild variant="ghost" size="sm"><Link to="/documents">View library <ArrowRight size={15} /></Link></Button></div>{recent.isPending ? <p className="panel-message">Loading documents…</p> : recent.isError ? <p className="panel-message error-text">{recent.error.message} <button onClick={() => recent.refetch()}>Retry</button></p> : recent.data?.items.length ? <div className="recent-list">{recent.data.items.map(document => <Link className="recent-row" to="/documents/$documentId" params={{ documentId: document.id }} key={document.id}><span className="file-glyph"><FileText size={18} /></span><span className="recent-name"><strong>{document.filename}</strong><small>{formatDate(document.created_at)} · {formatBytes(document.original_size_bytes)}</small></span><Badge variant="outline">{statusLabel(document.status)}</Badge><ArrowRight size={15} /></Link>)}</div> : <p className="panel-message">No documents yet. Save your first file above.</p>}</section>
  </div>
}
