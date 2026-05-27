import React, { useState } from 'react'
import { motion } from 'framer-motion'
import { User, Zap, ChevronDown, ChevronUp } from 'lucide-react'
import { cn, queryTypeLabel, queryTypeBadgeClass } from '@/lib/utils'
import { SourceCard } from './SourceCard'
import type { Message } from '@/store/AppStore'

const ThinkingDots: React.FC = () => (
  <div className="flex items-center gap-1 py-1 dot-anim">
    <span className="w-1.5 h-1.5 bg-accent/70 rounded-full" />
    <span className="w-1.5 h-1.5 bg-accent/70 rounded-full" />
    <span className="w-1.5 h-1.5 bg-accent/70 rounded-full" />
  </div>
)

export const ChatMessage: React.FC<{ message: Message }> = ({ message }) => {
  const [sourcesOpen, setSourcesOpen] = useState(false)
  const isUser = message.role === 'user'

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: 'spring', damping: 20, stiffness: 200 }}
      className={cn('flex gap-3', isUser && 'flex-row-reverse')}
    >
      {/* Avatar */}
      <div className={cn(
        'flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center mt-0.5',
        isUser ? 'bg-surface-4' : 'bg-gradient-to-br from-accent to-blue-700',
      )}>
        {isUser
          ? <User size={13} className="text-subtle" />
          : <Zap size={13} className="text-white" />
        }
      </div>

      {/* Bubble */}
      <div className={cn('flex-1 max-w-[85%]', isUser && 'flex justify-end')}>
        <div className={cn(
          'rounded-2xl px-4 py-2.5 text-[14px] leading-7',
          isUser
            ? 'chat-bubble-user rounded-tr-sm text-slate-200 max-w-[70%]'
            : 'chat-bubble-assistant rounded-tl-sm text-slate-300 max-w-[780px] w-fit',
        )}>
          {message.loading ? (
            <ThinkingDots />
          ) : (
            <div className="space-y-3">
              {!isUser && (
                <div className="text-xs uppercase tracking-wider text-accent font-semibold opacity-80">
                  Answer
                  </div>
                )
              }

  <div className="leading-7 text-[14px] text-slate-200 whitespace-pre-line">
    {message.content
    .replace("PAGE CONTENT:", "")
    .replace("ANSWER:", "")
    .replace("Key points:", "")
    .replace("Supporting text:", "\nSources")
    .replace(/[-]{5,}/g, "")
    .replace(/\n{3,}/g, "\n\n")
    .replace(/\s-\s/g, "\n• ")
    .trim()
    }
  </div>
</div>
          )}
        </div>

        {/* Query type badge + sources */}
        {!isUser && !message.loading && message.queryType && (
          <div className="mt-2 space-y-2">
            <div className="flex items-center gap-2">
              <span className={cn(
                'text-[10px] font-medium rounded-md px-2 py-1',
                queryTypeBadgeClass[message.queryType] ?? 'badge-concept',
              )}>
                {queryTypeLabel[message.queryType] ?? message.queryType} query
              </span>

              {message.sources && message.sources.length > 0 && (
                <button
                  onClick={() => setSourcesOpen(o => !o)}
                  className="flex items-center gap-1 text-[11px] text-subtle hover:text-slate-300 transition-colors"
                >
                  {sourcesOpen ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
                  {message.sources.length} source{message.sources.length !== 1 ? 's' : ''}
                </button>
              )}
            </div>

            {sourcesOpen && message.sources && message.sources.length > 0 && (
              <motion.div
                initial={{ opacity: 0, y: -4 }}
                animate={{ opacity: 1, y: 0 }}
                className="space-y-1.5"
              >
                {message.sources.map((src, i) => (
                  <SourceCard key={i} source={src} index={i} />
                ))}
              </motion.div>
            )}
          </div>
        )}
      </div>
    </motion.div>
  )
}
