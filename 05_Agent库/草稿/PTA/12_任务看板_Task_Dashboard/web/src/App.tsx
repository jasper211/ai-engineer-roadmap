import { useState } from 'react'
import { Command, Activity, Newspaper, Cpu } from 'lucide-react'
import { TaskBoard } from './pages/TaskBoard'
import { PtaStatus } from './pages/PtaStatus'
import { ActivityFeed } from './pages/ActivityFeed'
import { AgentMonitor } from './pages/AgentMonitor'

type Tab = 'tasks' | 'activity' | 'agents' | 'status'

const TABS: { key: Tab; label: string; icon: typeof Command }[] = [
  { key: 'tasks', label: '指挥中心', icon: Command },
  { key: 'activity', label: '与我相关', icon: Newspaper },
  { key: 'agents', label: 'Agent监控', icon: Cpu },
  { key: 'status', label: '运行状态', icon: Activity },
]

export default function App() {
  const [tab, setTab] = useState<Tab>('tasks')

  return (
    <div className="min-h-screen bg-bg-base">
      <nav className="sticky top-0 z-40 flex items-center gap-2 border-b border-border-default bg-bg-base/85 px-5 py-3 backdrop-blur-xl lg:px-8">
        <div className="mr-5 flex items-center gap-2"><span className="grid h-8 w-8 place-items-center rounded-lg bg-accent-primary text-sm font-bold text-white">P</span><span className="font-heading font-semibold">PTA</span><span className="hidden text-xs text-text-muted sm:inline">任务驾驶舱</span></div>
        {TABS.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm transition ${tab === key ? 'bg-bg-elevated text-text-primary' : 'text-text-secondary hover:text-text-primary'}`}
          >
            <Icon size={16} /> {label}
          </button>
        ))}
      </nav>
      {tab === 'tasks' && <TaskBoard />}
      {tab === 'activity' && <ActivityFeed />}
      {tab === 'agents' && <AgentMonitor />}
      {tab === 'status' && <PtaStatus />}
    </div>
  )
}
