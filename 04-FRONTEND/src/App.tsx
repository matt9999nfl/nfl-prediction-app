import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { Layout } from '@/components/Layout'
import { DashboardPage } from '@/pages/DashboardPage'
import { GameDetailPage } from '@/pages/GameDetailPage'
import { ModelPage } from '@/pages/ModelPage'
import { DatasetsPage } from '@/pages/DatasetsPage'
import { DatasetDetailPage } from '@/pages/DatasetDetailPage'
import { ExperimentsNewPage } from '@/pages/ExperimentsNewPage'
import { ExperimentDetailPage } from '@/pages/ExperimentDetailPage'
import { FrameworksPage } from '@/pages/FrameworksPage'
import { FrameworkDetailPage } from '@/pages/FrameworkDetailPage'
import { AboutPage } from '@/pages/AboutPage'
import { TeamPage } from '@/pages/TeamPage'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/games/:gameId" element={<GameDetailPage />} />
          <Route path="/teams/:team" element={<TeamPage />} />
          <Route path="/datasets" element={<DatasetsPage />} />
          <Route path="/datasets/:datasetId" element={<DatasetDetailPage />} />
          <Route path="/experiments" element={<ModelPage />} />
          <Route path="/experiments/new" element={<ExperimentsNewPage />} />
          <Route path="/experiments/:id" element={<ExperimentDetailPage />} />
          <Route path="/model" element={<Navigate to="/experiments" replace />} />
          <Route path="/frameworks" element={<FrameworksPage />} />
          <Route path="/frameworks/:id" element={<FrameworkDetailPage />} />
          <Route path="/about" element={<AboutPage />} />
          {/* Catch-all */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
