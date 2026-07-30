#!/usr/bin/env node
import fs from 'node:fs'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '../..')
const snapshotDir = path.join(root, '10_部署与运行_Deploy_and_Run/frontend/public/data/model_snapshots')
const files = fs.readdirSync(snapshotDir)
  .filter(name => /^L3-.*\.json$/.test(name) && !name.endsWith('.manifest.json'))

const governanceLanguage = /P[01]\s*[:：]|系统\s*bug|根因|未纳入流程库|当前无标准|待建设|纯手工|批次\d+|新增[:：]/
const findings = []

for (const file of files) {
  const snapshot = JSON.parse(fs.readFileSync(path.join(snapshotDir, file), 'utf8'))
  const counts = new Map()
  for (const l4 of snapshot.l4s) {
    const value = String(l4.deliverable || '').trim()
    if (value) counts.set(value, (counts.get(value) || 0) + 1)
  }
  for (const l4 of snapshot.l4s) {
    const value = String(l4.deliverable || '').trim()
    const reasons = []
    let issueType = ''
    if (value.length > 80 || governanceLanguage.test(value)) {
      issueType = 'MIXED_CONTENT'
      if (value.length > 80) reasons.push(`长文本${value.length}字`)
      if (governanceLanguage.test(value)) reasons.push('混入问题或治理说明')
    } else if (value && (counts.get(value) || 0) >= 3) {
      issueType = 'REPEATED_VALUE'
      reasons.push(`同一L3内重复${counts.get(value)}次，需业务核实是否合理复用`)
    }
    if (!issueType) continue
    findings.push({
      l3_code: snapshot.l3_code,
      l4_code: l4.l4_code,
      l4_name: l4.l4_name,
      issue_type: issueType,
      reasons,
      evidence_id: l4.evidence_refs?.l4_deliverable || '',
      source_value: value,
    })
  }
}

const result = {
  schema_version: 'vnw.l4-deliverable-audit.v1',
  generated_at: new Date().toISOString(),
  scanned_l3_count: files.length,
  affected_l3_count: new Set(findings.map(item => item.l3_code)).size,
  finding_count: findings.length,
  findings,
}

const output = path.join(root, '07_接入记忆_Integrate_Memory/l4_deliverable_quality_audit.json')
const frontendOutput = path.join(root, '10_部署与运行_Deploy_and_Run/frontend/public/data/l4_deliverable_quality_audit.json')
const content = `${JSON.stringify(result, null, 2)}\n`
fs.writeFileSync(output, content)
fs.writeFileSync(frontendOutput, content)
console.log(JSON.stringify({ output, frontend_output: frontendOutput, scanned_l3_count: result.scanned_l3_count, affected_l3_count: result.affected_l3_count, finding_count: result.finding_count }))
