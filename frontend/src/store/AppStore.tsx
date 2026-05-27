import React, { createContext, useContext, useReducer } from 'react'
import type { DocumentInfo, Source, ChatResponse } from '@/lib/api'

const STORAGE_KEY =
  'pdf-assistant-chats'

function loadPersistedChats() {
  try {
    const saved =
      localStorage.getItem(
        STORAGE_KEY
      )

    return saved
      ? JSON.parse(saved)
      : {}

  } catch {
    return {}
  }
}

function persistChats(
  chats: Record<string, Message[]>
) {
  try {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify(chats)
    )
  } catch {
    // ignore storage errors
  }
}

// ── Types ──────────────────────────────────────────────────────────────────

export interface Message {
  id:         string
  role:       'user' | 'assistant'
  content:    string
  queryType?: string
  sources?:   Source[]
  loading?:   boolean
}

export interface AppState {
  documents:      DocumentInfo[]
  activeDocId:    string | null

  // currently visible messages
  messages:       Message[]

  // chat history per document
  chats:          Record<string, Message[]>

  isLoading:      boolean
  pagePreviewDoc: string | null
  pagePreviewNum: number | null
}

type Action =
  | { type: 'SET_DOCS';        payload: DocumentInfo[] }
  | { type: 'ADD_DOC';         payload: DocumentInfo }
  | { type: 'UPDATE_DOC';      payload: DocumentInfo }
  | { type: 'REMOVE_DOC';      payload: string }
  | { type: 'SET_ACTIVE_DOC';  payload: string | null }
  | { type: 'ADD_MESSAGE';     payload: Message }
  | { type: 'UPDATE_MESSAGE';  payload: { id: string; updates: Partial<Message> } }
  | { type: 'SET_LOADING';     payload: boolean }
  | { type: 'CLEAR_MESSAGES' }
  | { type: 'OPEN_PREVIEW';    payload: { docId: string; page: number } }
  | { type: 'CLOSE_PREVIEW' }

// ── Reducer ────────────────────────────────────────────────────────────────

const init: AppState = {
  documents:      [],
  activeDocId:    null,
  messages:       [],
  chats:          loadPersistedChats(),
  isLoading:      false,
  pagePreviewDoc: null,
  pagePreviewNum: null,
}

function reducer(
  state: AppState,
  action: Action
): AppState {

  switch (action.type) {

    case 'SET_DOCS':
      return {
        ...state,
        documents: action.payload,
      }

    case 'ADD_DOC':
      return {
        ...state,
        documents: [
          action.payload,
          ...state.documents,
        ],
      }

    case 'UPDATE_DOC':
      return {
        ...state,
        documents: state.documents.map(
          doc =>
            doc.doc_id === action.payload.doc_id
              ? action.payload
              : doc
        ),
      }

    case 'REMOVE_DOC':
      return {
        ...state,

        documents: state.documents.filter(
          d => d.doc_id !== action.payload
        ),

        activeDocId:
          state.activeDocId === action.payload
            ? null
            : state.activeDocId,
      }

    case 'SET_ACTIVE_DOC':
      return {
        ...state,
        activeDocId: action.payload,

        // restore saved chat
        messages: action.payload
          ? state.chats[action.payload] || []
          : [],
      }

    case 'ADD_MESSAGE': {
      const updatedMessages = [
        ...state.messages,
        action.payload,
      ]

      const docId =
        state.activeDocId

      const updatedChats = docId
        ? {
            ...state.chats,
            [docId]: updatedMessages,
          }
        : state.chats

      persistChats(
        updatedChats
      )

      return {
        ...state,
        messages: updatedMessages,
        chats: updatedChats,
      }
    }

    case 'UPDATE_MESSAGE': {
      const updatedMessages =
        state.messages.map(
          msg =>
            msg.id === action.payload.id
              ? {
                  ...msg,
                  ...action.payload.updates,
                }
              : msg
        )

      const docId =
        state.activeDocId

      const updatedChats = docId
        ? {
            ...state.chats,
            [docId]: updatedMessages,
          }
        : state.chats

      persistChats(
        updatedChats
      )

      return {
        ...state,
        messages: updatedMessages,
        chats: updatedChats,
      }
    }

    case 'SET_LOADING':
      return {
        ...state,
        isLoading: action.payload,
      }

    case 'CLEAR_MESSAGES': {
      const docId =
        state.activeDocId

      const updatedChats = docId
        ? {
            ...state.chats,
            [docId]: [],
          }
        : state.chats

      persistChats(
        updatedChats
      )

      return {
        ...state,
        messages: [],
        chats: updatedChats,
      }
    }

    case 'OPEN_PREVIEW':
      return {
        ...state,
        pagePreviewDoc:
          action.payload.docId,

        pagePreviewNum:
          action.payload.page,
      }

    case 'CLOSE_PREVIEW':
      return {
        ...state,
        pagePreviewDoc: null,
        pagePreviewNum: null,
      }

    default:
      return state
  }
}
// ── Context ────────────────────────────────────────────────────────────────

const Ctx = createContext<{
  state:    AppState
  dispatch: React.Dispatch<Action>
} | null>(null)

export const AppProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [state, dispatch] = useReducer(reducer, init)
  return <Ctx.Provider value={{ state, dispatch }}>{children}</Ctx.Provider>
}

export const useApp = () => {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error('useApp must be used inside AppProvider')
  return ctx
}
