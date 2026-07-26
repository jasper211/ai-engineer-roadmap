import { Link } from 'react-router'
import { Bot, GitBranch, Settings2 } from 'lucide-react'

export default function BriefLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-bg-base text-text-primary">
      <header className="sticky top-0 z-40 border-b border-border-default bg-bg-base/90 backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-[1200px] items-center justify-between px-4 sm:px-6">
          <Link to="/brief" className="flex items-center gap-3">
            <div className="grid h-9 w-9 place-items-center rounded-lg bg-accent-primary text-white">
              <GitBranch className="h-4 w-4" />
            </div>
            <div>
              <p className="font-heading text-sm font-bold text-text-primary">价值节点 · 自动化就绪度</p>
              <p className="text-[11px] text-text-muted">面向业务负责人的结论视图</p>
            </div>
          </Link>
          <div className="flex items-center gap-2">
            <Link
              to="/brief/automation"
              className="flex items-center gap-1.5 rounded-md border border-border-default px-3 py-1.5 text-xs text-text-muted hover:text-text-secondary"
            >
              <Bot className="h-3.5 w-3.5" /> 自动化全景(L4级)
            </Link>
            <Link
              to="/"
              className="flex items-center gap-1.5 rounded-md border border-border-default px-3 py-1.5 text-xs text-text-muted hover:text-text-secondary"
            >
              <Settings2 className="h-3.5 w-3.5" /> 内部数据视图
            </Link>
          </div>
        </div>
      </header>

      <main className="mx-auto min-h-[calc(100vh-64px)] max-w-[1200px] px-4 py-6 sm:px-6">
        {children}
      </main>

      <footer className="border-t border-border-default px-4 py-5 text-xs text-text-muted sm:px-6">
        <div className="mx-auto max-w-[1200px]">数据来自 VNW 数据底座自动同步 · 熔断/移交状态每次同步重新生成</div>
      </footer>
    </div>
  )
}
