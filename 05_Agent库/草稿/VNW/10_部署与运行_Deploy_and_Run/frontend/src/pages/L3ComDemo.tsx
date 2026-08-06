import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router'
import { ArrowLeft, Database, Download, ExternalLink, GitBranch, ShieldCheck } from 'lucide-react'

const SECTIONS = [
  ['panel-a', 'A 流程蓝图'],
  ['panel-e', 'E 交付物地图'],
  ['panel-c', 'C 任务卡片'],
  ['panel-b', 'B 人机协作'],
  ['panel-d', 'D 优先级'],
  ['decision-panel', '负责人决策'],
  ['panel-f', 'F 证据'],
] as const

export default function L3ComDemo() {
  const frameRef = useRef<HTMLIFrameElement>(null)
  const [frameHeight, setFrameHeight] = useState(5200)

  useEffect(() => {
    const frame = frameRef.current
    if (!frame) return
    let observer: ResizeObserver | undefined

    const syncHeight = () => {
      const doc = frame.contentDocument
      if (!doc) return
      doc.documentElement.classList.add('system-embedded')
      setFrameHeight(Math.max(900, doc.documentElement.scrollHeight))
      observer?.disconnect()
      observer = new ResizeObserver(() => {
        setFrameHeight(Math.max(900, doc.documentElement.scrollHeight))
      })
      observer.observe(doc.body)
    }

    frame.addEventListener('load', syncHeight)
    return () => {
      frame.removeEventListener('load', syncHeight)
      observer?.disconnect()
    }
  }, [])

  function jumpTo(id: string) {
    frameRef.current?.contentDocument?.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Link to="/models" className="inline-flex items-center gap-2 text-xs text-text-muted hover:text-text-primary">
          <ArrowLeft className="h-4 w-4" />返回模型清单
        </Link>
        <div className="flex flex-wrap items-center gap-3">
          <a
            href="/demos/L3流程模型_demo_L3-COM_标准测试版_20260728.html"
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 text-xs text-text-muted hover:text-accent-primary"
          >
            独立页面打开 <ExternalLink className="h-3.5 w-3.5" />
          </a>
          <span className="flex items-center gap-1.5 text-xs text-text-muted">
            <Download className="h-3.5 w-3.5" />下载分析报告
            <a href="/reports/L3流程分析报告_L3-COM.html" download className="text-accent-primary hover:underline">HTML</a>
            ·
            <a href="/reports/L3流程分析报告_L3-COM.md" download className="text-accent-primary hover:underline">MD</a>
          </span>
        </div>
      </div>

      <section className="overflow-hidden rounded-2xl border border-border-default bg-bg-elevated shadow-panel">
        <div className="border-b border-border-default bg-gradient-to-r from-indigo-50 via-white to-sky-50 px-5 py-5 sm:px-7">
          <div className="flex flex-wrap items-start justify-between gap-5">
            <div>
              <div className="flex items-center gap-2 text-xs font-semibold text-accent-primary">
                <GitBranch className="h-4 w-4" /> L3流程模型 · 标准验证样本
              </div>
              <h1 className="mt-2 font-heading text-2xl font-bold text-text-primary sm:text-3xl">L3-COM · 佣金全链路管理</h1>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-text-secondary">
                完整Demo已经纳入系统主视图。以下按“流程—交付物—任务—协作—优先级—决策—证据”的顺序阅读，不再保留另一套简化骨架。
              </p>
            </div>
            <div className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
              <div className="rounded-xl border border-border-default bg-white px-3 py-2"><b className="block text-lg text-text-primary">18</b><span className="text-text-muted">数据库L4</span></div>
              <div className="rounded-xl border border-border-default bg-white px-3 py-2"><b className="block text-lg text-text-primary">4</b><span className="text-text-muted">正式VN桥接</span></div>
              <div className="rounded-xl border border-border-default bg-white px-3 py-2"><b className="block text-lg text-text-primary">49</b><span className="text-text-muted">任务卡</span></div>
              <div className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2"><b className="block text-lg text-amber-700">A×</b><span className="text-amber-700">暂不可移交</span></div>
            </div>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-blue-50 px-3 py-1.5 text-xs text-blue-700"><Database className="h-3.5 w-3.5" />数据库桥接已核对</span>
            <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-3 py-1.5 text-xs text-emerald-700"><ShieldCheck className="h-3.5 w-3.5" />M、E Gate通过</span>
            <span className="rounded-full bg-amber-50 px-3 py-1.5 text-xs text-amber-700">熔断与人工控制门仍保留</span>
          </div>
        </div>

        <nav className="sticky top-16 z-20 flex gap-2 overflow-x-auto border-b border-border-default bg-white/95 px-4 py-3 backdrop-blur sm:px-6">
          {SECTIONS.map(([id, label]) => (
            <button key={id} onClick={() => jumpTo(id)} className="shrink-0 rounded-lg border border-border-default bg-white px-3 py-2 text-xs font-medium text-text-secondary transition hover:border-accent-primary hover:text-accent-primary">
              {label}
            </button>
          ))}
        </nav>

        <iframe
          ref={frameRef}
          title="L3-COM完整流程模型"
          src="/demos/L3流程模型_demo_L3-COM_标准测试版_20260728.html"
          style={{ height: frameHeight }}
          className="block w-full border-0 bg-white"
        />
      </section>
    </div>
  )
}
