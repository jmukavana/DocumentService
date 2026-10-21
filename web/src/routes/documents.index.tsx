import { Link, createFileRoute } from "@tanstack/react-router"
import { useQuery } from "@tanstack/react-query"
import { flexRender, getCoreRowModel, getSortedRowModel, useReactTable, type ColumnDef, type SortingState } from "@tanstack/react-table"
import { useMemo, useState } from "react"
import { ArrowRight, FileText, Search } from "lucide-react"
import { AppShell } from "@/components/app-shell"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { api, formatBytes, formatDate, statusLabel, type Document, type DocumentList } from "@/lib/api"

export const Route = createFileRoute("/documents/")({ component: DocumentsRoute })

function DocumentsRoute() {
  return <AppShell title="Your document library." subtitle="Find, review, and manage every file processed by the service."><Documents /></AppShell>
}

function Documents() {
  const [search, setSearch] = useState("")
  const [submitted, setSubmitted] = useState("")
  const [status, setStatus] = useState("")
  const [page, setPage] = useState(1)
  const [sorting, setSorting] = useState<SortingState>([])
  const documents = useQuery({
    queryKey: ["documents", "list", submitted, status, page],
    queryFn: () => {
      const params = new URLSearchParams({ page: String(page), page_size: "20" })
      if (submitted) params.set("search", submitted)
      if (status) params.set("status", status)
      return api<DocumentList>(`?${params}`)
    },
    refetchInterval: query => query.state.data?.items.some(item => item.status === "ocr_pending") ? 5_000 : false,
  })
  const columns = useMemo<ColumnDef<Document>[]>(() => [
    { accessorKey: "filename", header: "Document", cell: ({ row }) => <Link className="table-file" to="/documents/$documentId" params={{ documentId: row.original.id }}><span className="file-glyph"><FileText size={17} /></span><span><strong>{row.original.filename}</strong><small>{row.original.mime_type}</small></span></Link> },
    { accessorKey: "status", header: "Status", cell: ({ row }) => <Badge variant="outline" className={`status-${row.original.status}`}>{statusLabel(row.original.status)}</Badge> },
    { accessorKey: "original_size_bytes", header: "Size", cell: ({ row }) => formatBytes(row.original.original_size_bytes) },
    { accessorKey: "created_at", header: "Added", cell: ({ row }) => formatDate(row.original.created_at) },
    { id: "open", header: "", cell: ({ row }) => <Link to="/documents/$documentId" params={{ documentId: row.original.id }} aria-label={`Open ${row.original.filename}`}><ArrowRight size={16} /></Link> },
  ], [])
  const table = useReactTable({ data: documents.data?.items ?? [], columns, state: { sorting }, onSortingChange: setSorting, getCoreRowModel: getCoreRowModel(), getSortedRowModel: getSortedRowModel() })

  return <section className="library-panel">
    <div className="library-toolbar"><form onSubmit={event => { event.preventDefault(); setSubmitted(search.trim()); setPage(1) }} className="search-box"><Search size={17} /><Input aria-label="Search documents" placeholder="Search filenames and extracted text" value={search} onChange={event => setSearch(event.target.value)} /><Button type="submit" variant="secondary">Search</Button></form><select aria-label="Filter by status" value={status} onChange={event => { setStatus(event.target.value); setPage(1) }}><option value="">All statuses</option><option value="ocr_pending">OCR pending</option><option value="ocr_done">OCR complete</option><option value="ocr_failed">OCR failed</option><option value="ready">Ready</option></select></div>
    {documents.isPending ? <div className="p-6 space-y-3"><Skeleton className="h-12 w-full" /><Skeleton className="h-12 w-full" /><Skeleton className="h-12 w-full" /></div> : documents.isError ? <div className="panel-message error-text" role="alert">{documents.error.message} <Button variant="outline" onClick={() => documents.refetch()}>Retry</Button></div> : documents.data?.items.length ? <><div className="table-scroll"><Table><TableHeader>{table.getHeaderGroups().map(group => <TableRow key={group.id}>{group.headers.map(header => <TableHead key={header.id}><button type="button" disabled={!header.column.getCanSort()} onClick={header.column.getToggleSortingHandler()}>{flexRender(header.column.columnDef.header, header.getContext())}</button></TableHead>)}</TableRow>)}</TableHeader><TableBody>{table.getRowModel().rows.map(row => <TableRow key={row.id}>{row.getVisibleCells().map(cell => <TableCell key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</TableCell>)}</TableRow>)}</TableBody></Table></div><div className="table-footer"><span>{documents.data.total} document{documents.data.total === 1 ? "" : "s"}</span><div><Button variant="outline" size="sm" disabled={page === 1} onClick={() => setPage(page - 1)}>Previous</Button><span>Page {page}</span><Button variant="outline" size="sm" disabled={page * 20 >= documents.data.total} onClick={() => setPage(page + 1)}>Next</Button></div></div></> : <div className="empty-library"><FileText size={29} /><strong>No matching documents</strong><p>{submitted || status ? "Try a different search or status filter." : "Ingest your first file from the workbench."}</p><Button asChild variant="outline"><Link to="/">Open workbench</Link></Button></div>}
  </section>
}
