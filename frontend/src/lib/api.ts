import axios from 'axios'

const API_URL =
  import.meta.env.VITE_API_URL ||
  "http://localhost:8000"

console.log(
  "API URL:",
  import.meta.env.VITE_API_URL
)

// ── Persistent Browser User ID ────────────────────────────────────────────
const USER_ID_KEY =
  "pdf_assistant_user_id"

let userId =
  localStorage.getItem(
    USER_ID_KEY
  )

if (!userId) {
  userId =
    crypto.randomUUID()

  localStorage.setItem(
    USER_ID_KEY,
    userId
  )
}

console.log(
  "USER ID:",
  userId
)

// ── Axios Instance ────────────────────────────────────────────────────────
const api = axios.create({
  baseURL: `${API_URL}/api`,
  timeout: 120_000,
})

// Automatically attach user id
api.interceptors.request.use(
  (config) => {

    config.headers[
      "x-user-id"
    ] = userId

    return config
  }
)

export interface DocumentInfo {
  doc_id:      string
  user_id?:    string
  name:        string
  pages:       number
  status:
    | 'pending'
    | 'processing'
    | 'ready'
    | 'error'
  ocr_pages:   number
  chunks:      number
  upload_time: string
  suggestions?: string[]
}

export interface Source {
  doc_id:      string
  doc_name:    string
  page:        number
  text:        string
  ocr_sourced: boolean
  confidence:
    | 'high'
    | 'medium'
    | 'low'
}

export interface ChatResponse {
  answer: string
  query_type:
    | 'page'
    | 'formula'
    | 'concept'
    | 'exact'
  sources: Source[]
}

export interface PagePreview {
  doc_id: string
  page: number
  text: string
  ocr_used: boolean
  image_b64:
    | string
    | null
}

// ── Documents ──────────────────────────────────────────────────────────────
export const uploadPDF =
async (
  file: File
): Promise<DocumentInfo> => {

  const form =
    new FormData()

  form.append(
    'file',
    file
  )

  const res =
    await api.post<
      DocumentInfo
    >(
      '/documents',
      form,
      {
        headers: {
          'Content-Type':
            'multipart/form-data',
        },
      }
    )

  return res.data
}

export const listDocuments =
async (): Promise<
  DocumentInfo[]
> => {

  const res =
    await api.get<
      DocumentInfo[]
    >(
      '/documents'
    )

  return res.data
}

export const getDocument =
async (
  docId: string
): Promise<DocumentInfo> => {

  const res =
    await api.get<
      DocumentInfo
    >(
      `/documents/${docId}`
    )

  return res.data
}

export const deleteDocument =
async (
  docId: string
): Promise<void> => {

  await api.delete(
    `/documents/${docId}`
  )
}

export const getPagePreview =
async (
  docId: string,
  page: number
): Promise<PagePreview> => {

  const res =
    await api.get<
      PagePreview
    >(
      `/documents/${docId}/pages/${page}`
    )

  return res.data
}

// ── Chat ───────────────────────────────────────────────────────────────────
export const sendChat =
async (
  docId: string,
  query: string,
  history: {
    role: string
    content: string
  }[] = [],
): Promise<ChatResponse> => {

  const res =
    await api.post<
      ChatResponse
    >(
      '/chat',
      {
        doc_id:
          docId,
        query,
        history,
      }
    )

  return res.data
}