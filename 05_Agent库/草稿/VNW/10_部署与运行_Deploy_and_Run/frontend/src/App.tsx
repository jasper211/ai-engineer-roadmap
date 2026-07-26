import { Routes, Route } from 'react-router'
import Layout from './components/Layout'
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

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Home />} />
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
  )
}
