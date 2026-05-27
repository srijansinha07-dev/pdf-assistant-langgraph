import React, { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { ChevronDown, ExternalLink, ScanText, FileText } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useApp } from '@/store/AppStore'
import type { Source } from '@/lib/api'

const ConfidenceDot: React.FC<{ level: string }> = ({ level }) => (
  <span className={cn(
    'inline-flex items-center gap-1 text-[10px] font-medium',
    level === 'high'   && 'text-emerald-400',
    level === 'medium' && 'text-yellow-400',
    level === 'low'    && 'text-red-400',
  )}>
    <span className={cn(
      'w-1.5 h-1.5 rounded-full',
      level === 'high'   && 'bg-emerald-400',
      level === 'medium' && 'bg-yellow-400',
      level === 'low'    && 'bg-red-400',
    )} />
    {level.charAt(0).toUpperCase() + level.slice(1)} confidence
  </span>
)

export const SourceCard: React.FC<{ source: Source; index: number }> = ({ source, index }) => {
  const { dispatch } = useApp()
  const [expanded, setExpanded] = useState(false)

  const openPage = () => {
    dispatch({
      type: 'OPEN_PREVIEW',
      payload: { docId: source.doc_id, page: source.page },
    })
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.05 }}
      className="source-card rounded-xl overflow-hidden"
    >
      {/* Header */}
      <button
        onClick={() => setExpanded(e => !e)}
        className="w-full flex items-center justify-between p-3 text-left hover:bg-white/[0.02] transition-colors"
      >
        <div className="flex items-center gap-2.5 min-w-0">
          <div className="w-7 h-7 rounded-lg bg-surface-3 flex items-center justify-center flex-shrink-0">
            <FileText size={13} className="text-subtle" />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-1.5 flex-wrap">
              <span className="text-[11px] font-semibold text-slate-300">
                Page {source.page}
              </span>
              {source.ocr_sourced && (
                <span className="flex items-center gap-0.5 badge-ocr rounded px-1 py-0.5 text-[9px]">
                  <ScanText size={8} /> OCR
                </span>
              )}
              <ConfidenceDot level={source.confidence} />
            </div>
            <p className="text-[10px] text-muted truncate">{source.doc_name}</p>
          </div>
        </div>
        <ChevronDown
          size={14}
          className={cn('text-muted transition-transform flex-shrink-0 ml-2', expanded && 'rotate-180')}
        />
      </button>

      {/* Expanded text */}
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="px-3 pb-3 border-t border-white/[0.05]">
              <p className="text-[11px] text-slate-400 mt-2.5 leading-relaxed text-sm text-slate-300 leading-7 bg-surface-2 rounded-lg p-2.5">
                {source.text}
              </p>
              <button
                onClick={openPage}
                className="inline-flex items-center gap-2 rounded-xl px-4 py-2 bg-blue-500/10 hover:bg-blue-500/20 border border-blue-500/20 text-blue-300 hover:text-blue-200 transition-all duration-200 hover:scale-[1.02]"
              >
                <ExternalLink size={11} />
                Open source page →
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  )
}
