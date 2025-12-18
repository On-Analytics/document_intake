type AnyError = any

export function toFriendlyErrorMessage(err: AnyError, fallback: string): string {
  if (!err) return fallback

  const status = err?.status ?? err?.statusCode
  const code = err?.code
  const message = err?.message

  if (status === 401) return 'You are not signed in. Please sign in and try again.'
  if (status === 403) return 'You do not have permission to perform this action.'

  if (code === 'PGRST301' || code === '42501') {
    return 'You do not have permission to access this data.'
  }

  if (typeof message === 'string' && message.trim().length > 0) {
    return message
  }

  return fallback
}
