import React, { useState, useEffect } from 'react'
import {
  BellRing,
  ShieldAlert,
  Mail,
  Volume2,
  VolumeX,
  Check,
  Edit2,
  Sliders,
  Send,
  Bell,
  Clock,
  FileText,
  Phone,
  MessageSquare,
  Key,
  Loader2,
  AlertTriangle
} from 'lucide-react'
import { useToastStore, sendBrowserPushNotification } from '@/store/useToastStore'
import { api } from '@/api/api'

export function AlertsTab() {
  const { addToast, soundEnabled, setSoundEnabled, pushEnabled, setPushEnabled } = useToastStore()

  // State for Critical Severity configuration modal
  const [severityConfigModalOpen, setSeverityConfigModalOpen] = useState(false)
  const [minSeverity, setMinSeverity] = useState(localStorage.getItem('alert_min_severity') || 'critical')
  const [escalationTime, setEscalationTime] = useState(localStorage.getItem('alert_escalation_time') || '0')
  const [soundAlerts, setSoundAlerts] = useState(soundEnabled)
  const [pushAlerts, setPushAlerts] = useState(pushEnabled)

  // Loading & Testing state
  const [isLoading, setIsLoading] = useState(true)
  const [testingChannel, setTestingChannel] = useState<string | null>(null)

  // Form states for Alert Destinations
  const [phoneNumber, setPhoneNumber] = useState('')
  const [whatsappEnabled, setWhatsappEnabled] = useState(false)
  const [whatsappWebhook, setWhatsappWebhook] = useState('')

  const [telegramEnabled, setTelegramEnabled] = useState(false)
  const [telegramBotToken, setTelegramBotToken] = useState('')
  const [telegramChatId, setTelegramChatId] = useState('')

  const [emailEnabled, setEmailEnabled] = useState(false)
  const [emailAddress, setEmailAddress] = useState('')
  const [smtpHost, setSmtpHost] = useState('smtp.gmail.com')
  const [smtpPort, setSmtpPort] = useState(587)
  const [smtpUser, setSmtpUser] = useState('')
  const [smtpPassword, setSmtpPassword] = useState('')

  // Edit expanders
  const [isEditingPhone, setIsEditingPhone] = useState(false)
  const [isEditingTelegram, setIsEditingTelegram] = useState(false)
  const [isEditingEmail, setIsEditingEmail] = useState(false)

  // Daily report schedule
  const [dailyReportEmailEnabled, setDailyReportEmailEnabled] = useState(
    localStorage.getItem('alert_daily_report_email_enabled') !== 'false'
  )
  const [dailyReportTime, setDailyReportTime] = useState(
    localStorage.getItem('alert_daily_report_time') || '18:00'
  )

  // Fetch settings from Backend API on mount
  useEffect(() => {
    const fetchSettings = async () => {
      try {
        setIsLoading(true)
        const res = await api.get('/api/alerts/settings')
        if (res.data) {
          setPhoneNumber(res.data.phone_number || '')
          setWhatsappEnabled(!!res.data.whatsapp_enabled)
          setWhatsappWebhook(res.data.whatsapp_webhook_url || '')

          setTelegramEnabled(!!res.data.telegram_enabled)
          setTelegramBotToken(res.data.telegram_bot_token || '')
          setTelegramChatId(res.data.telegram_chat_id || '')

          setEmailEnabled(!!res.data.email_enabled)
          setEmailAddress(res.data.email_address || '')
          setSmtpHost(res.data.smtp_host || 'smtp.gmail.com')
          setSmtpPort(res.data.smtp_port || 587)
          setSmtpUser(res.data.smtp_user || '')
          setSmtpPassword(res.data.smtp_password || '')
        }
      } catch (err: any) {
        console.warn('Could not fetch alert destinations from backend:', err)
      } finally {
        setIsLoading(false)
      }
    }
    fetchSettings()
  }, [])

  const saveSettingsToBackend = async (payload: any) => {
    try {
      await api.post('/api/alerts/settings', payload)
      addToast({ title: 'Settings Saved', message: 'Alert configuration synced to server.', type: 'success' })
    } catch (err: any) {
      addToast({ title: 'Save Failed', message: err?.response?.data?.detail || 'Could not save alert settings', type: 'danger' })
    }
  }

  const handleTestAlert = async (channel: 'telegram' | 'email' | 'whatsapp') => {
    setTestingChannel(channel)
    try {
      const res = await api.post('/api/alerts/test', { channel })
      addToast({
        title: 'Test Alert Sent',
        message: res.data?.message || `Test notification dispatched to ${channel}!`,
        type: 'success'
      })
    } catch (err: any) {
      addToast({
        title: 'Test Failed',
        message: err?.response?.data?.detail || `Failed to send test alert to ${channel}.`,
        type: 'danger'
      })
    } finally {
      setTestingChannel(null)
    }
  }

  const handleSaveSeverity = async () => {
    localStorage.setItem('alert_min_severity', minSeverity)
    localStorage.setItem('alert_escalation_time', escalationTime)
    setSoundEnabled(soundAlerts)
    await setPushEnabled(pushAlerts)
    setSeverityConfigModalOpen(false)
    addToast({
      title: 'Alert Escalation Updated',
      message: `Critical alerts set to ${minSeverity.toUpperCase()} with ${escalationTime === '0' ? 'immediate' : escalationTime + 's'} escalation.`,
      type: 'success',
    })
  }

  const handleTogglePush = async () => {
    const next = !pushEnabled
    const success = await setPushEnabled(next)
    if (success && next) {
      addToast({ title: 'Push Notifications', message: 'Browser push notifications enabled.', type: 'success' })
      sendBrowserPushNotification('🚨 DevaVision AI', 'Push notifications are operational!')
    } else if (!next) {
      addToast({ title: 'Push Notifications', message: 'Browser push notifications disabled.', type: 'default' })
    } else {
      addToast({ title: 'Permission Blocked', message: 'Please enable notifications permission in browser settings.', type: 'danger' })
    }
  }

  return (
    <div className="relative z-10 space-y-6 max-w-2xl">
      <div className="flex items-center gap-3 mb-6">
        <BellRing className="w-6 h-6 text-primary" />
        <div>
          <h2 className="text-xl font-bold text-white tracking-wide">Alerts & Notifications</h2>
          <p className="text-xs text-muted-foreground">
            Manage live phone numbers, Telegram bots with snapshot delivery, and email notification destinations.
          </p>
        </div>
      </div>

      <div className="space-y-4">
        {/* 1. Phone & WhatsApp Notification Card */}
        <div className="bg-background/40 p-5 rounded-2xl border border-foreground/10 hover:border-primary/30 transition-all space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <div className="p-3 rounded-xl bg-success/15 text-success border border-success/20">
                <Phone className="w-6 h-6" />
              </div>
              <div>
                <div className="font-bold text-sm text-white flex items-center gap-2">
                  Phone / WhatsApp Alerts
                  <span className={`text-[10px] px-2 py-0.5 rounded-full ${whatsappEnabled && phoneNumber ? 'bg-success/20 text-success' : 'bg-muted/20 text-muted-foreground'} font-bold uppercase`}>
                    {whatsappEnabled && phoneNumber ? 'Active' : 'Disabled'}
                  </span>
                </div>
                <div className="text-xs text-muted-foreground mt-0.5">
                  {phoneNumber ? `Target Number: ${phoneNumber}` : 'No phone number configured'}
                </div>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={() => {
                  const next = !whatsappEnabled
                  setWhatsappEnabled(next)
                  saveSettingsToBackend({ whatsapp_enabled: next, phone_number: phoneNumber })
                }}
                className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all ${whatsappEnabled ? 'bg-success/20 text-success border border-success/30' : 'bg-foreground/10 text-muted-foreground'}`}
              >
                {whatsappEnabled ? 'Enabled' : 'Disabled'}
              </button>
              <button
                onClick={() => setIsEditingPhone(!isEditingPhone)}
                className="px-4 py-2 bg-foreground/10 hover:bg-foreground/20 text-white rounded-xl text-xs font-bold transition-all flex items-center gap-1.5"
              >
                <Edit2 className="w-3.5 h-3.5" /> {isEditingPhone ? 'Close' : 'Configure'}
              </button>
            </div>
          </div>

          {/* Inline Edit Form for Phone / WhatsApp */}
          {isEditingPhone && (
            <div className="pt-4 border-t border-foreground/10 space-y-3 animate-fadeIn">
              <div>
                <label className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider block mb-1">
                  Recipient Phone Number
                </label>
                <input
                  type="text"
                  value={phoneNumber}
                  onChange={(e) => setPhoneNumber(e.target.value)}
                  placeholder="+91 9876543210"
                  className="w-full bg-background/60 border border-foreground/20 rounded-xl px-3 py-2 text-xs text-white focus:outline-none focus:border-primary font-mono"
                />
              </div>

              <div>
                <label className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider block mb-1">
                  WhatsApp Gateway / Webhook URL (Optional)
                </label>
                <input
                  type="url"
                  value={whatsappWebhook}
                  onChange={(e) => setWhatsappWebhook(e.target.value)}
                  placeholder="https://api.whatsapp-gateway.com/send"
                  className="w-full bg-background/60 border border-foreground/20 rounded-xl px-3 py-2 text-xs text-white focus:outline-none focus:border-primary font-mono text-[11px]"
                />
              </div>

              <div className="flex items-center justify-between pt-2">
                <button
                  disabled={testingChannel === 'whatsapp' || !whatsappWebhook}
                  onClick={() => handleTestAlert('whatsapp')}
                  className="px-3 py-1.5 bg-success/15 hover:bg-success/25 text-success border border-success/30 rounded-xl text-xs font-bold transition-all flex items-center gap-1.5 disabled:opacity-50"
                >
                  {testingChannel === 'whatsapp' ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />}
                  Send Test Alert
                </button>

                <button
                  onClick={() => {
                    saveSettingsToBackend({
                      phone_number: phoneNumber,
                      whatsapp_enabled: whatsappEnabled,
                      whatsapp_webhook_url: whatsappWebhook
                    })
                    setIsEditingPhone(false)
                  }}
                  className="px-4 py-2 bg-primary hover:bg-primary/90 text-white rounded-xl text-xs font-bold transition-all flex items-center gap-1"
                >
                  <Check className="w-4 h-4" /> Save Phone Settings
                </button>
              </div>
            </div>
          )}
        </div>

        {/* 2. Telegram Bot Alerts with Snapshot Card */}
        <div className="bg-background/40 p-5 rounded-2xl border border-foreground/10 hover:border-primary/30 transition-all space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <div className="p-3 rounded-xl bg-info/15 text-info border border-info/20">
                <Send className="w-6 h-6" />
              </div>
              <div>
                <div className="font-bold text-sm text-white flex items-center gap-2">
                  Telegram Bot (Photos & Alerts)
                  <span className={`text-[10px] px-2 py-0.5 rounded-full ${telegramEnabled && telegramBotToken ? 'bg-success/20 text-success' : 'bg-muted/20 text-muted-foreground'} font-bold uppercase`}>
                    {telegramEnabled && telegramBotToken ? 'Active' : 'Disabled'}
                  </span>
                </div>
                <div className="text-xs text-muted-foreground mt-0.5">
                  {telegramChatId ? `Chat ID: ${telegramChatId}` : 'Instant snapshot images sent to Telegram'}
                </div>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={() => {
                  const next = !telegramEnabled
                  setTelegramEnabled(next)
                  saveSettingsToBackend({ telegram_enabled: next, telegram_bot_token: telegramBotToken, telegram_chat_id: telegramChatId })
                }}
                className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all ${telegramEnabled ? 'bg-success/20 text-success border border-success/30' : 'bg-foreground/10 text-muted-foreground'}`}
              >
                {telegramEnabled ? 'Enabled' : 'Disabled'}
              </button>
              <button
                onClick={() => setIsEditingTelegram(!isEditingTelegram)}
                className="px-4 py-2 bg-foreground/10 hover:bg-foreground/20 text-white rounded-xl text-xs font-bold transition-all flex items-center gap-1.5"
              >
                <Edit2 className="w-3.5 h-3.5" /> {isEditingTelegram ? 'Close' : 'Configure'}
              </button>
            </div>
          </div>

          {/* Inline Edit Form for Telegram */}
          {isEditingTelegram && (
            <div className="pt-4 border-t border-foreground/10 space-y-3 animate-fadeIn">
              <div>
                <label className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider block mb-1">
                  Telegram Bot Token
                </label>
                <input
                  type="password"
                  value={telegramBotToken}
                  onChange={(e) => setTelegramBotToken(e.target.value)}
                  placeholder="123456789:ABCdefGHIjklMNOpqrSTUvwxYZ"
                  className="w-full bg-background/60 border border-foreground/20 rounded-xl px-3 py-2 text-xs text-white focus:outline-none focus:border-primary font-mono text-[11px]"
                />
              </div>

              <div>
                <label className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider block mb-1">
                  Telegram Chat ID / Group ID
                </label>
                <input
                  type="text"
                  value={telegramChatId}
                  onChange={(e) => setTelegramChatId(e.target.value)}
                  placeholder="-1001234567890 or 987654321"
                  className="w-full bg-background/60 border border-foreground/20 rounded-xl px-3 py-2 text-xs text-white focus:outline-none focus:border-primary font-mono text-xs"
                />
                <span className="text-[10px] text-muted-foreground mt-1 block">
                  Tip: Get your Chat ID by messaging <code>@userinfobot</code> on Telegram.
                </span>
              </div>

              <div className="flex items-center justify-between pt-2">
                <button
                  disabled={testingChannel === 'telegram' || !telegramBotToken || !telegramChatId}
                  onClick={() => handleTestAlert('telegram')}
                  className="px-3 py-1.5 bg-info/15 hover:bg-info/25 text-info border border-info/30 rounded-xl text-xs font-bold transition-all flex items-center gap-1.5 disabled:opacity-50"
                >
                  {testingChannel === 'telegram' ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />}
                  Send Test Photo Alert
                </button>

                <button
                  onClick={() => {
                    saveSettingsToBackend({
                      telegram_bot_token: telegramBotToken,
                      telegram_chat_id: telegramChatId,
                      telegram_enabled: telegramEnabled
                    })
                    setIsEditingTelegram(false)
                  }}
                  className="px-4 py-2 bg-primary hover:bg-primary/90 text-white rounded-xl text-xs font-bold transition-all flex items-center gap-1"
                >
                  <Check className="w-4 h-4" /> Save Telegram Settings
                </button>
              </div>
            </div>
          )}
        </div>

        {/* 3. Email (SMTP) Notifications Card */}
        <div className="bg-background/40 p-5 rounded-2xl border border-foreground/10 hover:border-primary/30 transition-all space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <div className="p-3 rounded-xl bg-primary/15 text-primary border border-primary/20">
                <Mail className="w-6 h-6" />
              </div>
              <div>
                <div className="font-bold text-sm text-white flex items-center gap-2">
                  Email Alert Notifications
                  <span className={`text-[10px] px-2 py-0.5 rounded-full ${emailEnabled && emailAddress ? 'bg-success/20 text-success' : 'bg-muted/20 text-muted-foreground'} font-bold uppercase`}>
                    {emailEnabled && emailAddress ? 'Active' : 'Disabled'}
                  </span>
                </div>
                <div className="text-xs text-muted-foreground mt-0.5">
                  {emailAddress || 'No recipient email configured'}
                </div>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={() => {
                  const next = !emailEnabled
                  setEmailEnabled(next)
                  saveSettingsToBackend({ email_enabled: next, email_address: emailAddress })
                }}
                className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all ${emailEnabled ? 'bg-success/20 text-success border border-success/30' : 'bg-foreground/10 text-muted-foreground'}`}
              >
                {emailEnabled ? 'Enabled' : 'Disabled'}
              </button>
              <button
                onClick={() => setIsEditingEmail(!isEditingEmail)}
                className="px-4 py-2 bg-foreground/10 hover:bg-foreground/20 text-white rounded-xl text-xs font-bold transition-all flex items-center gap-1.5"
              >
                <Edit2 className="w-3.5 h-3.5" /> {isEditingEmail ? 'Close' : 'Configure'}
              </button>
            </div>
          </div>

          {/* Inline Edit Form for Email */}
          {isEditingEmail && (
            <div className="pt-4 border-t border-foreground/10 space-y-3 animate-fadeIn">
              <div>
                <label className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider block mb-1">
                  Recipient Email Address
                </label>
                <input
                  type="email"
                  value={emailAddress}
                  onChange={(e) => setEmailAddress(e.target.value)}
                  placeholder="security@company.com"
                  className="w-full bg-background/60 border border-foreground/20 rounded-xl px-3 py-2 text-xs text-white focus:outline-none focus:border-primary"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider block mb-1">
                    SMTP Host
                  </label>
                  <input
                    type="text"
                    value={smtpHost}
                    onChange={(e) => setSmtpHost(e.target.value)}
                    placeholder="smtp.gmail.com"
                    className="w-full bg-background/60 border border-foreground/20 rounded-xl px-3 py-2 text-xs text-white focus:outline-none focus:border-primary font-mono text-[11px]"
                  />
                </div>
                <div>
                  <label className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider block mb-1">
                    SMTP Port
                  </label>
                  <input
                    type="number"
                    value={smtpPort}
                    onChange={(e) => setSmtpPort(parseInt(e.target.value) || 587)}
                    placeholder="587"
                    className="w-full bg-background/60 border border-foreground/20 rounded-xl px-3 py-2 text-xs text-white focus:outline-none focus:border-primary font-mono text-[11px]"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider block mb-1">
                    SMTP Username / Email
                  </label>
                  <input
                    type="text"
                    value={smtpUser}
                    onChange={(e) => setSmtpUser(e.target.value)}
                    placeholder="alerts-sender@gmail.com"
                    className="w-full bg-background/60 border border-foreground/20 rounded-xl px-3 py-2 text-xs text-white focus:outline-none focus:border-primary text-xs"
                  />
                </div>
                <div>
                  <label className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider block mb-1">
                    SMTP Password / App Password
                  </label>
                  <input
                    type="password"
                    value={smtpPassword}
                    onChange={(e) => setSmtpPassword(e.target.value)}
                    placeholder="••••••••••••"
                    className="w-full bg-background/60 border border-foreground/20 rounded-xl px-3 py-2 text-xs text-white focus:outline-none focus:border-primary text-xs"
                  />
                </div>
              </div>

              <div className="flex items-center justify-between pt-2">
                <button
                  disabled={testingChannel === 'email' || !emailAddress}
                  onClick={() => handleTestAlert('email')}
                  className="px-3 py-1.5 bg-primary/15 hover:bg-primary/25 text-primary border border-primary/30 rounded-xl text-xs font-bold transition-all flex items-center gap-1.5 disabled:opacity-50"
                >
                  {testingChannel === 'email' ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Mail className="w-3.5 h-3.5" />}
                  Send Test Email
                </button>

                <button
                  onClick={() => {
                    saveSettingsToBackend({
                      email_address: emailAddress,
                      email_enabled: emailEnabled,
                      smtp_host: smtpHost,
                      smtp_port: smtpPort,
                      smtp_user: smtpUser,
                      smtp_password: smtpPassword
                    })
                    setIsEditingEmail(false)
                  }}
                  className="px-4 py-2 bg-primary hover:bg-primary/90 text-white rounded-xl text-xs font-bold transition-all flex items-center gap-1"
                >
                  <Check className="w-4 h-4" /> Save Email Settings
                </button>
              </div>
            </div>
          )}
        </div>

        {/* 4. Critical Severity Escalation Card */}
        <div className="bg-background/40 p-5 rounded-2xl border border-foreground/10 flex items-center justify-between hover:border-primary/30 transition-all">
          <div className="flex items-center gap-4">
            <div className="p-3 rounded-xl bg-danger/15 text-danger border border-danger/20">
              <ShieldAlert className="w-6 h-6" />
            </div>
            <div>
              <div className="font-bold text-sm text-white flex items-center gap-2">
                Critical Severity Escalation
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-danger/20 text-danger font-mono font-bold uppercase">
                  {minSeverity}
                </span>
              </div>
              <div className="text-xs text-muted-foreground mt-0.5">
                {escalationTime === '0' ? 'Immediate escalation' : `${escalationTime}s delayed escalation`} • Audio: {soundEnabled ? 'ON' : 'OFF'} • Push: {pushEnabled ? 'ON' : 'OFF'}
              </div>
            </div>
          </div>
          <button
            onClick={() => {
              setSoundAlerts(soundEnabled)
              setPushAlerts(pushEnabled)
              setSeverityConfigModalOpen(true)
            }}
            className="px-4 py-2 bg-primary/15 hover:bg-primary/30 text-primary border border-primary/30 rounded-xl text-xs font-bold transition-all shadow-sm flex items-center gap-1.5"
          >
            <Sliders className="w-3.5 h-3.5" /> Configure
          </button>
        </div>

        {/* 5. Browser Desktop Notifications Card */}
        <div className="bg-background/40 p-5 rounded-2xl border border-foreground/10 hover:border-primary/30 transition-all flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="p-3 rounded-xl bg-info/15 text-info border border-info/20">
              <Bell className="w-6 h-6" />
            </div>
            <div>
              <div className="font-bold text-sm text-white flex items-center gap-2">
                Browser Desktop Notifications
                <span className={`text-[10px] px-2 py-0.5 rounded-full ${pushEnabled ? 'bg-success/20 text-success' : 'bg-muted/20 text-muted-foreground'} font-bold uppercase`}>
                  {pushEnabled ? 'Active' : 'Disabled'}
                </span>
              </div>
              <div className="text-xs text-muted-foreground mt-0.5">Instant pop-up notifications on screen during alert triggers.</div>
            </div>
          </div>

          <button
            onClick={handleTogglePush}
            className={`px-4 py-2 rounded-xl text-xs font-bold transition-all ${pushEnabled ? 'bg-success/20 text-success border border-success/30' : 'bg-foreground/10 text-muted-foreground'}`}
          >
            {pushEnabled ? 'Enabled' : 'Enable Push'}
          </button>
        </div>
      </div>

      {/* Severity Modal */}
      {severityConfigModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-md animate-fadeIn">
          <div className="bg-background border border-foreground/15 rounded-3xl p-6 w-full max-w-md space-y-6 shadow-2xl">
            <div className="flex justify-between items-center border-b border-foreground/10 pb-4">
              <h3 className="font-bold text-lg text-white flex items-center gap-2">
                <ShieldAlert className="w-5 h-5 text-danger" /> Configure Alert Escalation
              </h3>
            </div>

            <div className="space-y-4">
              <div>
                <label className="text-xs font-bold text-muted-foreground uppercase tracking-wider block mb-2">Minimum Trigger Threshold</label>
                <select
                  value={minSeverity}
                  onChange={(e) => setMinSeverity(e.target.value)}
                  className="w-full bg-foreground/5 border border-foreground/10 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-primary"
                >
                  <option value="critical" className="bg-background text-white">Critical Severity Only (DANGER)</option>
                  <option value="warning" className="bg-background text-white">Warning & Critical (WARNING + DANGER)</option>
                  <option value="all" className="bg-background text-white">All Events (INFO + WARNING + DANGER)</option>
                </select>
              </div>

              <div>
                <label className="text-xs font-bold text-muted-foreground uppercase tracking-wider block mb-2">Escalation Delay</label>
                <select
                  value={escalationTime}
                  onChange={(e) => setEscalationTime(e.target.value)}
                  className="w-full bg-foreground/5 border border-foreground/10 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-primary"
                >
                  <option value="0" className="bg-background text-white">Immediate (0 seconds)</option>
                  <option value="30" className="bg-background text-white">30 Seconds</option>
                  <option value="60" className="bg-background text-white">60 Seconds (1 minute)</option>
                  <option value="300" className="bg-background text-white">300 Seconds (5 minutes)</option>
                </select>
              </div>

              <div className="p-3 rounded-xl bg-foreground/5 border border-foreground/10 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  {soundAlerts ? <Volume2 className="w-5 h-5 text-success" /> : <VolumeX className="w-5 h-5 text-muted-foreground" />}
                  <div>
                    <div className="font-bold text-sm text-white">Audio Alarm Sound</div>
                    <div className="text-xs text-muted-foreground">Play browser audio chime on alert</div>
                  </div>
                </div>
                <input
                  type="checkbox"
                  checked={soundAlerts}
                  onChange={(e) => setSoundAlerts(e.target.checked)}
                  className="w-5 h-5 accent-primary cursor-pointer"
                />
              </div>

              <div className="p-3 rounded-xl bg-foreground/5 border border-foreground/10 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <Bell className="w-5 h-5 text-info" />
                  <div>
                    <div className="font-bold text-sm text-white">Browser Push Notification</div>
                    <div className="text-xs text-muted-foreground font-medium">Desktop pop-up on critical alerts</div>
                  </div>
                </div>
                <input
                  type="checkbox"
                  checked={pushAlerts}
                  onChange={(e) => setPushAlerts(e.target.checked)}
                  className="w-5 h-5 accent-primary cursor-pointer"
                />
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-4 border-t border-foreground/10">
              <button
                onClick={() => setSeverityConfigModalOpen(false)}
                className="px-4 py-2 rounded-xl bg-foreground/10 hover:bg-foreground/20 text-muted-foreground hover:text-white text-xs font-bold transition-all"
              >
                Cancel
              </button>
              <button
                onClick={handleSaveSeverity}
                className="px-5 py-2 rounded-xl bg-primary hover:bg-primary/90 text-white text-xs font-bold transition-all shadow-md flex items-center gap-1.5"
              >
                <Check className="w-4 h-4" /> Save Configuration
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
