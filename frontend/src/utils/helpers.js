export function safeStringify(value) {
  try {
    return JSON.stringify(value, null, 2)
  } catch (e) {
    console.warn('safeStringify failed:', e)
    return String(value)
  }
}

function stripHtml(text) {
  const div = document.createElement('div')
  div.innerHTML = String(text)
  return (div.textContent || div.innerText || '').trim()
}

// frappe.throw() messages arrive JSON-encoded inside _server_messages
function getServerMessage(body) {
  if (!body?._server_messages) return ''
  try {
    return JSON.parse(body._server_messages)
      .map((m) => {
        try {
          const parsed = JSON.parse(m)
          return parsed.message || ''
        } catch {
          return m
        }
      })
      .map(stripHtml)
      .filter(Boolean)
      .join('\n')
  } catch {
    return ''
  }
}

export function getErrorText(err) {
  if (!err) return 'No response from the server.'
  const body = err.responseJSON || (err._server_messages || err.exception ? err : null)
  const serverMessage = getServerMessage(body)
  if (serverMessage) return serverMessage
  const exception = body?.exception ? String(body.exception).split('\n')[0] : ''
  return (
    exception ||
    err.message ||
    body?.message ||
    (err.status ? `HTTP ${err.status} ${err.statusText || ''}`.trim() : '') ||
    String(err)
  )
}

export function normalizeBotText(bot) {
  if (typeof bot === 'string') return bot
  if (bot && typeof bot === 'object') {
    if (bot.error) return `⚠️ ${bot.error}`
    return bot.answer || bot.text || ''
  }
  return ''
}
