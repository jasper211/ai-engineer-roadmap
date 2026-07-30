import { Routes, Route } from 'react-router'
import Layout from './components/Layout'
import BriefLayout from './components/BriefLayout'
import Nodes from './pages/Nodes'
import NodeDetail from './pages/NodeDetail'
import Tables from './pages/Tables'
import Domains from './pages/Domains'
import GapsActions from './pages/GapsActions'
import InterviewSOP from './pages/InterviewSOP'
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
            {/* 2026-07-29:Jasper裁定删除治理驾驶舱(已被机会台V2取代)/闭环工作流
                (纯静态无数据)/Agent就绪度(与机会台重复)/数据健康(无独立价值)。
                /internal改为落到业务域进度(Domains,Jasper个人规则分析V1-V5
                进度跟踪)，其余VN锚点分析工具(价值节点/Gap与行动/访谈SOP)
                和数据表中心保留不动。 */}
            <Route path="/internal" element={<Domains />} />
            <Route path="/nodes" element={<Nodes />} />
            <Route path="/node/:nodeId" element={<NodeDetail />} />
            <Route path="/tables" element={<Tables />} />
            <Route path="/domains" element={<Domains />} />
            <Route path="/gaps-actions" element={<GapsActions />} />
            <Route path="/interview-sop" element={<InterviewSOP />} />
          </Routes>
        </Layout>
      } />
    </Routes>
  )
}
