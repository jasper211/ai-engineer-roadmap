import { useState } from 'react'
import { ListChecks, Activity, Newspaper, Cpu } from 'lucide-react'
import { TaskBoard } from './pages/TaskBoard'
import { PtaStatus } from './pages/PtaStatus'
import { ActivityFeed } from './pages/ActivityFeed'
import { AgentMonitor } from './pages/AgentMonitor'

type Tab = 'tasks' | 'activity' | 'agents' | 'status'

const TABS: { key: Tab; label: string; icon: typeof ListChecks }[] = [
  { key: 'tasks', label: '任务看板', icon: ListChecks },
  { key: 'activity', label: '今日动态', icon: Newspaper },
  { key: 'agents', label: 'Agent监控', icon: Cpu },
  { key: 'status', label: '运行状态', icon: Activity },
]

export default function App() {
  const [tab, setTab] = useState<Tab>('tasks')

  return (
    <div className="min-h-screen bg-bg-base">
      <nav className="border-b border-border-default bg-bg-elevated px-6 py-3 flex items-center gap-6">
        <span className="font-heading font-medium">PTA</span>
        {TABS.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`flex items-center gap-1.5 text-sm ${tab === key ? 'text-accent-primary-light' : 'text-text-secondary'}`}
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
