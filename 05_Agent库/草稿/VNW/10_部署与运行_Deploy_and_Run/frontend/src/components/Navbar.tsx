import { useState } from 'react'
import { NavLink, Link } from 'react-router'
import {
  Activity, AlertTriangle, Bot, ChevronRight, Database, ExternalLink, GitBranch,
  HeartPulse, LayoutDashboard, Menu, Network, Table2, Users, X,
} from 'lucide-react'

const groups = [
  {
    label: '总览',
    items: [
      { path: '/', label: '治理驾驶舱', icon: LayoutDashboard },
      { path: '/workflow', label: '闭环工作流', icon: GitBranch },
      { path: '/domains', label: '业务域进度', icon: Activity },
    ],
  },
  {
    label: '分析与执行',
    items: [
      { path: '/nodes', label: '价值节点', icon: Network },
      { path: '/gaps-actions', label: 'Gap 与行动', icon: AlertTriangle },
      { path: '/interview-sop', label: '访谈与 SOP', icon: Users },
      { path: '/agent-readiness', label: 'Agent 就绪度', icon: Bot },
    ],
  },
  {
    label: '数据治理',
    items: [
      { path: '/tables', label: '数据表中心', icon: Table2 },
      { path: '/data-health', label: '数据健康', icon: HeartPulse },
    ],
  },
]

function Navigation({ close }: { close?: () => void }) {
  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-border-default px-5 py-5">
        <div className="flex items-center gap-3">
          <div className="grid h-10 w-10 place-items-center rounded-xl bg-accent-primary text-white shadow-glow">
            <GitBranch className="h-5 w-5" />
          </div>
          <div>
            <p className="font-heading text-sm font-bold tracking-tight text-text-primary">VNW Control</p>
            <p className="mt-0.5 text-[11px] text-text-muted">价值节点治理工作台</p>
          </div>
        </div>
      </div>

      <div className="flex-1 space-y-6 overflow-y-auto px-3 py-5">
        {groups.map(group => (
          <section key={group.label}>
            <p className="mb-2 px-3 text-[10px] font-semibold uppercase tracking-[0.18em] text-text-muted">
              {group.label}
            </p>
            <div className="space-y-1">
              {group.items.map(item => (
                <NavLink
                  key={item.path}
                  to={item.path}
                  onClick={close}
                  className={({ isActive }) =>
                    `group flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-all ${
                      isActive
                        ? 'bg-accent-primary/15 text-text-primary ring-1 ring-accent-primary/30'
                        : 'text-text-secondary hover:bg-bg-surface hover:text-text-primary'
                    }`
                  }
                >
                  {({ isActive }) => (
                    <>
                      <item.icon className={`h-4 w-4 ${isActive ? 'text-accent-primary-light' : 'text-text-muted group-hover:text-text-secondary'}`} />
                      <span className="flex-1">{item.label}</span>
                      {isActive && <ChevronRight className="h-3.5 w-3.5 text-accent-primary-light" />}
                    </>
                  )}
                </NavLink>
              ))}
            </div>
          </section>
        ))}
      </div>

      <div className="border-t border-border-default p-4 space-y-3">
        <Link
          to="/brief"
          onClick={close}
          className="flex items-center justify-between rounded-xl border border-accent-primary/30 bg-accent-primary/10 p-3 text-xs font-medium text-accent-primary-light hover:bg-accent-primary/15"
        >
          <span>业务视图(给负责人看)</span>
          <ExternalLink className="h-3.5 w-3.5" />
        </Link>
        <div className="rounded-xl border border-accent-success/20 bg-accent-success/5 p-3">
          <div className="flex items-center gap-2 text-xs font-medium text-accent-success">
            <span className="h-2 w-2 rounded-full bg-accent-success shadow-[0_0_10px_#34D399]" />
            数据底座已连接
          </div>
          <p className="mt-1.5 text-[11px] leading-relaxed text-text-muted">VNW 自动同步 · 26 张治理表</p>
        </div>
      </div>
    </div>
  )
}

export default function Navbar() {
  const [mobileOpen, setMobileOpen] = useState(false)
  return (
    <>
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-64 border-r border-border-default bg-bg-elevated/95 backdrop-blur-xl lg:block">
        <Navigation />
      </aside>

      <header className="sticky top-0 z-40 flex h-16 items-center justify-between border-b border-border-default bg-bg-base/90 px-4 backdrop-blur-xl lg:hidden">
        <div className="flex items-center gap-3">
          <div className="grid h-9 w-9 place-items-center rounded-lg bg-accent-primary text-white">
            <GitBranch className="h-4 w-4" />
          </div>
          <div>
            <p className="font-heading text-sm font-bold text-text-primary">VNW Control</p>
            <p className="text-[10px] text-text-muted">价值节点治理工作台</p>
          </div>
        </div>
        <button
          aria-label="打开导航"
          onClick={() => setMobileOpen(true)}
          className="rounded-lg border border-border-default bg-bg-surface p-2 text-text-secondary"
        >
          <Menu className="h-5 w-5" />
        </button>
      </header>

      {mobileOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button aria-label="关闭导航" className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={() => setMobileOpen(false)} />
          <aside className="absolute inset-y-0 left-0 w-[min(86vw,320px)] border-r border-border-default bg-bg-elevated shadow-2xl">
            <button aria-label="关闭导航" onClick={() => setMobileOpen(false)} className="absolute right-3 top-3 z-10 rounded-lg p-2 text-text-muted hover:bg-bg-surface">
              <X className="h-5 w-5" />
            </button>
            <Navigation close={() => setMobileOpen(false)} />
          </aside>
        </div>
      )}
    </>
  )
}
