import { Routes, Route } from 'react-router'
import Layout from './components/Layout'
import BriefLayout from './components/BriefLayout'
import Home from './pages/Home'
import Workflow from './pages/Workflow'
import Nodes from './pages/Nodes'
import NodeDetail from './pages/NodeDetail'
import Tables from './pages/Tables'
import Domains from './pages/Domains'
import GapsActions from './pages/GapsActions'
import InterviewSOP from './pages/InterviewSOP'
import AgentReadiness from './pages/AgentReadiness'
import DataHealth from './pages/DataHealth'
import L3Demo from './pages/L3Demo'
import L3Models from './pages/L3Models'
import L3ModelDetail from './pages/L3ModelDetail'
import L3ComDemo from './pages/L3ComDemo'

export default function App() {
  return (
    <Routes>
      {/* 2026-07-29:机会台锚点从价值节点改为L3流程模型,全貌层直接用L3Models,
          详情层用L3ModelDetail(自带Gate/D1-D6/蓝图+已有demo的跳转入口)。
          旧的价值节点锚点页面(BriefHome/BriefNodeDetail/BriefAutomation)
          已删除,不保留兼容路由。 */}
      <Route path="/" element={<BriefLayout><L3Models /></BriefLayout>} />
      <Route path="/brief" element={<BriefLayout><L3Models /></BriefLayout>} />
      <Route path="/models" element={<BriefLayout><L3Models /></BriefLayout>} />
      <Route path="/models/:l3Code" element={<BriefLayout><L3ModelDetail /></BriefLayout>} />
      {/* 2026-07-26:单L3手工demo,验证五维流程模型概念,故意不接入任何导航菜单,只能直接访问URL */}
      <Route path="/demo/l3-iri" element={<BriefLayout><L3Demo /></BriefLayout>} />
      <Route path="/demo/l3-com" element={<BriefLayout><L3ComDemo /></BriefLayout>} />
      <Route path="*" element={
        <Layout>
          <Routes>
            <Route path="/internal" element={<Home />} />
            <Route path="/workflow" element={<Workflow />} />
            <Route path="/nodes" element={<Nodes />} />
            <Route path="/node/:nodeId" element={<NodeDetail />} />
            <Route path="/tables" element={<Tables />} />
            <Route path="/domains" element={<Domains />} />
            <Route path="/gaps-actions" element={<GapsActions />} />
            <Route path="/interview-sop" element={<InterviewSOP />} />
            <Route path="/agent-readiness" element={<AgentReadiness />} />
            <Route path="/data-health" element={<DataHealth />} />
          </Routes>
        </Layout>
      } />
    </Routes>
  )
}
