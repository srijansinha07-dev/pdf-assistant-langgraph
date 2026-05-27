import React, { useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { MessageSquare, Trash2, FileText, Layers, ScanText } from 'lucide-react'
import { useApp } from '@/store/AppStore'
import { sendChat } from '@/lib/api'
import { ChatMessage } from './ChatMessage'
import { ChatInput } from './ChatInput'
import type { Message } from '@/store/AppStore'

const nanoid = () => Math.random().toString(36).slice(2, 10)

// ── Empty state ────────────────────────────────────────────────────────────

const EmptyState: React.FC = () => (
  <div className="flex-1 flex flex-col items-center justify-center p-8 text-center">
    <motion.div
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ delay: 0.1 }}
    >
      <div className="w-16 h-16 rounded-2xl bg-surface-3 flex items-center justify-center mx-auto mb-4">
        <MessageSquare size={28} className="text-subtle" />
      </div>
      <h2 className="text-base font-semibold text-slate-300 mb-1.5">
        Select a document
      </h2>
      <p className="text-sm text-muted max-w-xs">
        Upload a PDF from the sidebar, then click on it to start asking questions.
      </p>
    </motion.div>
  </div>
)

// ── Active doc header ──────────────────────────────────────────────────────

const DocHeader: React.FC = () => {
  const { state, dispatch } = useApp()
  const doc = state.documents.find(d => d.doc_id === state.activeDocId)
  if (!doc) return null

  return (
    <div className="flex items-center justify-between px-5 py-3.5 border-b border-white/[0.06] bg-surface-1">
      <div className="flex items-center gap-2.5">
        <div className="w-7 h-7 rounded-lg bg-accent/15 flex items-center justify-center">
          <FileText size={13} className="text-accent" />
        </div>
        <div>
          <p className="text-sm font-semibold text-white truncate max-w-xs">{doc.name}</p>
          <div className="flex items-center gap-2 mt-0.5">
            <span className="flex items-center gap-1 text-[10px] text-subtle">
              <Layers size={9} /> {doc.pages} pages
            </span>
            {doc.ocr_pages > 0 && (
              <span className="flex items-center gap-1 text-[10px] badge-ocr rounded px-1.5 py-0.5">
                <ScanText size={9} /> {doc.ocr_pages} OCR'd
              </span>
            )}
          </div>
        </div>
      </div>

      <button
        onClick={() => dispatch({ type: 'CLEAR_MESSAGES' })}
        className="flex items-center gap-1.5 text-[11px] text-subtle hover:text-slate-300 px-2.5 py-1.5 rounded-lg hover:bg-white/[0.05] transition-all"
      >
        <Trash2 size={12} />
        Clear
      </button>
    </div>
  )
}

// ── Chat panel ─────────────────────────────────────────────────────────────

export const ChatPanel: React.FC = () => {
  const { state, dispatch } = useApp()
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const activeDoc = state.documents.find(d => d.doc_id === state.activeDocId)


  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [state.messages])

  const handleSend = async (query: string) => {
    if (!state.activeDocId) return

    // Add user message
    const userId = nanoid()
    const userMsg: Message = { id: userId, role: 'user', content: query }
    dispatch({ type: 'ADD_MESSAGE', payload: userMsg })

    // Add loading assistant message
    const assistantId = nanoid()
    const loadingMsg: Message = {
      id: assistantId, role: 'assistant', content: '', loading: true,
    }
    dispatch({ type: 'ADD_MESSAGE', payload: loadingMsg })
    dispatch({ type: 'SET_LOADING', payload: true })

    try {
      const history = state.messages.map(m => ({ role: m.role, content: m.content }))
      const res     = await sendChat(state.activeDocId, query, history)
      dispatch({
        type: 'UPDATE_MESSAGE',
        payload: {
          id:      assistantId,
          updates: {
            content:   res.answer,
            loading:   false,
            queryType: res.query_type,
            sources:   res.sources,
          },
        },
      })
        } catch (err: any) {
      console.error(
        'CHAT ERROR:',
        err
      )

      const errorMessage =
        err?.response?.data?.detail ||
        err?.response?.data?.answer ||
        err?.message ||
        'Something went wrong.'

      dispatch({
        type: 'UPDATE_MESSAGE',
        payload: {
          id: assistantId,
          updates: {
            content: `Error: ${errorMessage}`,
            loading: false,
          },
        },
      })
    } finally {
      dispatch({ type: 'SET_LOADING', payload: false })
    }
  }

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden">
      {state.activeDocId ? (
        <>
          <DocHeader />

          {/* Messages */}
          <div className="flex-1 overflow-y-auto px-5 py-5">
            <div className="max-w-[850px] mx-auto w-full space-y-5">
            <AnimatePresence initial={false}>
              {state.messages.length === 0 && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="text-center py-10"
                >
                  <p className="text-sm text-muted">
                    Ask anything about <span className="text-slate-400 font-medium">{activeDoc?.name}</span>
                  </p>
                  <p className="text-xs text-muted/70 mt-1">
                    Try formulas, concepts, page queries, or exact text lookups.
                  </p>
                </motion.div>
              )}
              {state.messages.map(msg => (
                <ChatMessage key={msg.id} message={msg} />
              ))}
            </AnimatePresence>
           <div ref={messagesEndRef} />
           </div>
           </div>

          {/* Input */}
          <ChatInput
          onSend={handleSend}
          disabled={!state.activeDocId || activeDoc?.status !== 'ready'}
          loading={state.isLoading}
          suggestions={activeDoc?.suggestions || []}
          />
        </>
      ) : (
        <EmptyState />
      )}
    </div>
  )
}
