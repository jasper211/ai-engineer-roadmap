import { AlertTriangle } from 'lucide-react'
import L3ModelDetail from './L3ModelDetail'

export default function L3ComDemo() {
  return (
    <div className="space-y-5">
      <div className="rounded-xl border border-amber-400/30 bg-amber-400/5 p-4 text-xs leading-5 text-amber-100">
        <div className="flex items-center gap-2 font-semibold"><AlertTriangle className="h-4 w-4" />L3-COM 单流程验证版</div>
        <p className="mt-1">本 demo 严格区分数据库权威事实与蓝图补充事实。当前可展示 18 个数据库 L4 和蓝图主链路；数据库尚无 VN-L4 映射且 D1-D6 为 0/18，因此不能作为 AIT 已就绪结论。</p>
      </div>
      <L3ModelDetail modelCode="L3-COM" />
    </div>
  )
}
