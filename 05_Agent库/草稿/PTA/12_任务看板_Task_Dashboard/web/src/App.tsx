import { useState } from 'react'
import { ListChecks, Activity } from 'lucide-react'
import { TaskBoard } from './pages/TaskBoard'
import { PtaStatus } from './pages/PtaStatus'

type Tab = 'tasks' | 'status'

export default function App() {
  const [tab, setTab] = useState<Tab>('tasks')

  return (
    <div className="min-h-screen bg-bg-base">
      <nav className="border-b border-border-default bg-bg-elevated px-6 py-3 flex items-center gap-6">
        <span className="font-heading font-medium">PTA</span>
        <button
          onClick={() => setTab('tasks')}
          className={`flex items-center gap-1.5 text-sm ${tab === 'tasks' ? 'text-accent-primary-light' : 'text-text-secondary'}`}
        >
          <ListChecks size={16} /> 任务看板
        </button>
        <button
          onClick={() => setTab('status')}
          className={`flex items-center gap-1.5 text-sm ${tab === 'status' ? 'text-accent-primary-light' : 'text-text-secondary'}`}
        >
          <Activity size={16} /> 运行状态
        </button>
      </nav>
      {tab === 'tasks' ? <TaskBoard /> : <PtaStatus />}
    </div>
  )
}
