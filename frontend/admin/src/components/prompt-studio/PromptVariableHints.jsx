const HINTS = {
  voice_system_prompt: [
    '{{customer_name}}', '{{account_type}}', '{{otp_status}}',
    '{{agent_name}}', '{{tenant_name}}',
  ],
  context_prompt: [
    '{{conversation_stage}}', '{{customer_intent}}', '{{kb_context}}',
  ],
  companion_mid_call_prompt: [
    '{{transcript}}', '{{customer_name}}', '{{suggested_action}}',
  ],
  companion_acw_prompt: [
    '{{transcript}}', '{{resolution}}', '{{action_items}}',
  ],
  qa_prompt: [
    '{{transcript}}', '{{agent_name}}', '{{call_duration}}',
  ],
  coaching_prompt: [
    '{{agent_name}}', '{{scored_calls}}', '{{weakness_pattern}}',
  ],
}

export default function PromptVariableHints({ promptKey }) {
  const vars = HINTS[promptKey] || []
  if (!vars.length) return null
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 8 }}>
      {vars.map(v => (
        <span key={v} style={{
          padding: '2px 8px', borderRadius: 4,
          background: 'rgba(244,247,61,0.12)',
          color: '#f4f73d', fontSize: 11, fontFamily: 'monospace',
        }}>{v}</span>
      ))}
    </div>
  )
}
