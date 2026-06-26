<script setup>
import { ref, reactive, computed, nextTick, onMounted, onBeforeUnmount } from 'vue'
import ChatbotToggler from './components/ChatbotToggler.vue'
import ChatbotPopup from './components/ChatbotPopup.vue'
import { runPipelineCancelable, callSupportBotCancelable, getSettingsDetails } from './utils/frappe.js'
import { getOrCreateChatId, getPollyPreference, setPollyPreference } from './utils/session.js'
import { normalizeBotText, getErrorText, safeStringify } from './utils/helpers.js'
const showChatbot = ref(false)
const activeTab = ref('chat')
const chatHistory = ref([])
const debugLogs = ref([])
const debugEnabled = ref(false)
const supportHistory = ref([])
const popupRef = ref(null)
const responseMode = ref('actual')
const autoReadEnabled = ref(true)
const settings = ref(null)
const isLoadingSettings = ref(false)
const currentDebug = ref(null)
const sendNonERPtoaiEnabled = ref((() => {
  try {
    return localStorage.getItem('sendNonERPtoaiEnabled') === 'true'
  } catch {
    return false
  }
})())
const ttsConfig = ref({
  enableVoiceChat: false,
  pollyAvailable: false,
  usePolly: true,
  voiceId: 'Zayd',
  enable_changai: false,
})
const activeTtsProvider = ref('off')
const cancelPendingChatRequest = ref(null)
const cancelPendingSupportRequest = ref(null)
const isAwaitingChatResponse = computed(() => cancelPendingChatRequest.value !== null)
const isAwaitingSupportResponse = computed(() => cancelPendingSupportRequest.value !== null)

function updateProviderFromSettings() {
  if (!ttsConfig.value.enableVoiceChat) {
    activeTtsProvider.value = 'off'
    return
  }
  activeTtsProvider.value = ttsConfig.value.usePolly ? 'polly' : 'browser'
}

function handleTtsProviderEvent(event) {
  const provider = event?.detail?.provider
  if (provider === 'polly' || provider === 'browser' || provider === 'off') {
    activeTtsProvider.value = provider
  }
}

async function loadSettings() {
  console.log('loadSettings called, frappe available:', !!window.frappe?.call)
  if (isLoadingSettings.value || settings.value) return

  isLoadingSettings.value = true
  try {
    settings.value = await getSettingsDetails(responseMode.value)
    ttsConfig.value = {
      enableVoiceChat: Boolean(settings.value?.enable_voice_chat),
      pollyAvailable: Boolean(settings.value?.polly_enabled),
      usePolly: Boolean(settings.value?.polly_enabled) && getPollyPreference(),
      voiceId: settings.value?.polly_voice_id || 'Zayd',
      enable_changai: Boolean(settings.value?.enable_changai),
    }
    updateProviderFromSettings()
    debugLogs.value.push({ type: 'settings', settings: settings.value })
  } catch (err) {
    const errorText = getErrorText(err)
    console.error('Settings API Error:', err)
    console.error('Settings error detail:', errorText)
    debugLogs.value.push({ type: 'settings', error: errorText })
  } finally {
    isLoadingSettings.value = false
  }
}

function toggleChatbot() {
  showChatbot.value = !showChatbot.value
}

function scrollToBottom() {
  popupRef.value?.scrollToBottom()
}

function toggleAutoRead() {
  autoReadEnabled.value = !autoReadEnabled.value
}

function togglePollyPreference() {
  const nextValue = !ttsConfig.value.usePolly
  ttsConfig.value = {
    ...ttsConfig.value,
    usePolly: nextValue && ttsConfig.value.pollyAvailable,
  }
  setPollyPreference(ttsConfig.value.usePolly)
  updateProviderFromSettings()
}

function sendNonErpToAI() {
  sendNonERPtoaiEnabled.value = !sendNonERPtoaiEnabled.value
  localStorage.setItem(
    'sendNonERPtoaiEnabled',
    sendNonERPtoaiEnabled.value
  )
}
async function handleSubmit(message) {
  if (activeTab.value === 'support') {
    await handleSupportSubmit(message)
  } else {
    await handleChatSubmit(message)
  }
}

async function handleChatSubmit(message) {
  currentDebug.value = null
  if (responseMode.value === 'actual') {
    await loadSettings()
  }

  chatHistory.value.push({ role: 'user', text: message })
  await nextTick()
  scrollToBottom()

  const thinkingMsg = reactive({ role: 'model', text: 'Thinking...', cancelable: true,isStatus: true,statusType: 'thinking'})
  chatHistory.value.push(thinkingMsg)
  await nextTick()
  scrollToBottom()
  const onPipelineUpdate = (msg) => {
  const now = Date.now()
  const seconds = ((now - lastStepTime) / 1000).toFixed(2)
  lastStepTime = now
  console.log('REALTIME STEP', msg)
  if (msg.message) {
  const step = `${msg.message} (${seconds}s)`
  steps.push(step)
  currentDebug.value = step
  thinkingMsg.text = msg.message
  thinkingMsg.statusType = 'pipeline'
}

  if (!msg.done && msg.message) {
    thinkingMsg.text = msg.message
    thinkingMsg.statusType = 'pipeline'
  }
if (msg.done) {
  thinkingMsg.cancelable = false

  if (msg.error) {
    thinkingMsg.text = `⚠️ ${msg.message || 'Something failed'}`
    thinkingMsg.isStatus = false
    thinkingMsg.statusType = null
  } else if (msg.data?.answer) {
    thinkingMsg.text = msg.data.answer
    thinkingMsg.isStatus = false
    thinkingMsg.statusType = null
  }

  frappe.realtime.off(eventName, onPipelineUpdate)
  currentDebug.value = null
  return
}
}

  let cancelled = false
  const chatId = getOrCreateChatId()
  const requestId = `${chatId}_${Date.now()}`
  const eventName = `debug_${requestId}`
  frappe.realtime.on(eventName, onPipelineUpdate)
  const request = runPipelineCancelable(message,chatId, responseMode.value,requestId,sendNonERPtoaiEnabled.value)
  let lastStepTime = Date.now()
  const steps = []
  cancelPendingChatRequest.value = () => {
  if (cancelled) return
  cancelled = true
  request.cancel()
  frappe.realtime.off(eventName, onPipelineUpdate)
  thinkingMsg.isStatus = false
  thinkingMsg.statusType = null
  thinkingMsg.text = 'Cancelled by user.'
  debugLogs.value.push({
  type: 'cancelled',
  user: message,
  steps: [...steps],
})
  currentDebug.value = null
  thinkingMsg.cancelable = false
  cancelPendingChatRequest.value = null
}
try {
  const response = await request.promise
  if (response?.open_report)
  {
    thinkingMsg.isStatus = false
    thinkingMsg.statusType = null
    thinkingMsg.text = `Opening "${response.report_name}" report." `
    debugLogs.value.push({
      type: 'success',
      steps: [...steps],
      final_response: response,
      entity_raw: response.entity_raw
    })
    currentDebug.value = null
    if (!response.report_name) {
      thinkingMsg.text = `Report name extraction failed.Can you ask the same question again?`
      return
    }
    frappe.set_route('query-report', response.report_name, response.filters || {})
    return
  }
else if (response?.create_entity) {
  thinkingMsg.isStatus = false
  thinkingMsg.statusType = null
  thinkingMsg.cancelable = false
  thinkingMsg.text = `Opening "${response.doc}" doctype for creating a new record.`

  debugLogs.value.push({
    type: 'success',
    user: message,
    steps: [...steps],
    final_response: response,
  })

  currentDebug.value = null

  const doctype = response.doc
  const fieldsToFill = response.fields_to_fill || {}
  const childTables = response.child_tables || {}

  // Fallback: if new fields_to_fill is empty, use old defaultMap logic
  const entityName = response.entity_name || ""
  const defaultMap = {
    Customer: { customer_name: entityName },
    Supplier: { supplier_name: entityName },
    Employee: { employee_name: entityName },
    Item: { item_code: entityName, item_name: entityName },
    Project: { project_name: entityName },
    Lead: { lead_name: entityName },
    Opportunity: { opportunity_name: entityName }
  }

  const defaults = Object.keys(fieldsToFill).length > 0
    ? fieldsToFill
    : (defaultMap[doctype] || {})

  frappe.route_options = defaults
  frappe.set_route("Form", doctype, "new")

  let attempts = 0
  const timer = setInterval(() => {
    if (attempts++ > 50) {
      clearInterval(timer)
      return
    }

    if (cur_frm && cur_frm.doctype === doctype && cur_frm.is_new()) {
      clearInterval(timer)

      // Fill main form fields
      Object.entries(defaults).forEach(([field, value]) => {
        if (value && cur_frm.fields_dict[field]) {
          cur_frm.set_value(field, value)
          cur_frm.refresh_field(field)
        }
      })

      // Fill child tables generically
      Object.entries(childTables).forEach(([tableField, rows]) => {
        if (!Array.isArray(rows) || !rows.length) return
        if (!cur_frm.fields_dict[tableField]) return

        rows.forEach(row => {
          const childRow = frappe.model.add_child(cur_frm.doc, tableField)
          Object.entries(row).forEach(([field, value]) => {
            if (value != null && value !== "") {
              frappe.model.set_value(childRow.doctype, childRow.name, field, value)
            }
          })
        })

        cur_frm.refresh_field(tableField)
      })
    }
  }, 200)

  return
}
if (response?.stop_followup) {
  thinkingMsg.isStatus = false
  thinkingMsg.statusType = null
  thinkingMsg.cancelable = false
  thinkingMsg.text = response.message || "You’re welcome!"

  debugLogs.value.push({
    type: 'stop_followup',
    user: message,
    steps: [...steps],
    final_response: response,
  })

  currentDebug.value = null
  return
}

    if (cancelled) return
    thinkingMsg.cancelable = false
    const finalBotText = normalizeBotText(response?.Bot)?.trim() || 'No response.'
    thinkingMsg.isStatus = false
    thinkingMsg.statusType = null
    thinkingMsg.text = finalBotText
    debugLogs.value.push({
      type: 'success',
      user: message,
      steps: [...steps],
      final_response: response,
    })
    currentDebug.value = null
  } catch (err) {
    if (cancelled) return
    thinkingMsg.cancelable = false
    thinkingMsg.isStatus = false
    thinkingMsg.statusType = null
    const errorText = getErrorText(err)
    currentDebug.value = null
    debugLogs.value.push({
  type: 'failed',
  user: message,
  steps: [...steps],
  error: errorText,
})
    console.error('ChangAI API Error:', err)
    if (err?.code === "ERR_NETWORK_CHANGED" || err?.message?.includes("ERR_NETWORK_CHANGED")){
    thinkingMsg.isStatus = false
    thinkingMsg.statusType = null
    thinkingMsg.text = '⚠️ Network error. Please check your connection and try again.'

    }
    else{
    thinkingMsg.isStatus = false
    thinkingMsg.statusType = null
    thinkingMsg.text = '⚠️ Something went wrong. Please try again.'
    }
  } finally {
  frappe.realtime.off(eventName, onPipelineUpdate)
  if (!cancelled) {
    cancelPendingChatRequest.value = null
  }
}
  await nextTick()
  scrollToBottom()
}

function handleCancelResponse() {
  if (activeTab.value === 'support') {
    cancelPendingSupportRequest.value?.()
    return
  }

  cancelPendingChatRequest.value?.()
}

async function handleSupportSubmit(message) {
  supportHistory.value.push({ role: 'user', text: message })
  await nextTick()
  scrollToBottom()

  const thinkingMsg = reactive({ role: 'model', text: 'Sending to support...',isStatus: true,statusType : 'support' })
  supportHistory.value.push(thinkingMsg)
  await nextTick()
  scrollToBottom()

  let cancelled = false
  const request = callSupportBotCancelable(message, responseMode.value)

  cancelPendingSupportRequest.value = () => {
    if (cancelled) return
    cancelled = true
    request.cancel()
    thinkingMsg.isStatus = false
    thinkingMsg.statusType = null
    thinkingMsg.text = 'Cancelled by user.'
    cancelPendingSupportRequest.value = null
  }

  try {
    const response = await request.promise
    if (cancelled) return
    thinkingMsg.isStatus = false
    thinkingMsg.statusType = null
    thinkingMsg.text = response ? safeStringify(response) : 'Support request sent successfully.'
  } catch (err) {
    if (cancelled) return
    console.error('Support API Error:', err)
    thinkingMsg.isStatus = false
    thinkingMsg.statusType = null
    thinkingMsg.text = '⚠️ Failed to reach support. Please try again.'
  } finally {
    if (!cancelled) {
      cancelPendingSupportRequest.value = null
    }
  }

  await nextTick()
  scrollToBottom()
}

onMounted(() => {
  if (typeof window !== 'undefined') {
    window.addEventListener('changai-tts-provider', handleTtsProviderEvent)
  }

  if (responseMode.value === 'actual') {
    loadSettings()
  }
})

onBeforeUnmount(() => {
  if (typeof window !== 'undefined') {
    window.removeEventListener('changai-tts-provider', handleTtsProviderEvent)
  }
})
</script>

<template>
  <ChatbotToggler v-if= "ttsConfig.enable_changai" :isOpen="showChatbot" @toggle="toggleChatbot" />
  <ChatbotPopup
    ref="popupRef"
    :isOpen="showChatbot"
    v-model:activeTab="activeTab"
    :chatHistory="chatHistory"
    :debugLogs="debugLogs"
    :currentDebug="currentDebug"
    :supportHistory="supportHistory"
    :autoReadEnabled="autoReadEnabled"
    :ttsConfig="ttsConfig"
    :activeTtsProvider="activeTtsProvider"
    :settings="settings"
    :isAwaitingChatResponse="isAwaitingChatResponse"
    :isAwaitingSupportResponse="isAwaitingSupportResponse"
    :debugEnabled="debugEnabled"
    :sendNonERPtoaiEnabled="sendNonERPtoaiEnabled"
    @toggleDebug="debugEnabled = !debugEnabled"
    @close="showChatbot = false"
    @submit="handleSubmit"
    @cancelResponse="handleCancelResponse"
    @toggleAutoRead="toggleAutoRead"
    @togglePollyPreference="togglePollyPreference"
    @toggleSendNonERP="sendNonErpToAI"

  />
</template>
