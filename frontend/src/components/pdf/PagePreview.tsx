import React, { useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { X, ScanText, FileText, ChevronLeft, ChevronRight } from 'lucide-react'
import { useApp } from '@/store/AppStore'
import { getPagePreview, type PagePreview } from '@/lib/api'

export const PagePreviewModal: React.FC = () => {
  const { state, dispatch } = useApp()
  const { pagePreviewDoc, pagePreviewNum } = state
  const [preview, setPreview]   = useState<PagePreview | null>(null)
  const [loading, setLoading]   = useState(false)

  const doc = state.documents.find(d => d.doc_id === pagePreviewDoc)

  useEffect(() => {
    if (!pagePreviewDoc || !pagePreviewNum) { setPreview(null); return }
    setLoading(true)
    getPagePreview(pagePreviewDoc, pagePreviewNum)
      .then(setPreview)
      .catch(() => setPreview(null))
      .finally(() => setLoading(false))
  }, [pagePreviewDoc, pagePreviewNum])

  const close = () => dispatch({ type: 'CLOSE_PREVIEW' })

  const changePage = (delta: number) => {
    if (!pagePreviewDoc || !pagePreviewNum || !doc) return
    const next = pagePreviewNum + delta
    if (next < 1 || next > doc.pages) return
    dispatch({ type: 'OPEN_PREVIEW', payload: { docId: pagePreviewDoc, page: next } })
  }

  return (
    <AnimatePresence>
      {pagePreviewDoc && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          style={{ backdropFilter: 'blur(8px)', background: 'rgba(8,11,16,0.85)' }}
          onClick={close}
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.94, y: 12 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.94, y: 12 }}
            transition={{ type: 'spring', damping: 25, stiffness: 260 }}
            className="glass rounded-2xl w-full max-w-3xl max-h-[90vh] flex flex-col overflow-hidden"
            onClick={e => e.stopPropagation()}
          >
            {/* Header */}
            <div className="flex items-center justify-between px-5 py-4 border-b border-white/[0.07]">
              <div className="flex items-center gap-2.5">
                <FileText size={16} className="text-accent" />
                <div>
                  <p className="text-sm font-semibold text-white">
                    Page {pagePreviewNum}
                  </p>
                  {doc && (
                    <p className="text-[11px] text-muted truncate max-w-xs">{doc.name}</p>
                  )}
                </div>
                {preview?.ocr_used && (
                  <span className="flex items-center gap-1 text-[10px] badge-ocr rounded-md px-1.5 py-0.5">
                    <ScanText size={9} /> OCR
                  </span>
                )}
              </div>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => changePage(-1)}
                  disabled={pagePreviewNum === 1}
                  className="p-1.5 rounded-lg hover:bg-white/[0.06] text-subtle disabled:opacity-30 transition-colors"
                >
                  <ChevronLeft size={16} />
                </button>
                <span className="text-xs text-muted px-1">
                  {pagePreviewNum} / {doc?.pages ?? '?'}
                </span>
                <button
                  onClick={() => changePage(1)}
                  disabled={pagePreviewNum === doc?.pages}
                  className="p-1.5 rounded-lg hover:bg-white/[0.06] text-subtle disabled:opacity-30 transition-colors"
                >
                  <ChevronRight size={16} />
                </button>
                <button
                  onClick={close}
                  className="ml-2 p-1.5 rounded-lg hover:bg-white/[0.06] text-subtle transition-colors"
                >
                  <X size={16} />
                </button>
              </div>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-auto p-5">
              {loading ? (
                <div className="flex items-center justify-center h-40">
                  <div className="w-6 h-6 border-2 border-accent border-t-transparent rounded-full animate-spin" />
                </div>
              ) : preview?.image_b64 ? (
                <img
                  src={`data:image/png;base64,${preview.image_b64}`}
                  alt={`Page ${pagePreviewNum}`}
                  className="w-full rounded-xl border border-white/[0.07] shadow-xl"
                />
              ) : preview?.text ? (
                <pre className="text-xs text-slate-300 font-mono whitespace-pre-wrap leading-relaxed">
                  {preview.text || '(No text extracted from this page)'}
                </pre>
              ) : (
                <p className="text-sm text-muted text-center py-12">
                  Could not load page preview.
                </p>
              )}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
