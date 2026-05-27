import React from 'react'
import { AppProvider } from './store/AppStore'
import { Sidebar } from './components/layout/Sidebar'
import { ChatPanel } from './components/chat/ChatPanel'
import { PagePreviewModal } from './components/pdf/PagePreview'

const App: React.FC = () => (
  <AppProvider>
    <div className="flex h-screen w-screen overflow-hidden bg-surface-0 bg-grid-pattern">
      {/* Ambient glow */}
      <div className="fixed inset-0 bg-glow-top pointer-events-none z-0" />

      <div className="relative z-10 flex w-full h-full">
        <Sidebar />
        <main className="flex-1 flex flex-col h-full overflow-hidden">
          <ChatPanel />
        </main>
      </div>

      <PagePreviewModal />
    </div>
  </AppProvider>
)

export default App
