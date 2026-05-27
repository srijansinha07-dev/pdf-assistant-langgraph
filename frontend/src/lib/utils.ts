import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

export const cn = (...inputs: ClassValue[]) => twMerge(clsx(inputs))

export const formatBytes = (bytes: number): string => {
  if (bytes < 1024)       return `${bytes} B`
  if (bytes < 1024**2)    return `${(bytes/1024).toFixed(1)} KB`
  return `${(bytes/1024**2).toFixed(1)} MB`
}

export const formatDate = (iso: string): string =>
  new Date(iso).toLocaleDateString('en-US', {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  })

export const queryTypeLabel: Record<string, string> = {
  formula: 'Formula',
  page:    'Page',
  concept: 'Concept',
  exact:   'Exact',
}

export const queryTypeBadgeClass: Record<string, string> = {
  formula: 'badge-formula',
  page:    'badge-page',
  concept: 'badge-concept',
  exact:   'badge-exact',
}
