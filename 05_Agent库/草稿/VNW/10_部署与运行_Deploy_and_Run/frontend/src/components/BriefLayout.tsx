import { Link } from 'react-router'
import { Bot, GitBranch, Network, Settings2 } from 'lucide-react'

export default function BriefLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-bg-base text-text-primary">
      <header className="sticky top-0 z-40 border-b border-border-default bg-bg-base/90 backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-[1200px] items-center justify-between px-4 sm:px-6">
          <Link to="/" className="flex items-center gap-3">
            <div className="grid h-9 w-9 place-items-center rounded-lg bg-accent-primary text-white">
              <GitBranch className="h-4 w-4" />
            </div>
            <div>
              <p className="font-heading text-sm font-bold text-text-primary">VNW · AI 化机会台</p>
              <p className="text-[11px] text-text-muted">从业务交付物到 AIT 设计</p>
            </div>
          </Link>
          <div className="flex items-center gap-2">
            <Link
              to="/models"
              className="flex items-center gap-1.5 rounded-md border border-accent-primary/40 bg-accent-primary/10 px-3 py-1.5 text-xs text-accent-primary-light hover:bg-accent-primary/15"
            >
              <Network className="h-3.5 w-3.5" /> L3 流程模型
            </Link>
            <Link
              to="/brief/automation"
              className="flex items-center gap-1.5 rounded-md border border-border-default px-3 py-1.5 text-xs text-text-muted hover:text-text-secondary"
            >
              <Bot className="h-3.5 w-3.5" /> 自动化全景(L4级)
            </Link>
            <Link
              to="/internal"
              className="flex items-center gap-1.5 rounded-md border border-border-default px-3 py-1.5 text-xs text-text-muted hover:text-text-secondary"
            >
              <Settings2 className="h-3.5 w-3.5" /> 数据证据
            </Link>
          </div>
        </div>
      </header>

      <main className="mx-auto min-h-[calc(100vh-64px)] max-w-[1200px] px-4 py-6 sm:px-6">
        {children}
      </main>

      <footer className="border-t border-border-default px-4 py-5 text-xs text-text-muted sm:px-6">
        <div className="mx-auto max-w-[1200px]">VNW 提供业务判断依据；确认验证后，由 AIT 承接工具、Skill 或 Agent 设计。</div>
      </footer>
    </div>
  )
}
