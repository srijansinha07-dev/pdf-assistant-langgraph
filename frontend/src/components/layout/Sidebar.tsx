import React, { useCallback, useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useDropzone } from 'react-dropzone'
import {
  FileText, Trash2, Upload, Loader2, CheckCircle2,
  AlertCircle, Clock, ScanText, Layers, Zap
} from 'lucide-react'
import { cn, formatDate } from '@/lib/utils'
import { useApp } from '@/store/AppStore'
import {
  uploadPDF, listDocuments, deleteDocument, getDocument,
  type DocumentInfo
} from '@/lib/api'

// ── Status polling ─────────────────────────────────────────────────────────
const useStatusPolling = (docId: string, status: string) => {
  const { dispatch } = useApp()
  useEffect(() => {
    if (status !== 'processing' && status !== 'pending') return
    const iv = setInterval(async () => {
      try {
        const updated = await getDocument(docId)
        dispatch({ type: 'UPDATE_DOC', payload: updated })
        if (updated.status === 'ready' || updated.status === 'error') {
          clearInterval(iv)
        }
      } catch {}
    }, 2000)
    return () => clearInterval(iv)
  }, [docId, status])
}

// ── Document card ──────────────────────────────────────────────────────────

const StatusIcon: React.FC<{ status: string }> = ({ status }) => {
  if (status === 'ready')      return <CheckCircle2 size={13} className="text-emerald-400" />
  if (status === 'error')      return <AlertCircle  size={13} className="text-red-400" />
  if (status === 'processing') return <Loader2 size={13} className="animate-spin text-accent" />
  return <Clock size={13} className="text-muted" />
}

const DocCard: React.FC<{ doc: DocumentInfo; active: boolean }> = ({ doc, active }) => {
  const { dispatch } = useApp()
  useStatusPolling(doc.doc_id, doc.status)

  const handleDelete = async (e: React.MouseEvent) => {
    e.stopPropagation()
    try {
      await deleteDocument(doc.doc_id)
      dispatch({ type: 'REMOVE_DOC', payload: doc.doc_id })
    } catch {}
  }

  return (
    <motion.div
      layout
      initial={{ opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -10 }}
      onClick={() => doc.status === 'ready' && dispatch({ type: 'SET_ACTIVE_DOC', payload: doc.doc_id })}
      className={cn(
        'group relative rounded-xl p-3 cursor-pointer glass glass-hover transition-all',
        active && 'border-accent/40 bg-accent/5 glow-accent',
        doc.status !== 'ready' && 'opacity-70 cursor-default',
      )}
    >
      {/* Active indicator */}
      {active && (
        <motion.div
          layoutId="active-doc"
          className="absolute left-0 top-3 bottom-3 w-0.5 bg-accent rounded-r-full"
        />
      )}

      <div className="flex items-start gap-2.5">
        <div className={cn(
          'flex-shrink-0 w-8 h-8 rounded-lg flex items-center justify-center mt-0.5',
          active ? 'bg-accent/20' : 'bg-surface-3',
        )}>
          <FileText size={15} className={active ? 'text-accent' : 'text-subtle'} />
        </div>

        <div className="flex-1 min-w-0">
          <p className="text-xs font-medium text-slate-200 truncate leading-tight">
            {doc.name.replace(/\.pdf$/i, '')}
          </p>

          <div className="flex items-center gap-2 mt-1.5 flex-wrap">
            <span className="flex items-center gap-1 text-[10px] text-subtle">
              <Layers size={10} /> {doc.pages}p
            </span>
            {doc.ocr_pages > 0 && (
              <span className="flex items-center gap-1 text-[10px] badge-ocr rounded-md px-1.5 py-0.5">
                <ScanText size={9} /> {doc.ocr_pages} OCR
              </span>
            )}
            {doc.status === 'ready' && (
              <span className="flex items-center gap-1 text-[10px] text-subtle">
                <Zap size={9} /> {doc.chunks} chunks
              </span>
            )}
          </div>

          <div className="flex items-center gap-1 mt-1.5">
            <StatusIcon status={doc.status} />
            <span className="text-[10px] text-subtle capitalize">{doc.status}</span>
          </div>
        </div>

        <button
          onClick={handleDelete}
          className="opacity-0 group-hover:opacity-100 transition-opacity p-1 rounded-md hover:bg-red-500/15 text-muted hover:text-red-400"
        >
          <Trash2 size={12} />
        </button>
      </div>
    </motion.div>
  )
}

// ── Upload zone ────────────────────────────────────────────────────────────

const UploadZone: React.FC = () => {
  const { dispatch } = useApp()

  const onDrop = useCallback(async (files: File[]) => {
    for (const file of files) {
      if (!file.name.toLowerCase().endsWith('.pdf')) continue
      try {
        const doc = await uploadPDF(file)
        dispatch({ type: 'ADD_DOC', payload: doc })
      } catch (err) {
        console.error('Upload failed', err)
      }
    }
  }, [dispatch])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'application/pdf': ['.pdf'] },
    multiple: true,
  })

  return (
    <div
      {...getRootProps()}
      className={cn(
        'rounded-xl border border-dashed p-4 text-center cursor-pointer transition-all',
        isDragActive
          ? 'border-accent bg-accent/10 scale-[0.98]'
          : 'border-white/10 hover:border-accent/40 hover:bg-white/[0.02]',
      )}
    >
      <input {...getInputProps()} />
      <div className={cn(
        'w-9 h-9 rounded-lg mx-auto mb-2.5 flex items-center justify-center transition-colors',
        isDragActive ? 'bg-accent/20' : 'bg-surface-3',
      )}>
        <Upload size={16} className={isDragActive ? 'text-accent' : 'text-subtle'} />
      </div>
      <p className="text-xs font-medium text-slate-300">
        {isDragActive ? 'Drop to upload' : 'Upload PDF'}
      </p>
      <p className="text-[11px] text-muted mt-0.5">Drag & drop or click</p>
    </div>
  )
}

// ── Sidebar ────────────────────────────────────────────────────────────────

export const Sidebar: React.FC = () => {
  const { state, dispatch } = useApp()

  useEffect(() => {
    listDocuments()
      .then(docs => dispatch({ type: 'SET_DOCS', payload: docs }))
      .catch(() => {})
  }, [])

  return (
    <aside className="w-64 flex flex-col h-full border-r border-white/[0.06] bg-surface-1">
      {/* Logo */}
      <div className="px-4 py-5 border-b border-white/[0.06]">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-accent to-blue-700 flex items-center justify-center">
            <Zap size={14} className="text-white" />
          </div>
          <span className="text-sm font-semibold text-white tracking-tight">Lumina</span>
          <span className="text-[10px] bg-accent/20 text-accent px-1.5 py-0.5 rounded-md ml-auto font-medium">
            AI
          </span>
        </div>
        <p className="text-[11px] text-muted mt-1 pl-9">Local PDF Assistant</p>
      </div>

      {/* Upload */}
      <div className="p-3 border-b border-white/[0.06]">
        <UploadZone />
      </div>

      {/* Documents */}
      <div className="flex-1 overflow-y-auto p-3 space-y-1.5">
        <p className="text-[10px] font-semibold text-muted uppercase tracking-wider px-1 mb-2">
          Documents ({state.documents.length})
        </p>
        <AnimatePresence initial={false}>
          {state.documents.map(doc => (
            <DocCard
              key={doc.doc_id}
              doc={doc}
              active={state.activeDocId === doc.doc_id}
            />
          ))}
        </AnimatePresence>
        {state.documents.length === 0 && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="text-center py-8"
          >
            <FileText size={28} className="text-surface-4 mx-auto mb-2" />
            <p className="text-xs text-muted">No documents yet</p>
          </motion.div>
        )}
      </div>

      {/* Footer */}
      <div className="p-3 border-t border-white/[0.06]">
        <p className="text-[10px] text-muted text-center">
          All processing is local · No cloud
        </p>
      </div>
    </aside>
  )
}
