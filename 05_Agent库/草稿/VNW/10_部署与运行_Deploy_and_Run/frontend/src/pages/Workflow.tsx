import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { WORKFLOW_STAGES } from '@/lib/data'
import {
  GitBranch, CheckCircle2, Clock, TrendingUp, Layers,
  FileText, MessageSquare, AlertCircle, Users
} from 'lucide-react'

function getStagePos(i: number, total: number) {
  const angle = (i * 2 * Math.PI) / total - Math.PI / 2
  return { x: 400 + 300 * Math.cos(angle), y: 230 + 160 * Math.sin(angle) }
}

export default function Workflow() {
  const [selected, setSelected] = useState<number | null>(null)
  const stages = WORKFLOW_STAGES
  const colors = ['#34D399','#34D399','#34D399','#6366F1','#6366F1','#64748B','#64748B','#64748B','#64748B']

  function pathD(i: number, j: number) {
    const a = getStagePos(i, 9), b = getStagePos(j, 9)
    const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2
    return `M ${a.x} ${a.y} Q ${mx} ${my} ${b.x} ${b.y}`
  }

  const stats = [
    { label: '价值节点', value: 72, icon: Layers },
    { label: '规则信号', value: 454, icon: MessageSquare },
    { label: '已识别规则', value: 112, icon: FileText },
    { label: '待执行行动', value: 118, icon: Clock },
    { label: '开放Gap', value: 209, icon: AlertCircle },
    { label: '岗位映射', value: 72, icon: Users },
  ]

  return (
    <div className="space-y-6">
      <motion.div initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }}>
        <div className="flex items-center gap-3">
          <GitBranch className="h-8 w-8 text-accent-primary" />
          <h1 className="font-heading text-3xl font-bold text-text-primary">工作流闭环可视化</h1>
        </div>
        <p className="mt-1 text-text-secondary">价值节点驱动的流程架构治理闭环 — 9阶段循环</p>
      </motion.div>

      {/* Stats */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
        {stats.map((s, i) => (
          <motion.div key={s.label} className="rounded-lg border border-border-default bg-bg-elevated p-3 text-center"
            initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: i * 0.05 }}>
            <s.icon className="mx-auto mb-1 h-4 w-4 text-accent-primary" />
            <p className="font-mono text-xl text-text-primary">{s.value}</p>
            <p className="text-xs text-text-muted">{s.label}</p>
          </motion.div>
        ))}
      </div>

      {/* SVG Diagram */}
      <motion.div className="rounded-lg border border-border-default bg-bg-elevated p-4"
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.2 }}>
        <div className="mb-3 flex items-center gap-4 text-xs">
          <span className="flex items-center gap-1"><span className="inline-block h-2 w-2 rounded-full bg-accent-success" />已完成</span>
          <span className="flex items-center gap-1"><span className="inline-block h-2 w-2 rounded-full bg-accent-primary" />进行中</span>
          <span className="flex items-center gap-1"><span className="inline-block h-2 w-2 rounded-full bg-text-muted" />待启动</span>
        </div>
        <div className="overflow-x-auto">
          <svg viewBox="0 0 800 460" className="mx-auto w-full max-w-[900px]">
            <defs>
              <marker id="arw" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto"><polygon points="0 0,8 3,0 6" fill="#3D4770"/></marker>
            </defs>
            {stages.map((_, i) => (
              <path key={i} d={pathD(i, (i+1)%9)} fill="none" stroke={i<3?'#34D399':i<5?'#6366F1':'#2A324A'}
                strokeWidth={i<5?2.5:1.5} strokeDasharray={i<5?'none':'6,4'} markerEnd="url(#arw)" opacity={i<5?0.8:0.4} />
            ))}
            {stages.map((stage, i) => {
              const pos = getStagePos(i, 9)
              const active = i === selected
              return (
                <g key={stage.id} onClick={() => setSelected(active ? null : i)} style={{ cursor: 'pointer' }}>
                  {(i===3||i===4||active) && (
                    <circle cx={pos.x} cy={pos.y} r="46" fill="none" stroke={colors[i]} strokeWidth="2" opacity="0.3">
                      <animate attributeName="r" values="46;52;46" dur="2s" repeatCount="indefinite"/>
                      <animate attributeName="opacity" values="0.3;0.1;0.3" dur="2s" repeatCount="indefinite"/>
                    </circle>
                  )}
                  <circle cx={pos.x} cy={pos.y} r="40"
                    fill={active ? `${colors[i]}25` : i<3 ? 'rgba(52,211,153,0.12)' : i<5 ? 'rgba(99,102,241,0.12)' : '#131825'}
                    stroke={colors[i]} strokeWidth={active?3:2} />
                  <text x={pos.x} y={pos.y-4} textAnchor="middle" fill={colors[i]} fontSize="14" fontWeight="700" fontFamily="monospace">{stage.id}</text>
                  <text x={pos.x} y={pos.y+14} textAnchor="middle" fill={i<5?colors[i]:'#64748B'} fontSize="10" fontWeight="500">{stage.short}</text>
                  <text x={pos.x} y={pos.y+62} textAnchor="middle" fill={active?'#F1F5F9':'#94A3B8'} fontSize="11" fontWeight={active?600:400}>{stage.name}</text>
                </g>
              )
            })}
            <text x="400" y="235" textAnchor="middle" fill="#64748B" fontSize="12">持续迭代</text>
          </svg>
        </div>
      </motion.div>

      {/* Detail panel */}
      <AnimatePresence>
        {selected !== null && (
          <motion.div className="rounded-lg border border-border-default bg-bg-elevated p-5"
            initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
            <div className="flex items-center gap-3">
              <span className="flex h-10 w-10 items-center justify-center rounded-full font-mono text-sm font-bold"
                style={{ backgroundColor: `${colors[selected]}20`, color: colors[selected] }}>{stages[selected].id}</span>
              <div>
                <h3 className="font-heading text-lg font-semibold text-text-primary">{stages[selected].name}</h3>
                <p className="text-sm text-text-secondary">{stages[selected].desc}</p>
              </div>
              {selected < 3 && <CheckCircle2 className="ml-auto h-5 w-5 text-accent-success" />}
              {(selected === 3 || selected === 4) && <TrendingUp className="ml-auto h-5 w-5 text-accent-primary" />}
              {selected > 4 && <Clock className="ml-auto h-5 w-5 text-text-muted" />}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Stage cards */}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
        {stages.map((stage, i) => (
          <motion.div key={stage.id} className="rounded-lg border border-border-default bg-bg-elevated p-4 cursor-pointer transition-all hover:border-border-hover"
            style={{ borderLeftWidth: 3, borderLeftColor: colors[i] }}
            initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 + i * 0.05 }}
            onClick={() => setSelected(i)}>
            <div className="flex items-center gap-3">
              <span className="flex h-8 w-8 items-center justify-center rounded-full text-xs font-bold" style={{ backgroundColor: `${colors[i]}20`, color: colors[i] }}>{stage.id}</span>
              <div>
                <h3 className="text-sm font-semibold text-text-primary">{stage.name}</h3>
                <p className="text-xs text-text-secondary">{stage.desc}</p>
              </div>
              {i < 3 ? <CheckCircle2 className="ml-auto h-4 w-4 text-accent-success" /> : i < 5 ? <TrendingUp className="ml-auto h-4 w-4 text-accent-primary" /> : <Clock className="ml-auto h-4 w-4 text-text-muted" />}
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  )
}
