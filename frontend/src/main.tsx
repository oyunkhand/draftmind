import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import './index.css'
import { AppProvider } from './lib/store'
import Dashboard from './pages/Dashboard'
import DraftBoard from './pages/DraftBoard'
import DraftSetup from './pages/DraftSetup'
import ModelPage from './pages/Model'
import Scouting from './pages/Scouting'
import SeriesHistory from './pages/SeriesHistory'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AppProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<Dashboard />} />
            <Route path="scouting" element={<Scouting />} />
            <Route path="scouting/:teamId" element={<Scouting />} />
            <Route path="draft" element={<DraftSetup />} />
            <Route path="draft/:id" element={<DraftBoard />} />
            <Route path="series" element={<SeriesHistory />} />
            <Route path="series/:id" element={<SeriesHistory />} />
            <Route path="model" element={<ModelPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AppProvider>
  </StrictMode>,
)
