const IS_DEV = import.meta.env.DEV
export const PIPELINE_TIMEOUT_MS = 180000

export const API = {
  PIPELINE: 'changai.changai.api.v2.text2sql_pipeline_v2.run_text2sql_pipeline',
  SUPPORT: 'changai.changai.api.v2.helpdesk_api.support_bot',
  SETTINGS: 'changai.changai.api.v2.schema_utils.get_frontend_settings',
  TTS: 'changai.changai.api.v2.tts.synthesize_tts',
}

export function frappeCall(method, args = {}, mode = 'actual') {
  if (mode === 'test') {
    return Promise.resolve({ Bot: `[TEST MODE] ${JSON.stringify(args)}` })
  }

  if (!window.frappe || !window.frappe.call) {
    if (IS_DEV) {
      console.warn('[DEV] frappe.call not available in actual mode')
    }
    return Promise.reject(new Error('Frappe API is unavailable in actual mode.'))
  }

  return new Promise((resolve, reject) => {
    window.frappe.call({
      method,
      args,
      callback(r) {
        resolve(r.message)
      },
      error(err) {
        reject(err)
      },
    })
  })
}

export function runPipeline(userQuestion, chatId, mode = 'actual', requestId = null, sendNonErptoAI) {
  return frappeCall(API.PIPELINE, {
    user_question: userQuestion,
    chat_id: chatId,
    request_id: requestId,
    sendNonErptoAI: sendNonErptoAI,
  }, mode)
}
export function runPipelineCancelable(userQuestion, chatId, mode = 'actual', requestId = null, sendNonErptoAI) {
  if (mode === 'test') {
    return {
      promise: Promise.resolve({
        Bot: `[TEST MODE] ${JSON.stringify({
          user_question: userQuestion,
          chat_id: chatId,
          request_id: requestId,
          sendNonErptoAI: sendNonErptoAI,
        })}`
      }),
      cancel: () => false,
    }
  }

  if (!window.frappe || !window.frappe.call) {
    return {
      promise: Promise.reject(new Error('Frappe API is unavailable in actual mode.')),
      cancel: () => false,
    }
  }

  let requestHandle = null
  let settled = false
  let timeoutId = null

  const promise = new Promise((resolve, reject) => {
    requestHandle = window.frappe.call({
      method: API.PIPELINE,
      args: {
        user_question: userQuestion,
        chat_id: chatId,
        request_id: requestId,
        sendNonErptoAI: sendNonErptoAI,
      },
      callback(r) {
        if (settled) return
        settled = true
        clearTimeout(timeoutId)
        resolve(r.message)
      },
      error(err) {
        if (settled) return
        settled = true
        clearTimeout(timeoutId)
        reject(err ?? new Error('Request failed without a response from the server.'))
      },
    })

    // frappe.call never settles if the connection stays open, so give up after a while
    timeoutId = setTimeout(() => {
      if (settled) return
      settled = true
      if (requestHandle && typeof requestHandle.abort === 'function') requestHandle.abort()
      const err = new Error('Request timed out')
      err.code = 'CHANGAI_TIMEOUT'
      reject(err)
    }, PIPELINE_TIMEOUT_MS)
  })

  const cancel = () => {
    if (settled) return false
    if (!requestHandle || typeof requestHandle.abort !== 'function') return false
    requestHandle.abort()
    settled = true
    clearTimeout(timeoutId)
    return true
  }

  return { promise, cancel }
}

export function callSupportBotCancelable(message, mode = 'actual') {
  if (mode === 'test') {
    return {
      promise: Promise.resolve(`[TEST MODE] ${JSON.stringify({ message })}`),
      cancel: () => false,
    }
  }

  if (!window.frappe || !window.frappe.call) {
    return {
      promise: Promise.reject(new Error('Frappe API is unavailable in actual mode.')),
      cancel: () => false,
    }
  }

  let requestHandle = null
  let settled = false

  const promise = new Promise((resolve, reject) => {
    requestHandle = window.frappe.call({
      method: API.SUPPORT,
      args: { message },
      callback(r) {
        settled = true
        resolve(r.message)
      },
      error(err) {
        settled = true
        reject(err)
      },
    })
  })

  const cancel = () => {
    if (settled) return false
    if (!requestHandle || typeof requestHandle.abort !== 'function') return false
    requestHandle.abort()
    settled = true
    return true
  }

  return { promise, cancel }
}

export function callSupportBot(message, mode = 'actual') {
  return frappeCall(API.SUPPORT, { message }, mode)
}

export function getSettingsDetails(mode = 'actual') {
  return frappeCall(API.SETTINGS, {}, mode)
}

export function synthesizeTTS(text, voiceId = 'Zayd', mode = 'actual') {
  return frappeCall(API.TTS, {
    text,
    voice_id: voiceId,
  }, mode)
}

export function isRealtimeConnected() {
  return Boolean(window.frappe?.realtime?.socket?.connected)
}
