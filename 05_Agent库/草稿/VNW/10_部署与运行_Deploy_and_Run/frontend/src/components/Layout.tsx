import Navbar from './Navbar'

export default function Layout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-bg-base text-text-primary">
      <Navbar />
      <div className="lg:pl-64">
        <main className="mx-auto min-h-[calc(100vh-72px)] max-w-[1560px] px-4 py-5 sm:px-6 lg:px-8 lg:py-8">
          {children}
        </main>
        <footer className="border-t border-border-default px-6 py-5 text-xs text-text-muted lg:px-8">
          <div className="mx-auto flex max-w-[1500px] flex-wrap items-center justify-between gap-2">
            <span>VNW · 价值节点驱动的规则治理闭环</span>
            <span>数据来自 VNW 数据底座自动同步</span>
          </div>
        </footer>
      </div>
    </div>
  )
}
