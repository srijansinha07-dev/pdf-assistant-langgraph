import React, { useState, useRef, useEffect } from 'react'
import { motion } from 'framer-motion'
import { Send, Sparkles } from 'lucide-react'
import { cn } from '@/lib/utils'

interface Props {
  onSend: (query: string) => void
  disabled: boolean
  loading: boolean
  suggestions?: string[]
}



export const ChatInput: React.FC<Props> = ({
  onSend,
  disabled,
  loading,
  suggestions = [],
}) => {
  const [value, setValue] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 160)}px`
    }
  }, [value])

  const handleSend = () => {
    const q = value.trim()
    if (!q || disabled || loading) return
    onSend(q)
    setValue('')
  }

  const handleKey = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  
  return (
    <div className="border-t border-white/[0.06] bg-surface-1 px-4 py-4">
      {/* Suggestion chips — shown when input is empty */}
      {!value && !loading && suggestions.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex gap-1.5 flex-wrap mb-3"
        >
          

          {suggestions.map(s => (
            <button
              key={s}
              onClick={() => { setValue(s); textareaRef.current?.focus() }}
              disabled={disabled}
              className="text-[11px] text-subtle hover:text-slate-300 border border-white/[0.07] hover:border-accent/30 rounded-full px-2.5 py-1 transition-all disabled:opacity-40"
            >
              {s}
            </button>
          ))}
        </motion.div>
      )}

      {/* Input */}
      <div className={cn(
        'flex items-end gap-2.5 glass rounded-2xl px-4 py-3 transition-all',
        !disabled && 'focus-within:border-accent/40 focus-within:bg-accent/5',
      )}>
        <Sparkles size={15} className="text-subtle mb-0.5 flex-shrink-0" />

        <textarea
          ref={textareaRef}
          value={value}
          onChange={e => setValue(e.target.value)}
          onKeyDown={handleKey}
          disabled={disabled || loading}
          placeholder={disabled ? 'Select a document to begin…' : 'Ask anything about the document…'}
          rows={1}
          className="flex-1 bg-transparent text-sm text-slate-200 placeholder-muted resize-none outline-none leading-relaxed min-h-[20px] disabled:cursor-not-allowed"
        />

        <motion.button
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          onClick={handleSend}
          disabled={!value.trim() || disabled || loading}
          className={cn(
            'flex-shrink-0 w-8 h-8 rounded-xl flex items-center justify-center transition-all mb-0.5',
            value.trim() && !disabled && !loading
              ? 'bg-accent text-white shadow-lg shadow-accent/30'
              : 'bg-surface-3 text-muted cursor-not-allowed',
          )}
        >
          {loading
            ? <div className="w-3.5 h-3.5 border-2 border-current border-t-transparent rounded-full animate-spin" />
            : <Send size={13} />
          }
        </motion.button>
      </div>

      <p className="text-[10px] text-muted text-center mt-2">
        Enter to send · Shift+Enter for newline
      </p>
    </div>
  )
}
