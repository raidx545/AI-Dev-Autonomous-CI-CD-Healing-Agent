import React, { useEffect } from 'react'
import { useAgent } from './context/AgentContext'
import { useWebSocket } from './hooks/useWebSocket'

import InputForm from './components/InputForm'
import RunSummaryCard from './components/RunSummaryCard'
import ScoreBreakdown from './components/ScoreBreakdown'
import FixesTable from './components/FixesTable'
import CICDTimeline from './components/CICDTimeline'
import PipelineLogs from './components/PipelineLogs'
import { motion, AnimatePresence } from 'framer-motion'

function Dashboard() {
    const { state } = useAgent()

    // Initialize WebSocket when runId exists
    useWebSocket(state.runId)

    return (
        <div className="app-container">
            <header className="app-header">
                <h1>RIFT 2026</h1>
                <p>Autonomous DevOps Agent</p>
            </header>

            <InputForm />

            <AnimatePresence>
                {state.status !== 'idle' && (
                    <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        className="dashboard-grid"
                    >
                        <RunSummaryCard />
                        <ScoreBreakdown />
                        <div className="full-width">
                            <FixesTable />
                        </div>
                        <CICDTimeline />
                        <PipelineLogs />
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    )
}

function App() {
    return (
        <div className="app-wrapper">
            {/* Use the AgentProvider from main.jsx or wrap here if not there. 
           Wait, main.jsx does NOT wrap it. We need to wrap it here or in main. 
           Let's wrap in main or here. Implementation plan said Context in App. 
           I'll check main.jsx again. If main doesn't wrap, I do it here.
           Actually I wrote main.jsx earlier and it imported App but didn't wrap. 
           So I must wrap here.
       */}
            <Dashboard />
        </div>
    )
}

// Re-export wrapped version default
import { AgentProvider } from './context/AgentContext'
export default function WrappedApp() {
    return (
        <AgentProvider>
            <App />
        </AgentProvider>
    )
}
