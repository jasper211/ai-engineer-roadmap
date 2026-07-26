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
import BriefHome from './pages/BriefHome'
import BriefNodeDetail from './pages/BriefNodeDetail'
import BriefAutomation from './pages/BriefAutomation'

export default function App() {
  return (
    <Routes>
      <Route path="/brief" element={<BriefLayout><BriefHome /></BriefLayout>} />
      <Route path="/brief/node/:nodeId" element={<BriefLayout><BriefNodeDetail /></BriefLayout>} />
      <Route path="/brief/automation" element={<BriefLayout><BriefAutomation /></BriefLayout>} />
      <Route path="/" element={<BriefLayout><BriefHome /></BriefLayout>} />
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
