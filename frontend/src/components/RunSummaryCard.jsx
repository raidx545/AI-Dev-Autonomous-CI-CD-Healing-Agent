import React from 'react'
import { GitBranch, Clock, AlertCircle, CheckCircle, Download } from 'lucide-react'
import { useAgent } from '../context/AgentContext'

export default function RunSummaryCard() {
    const { state } = useAgent()
    const { summary, status } = state

    if (!summary && status !== 'running') return null

    // Use summary data or fallback to initial checks if running but no partial summary yet
    const repoUrl = summary?.repo_url || '...'
    const branchName = summary?.branch_name || 'Creating branch...'
    const teamInfo = summary ? `${summary.team_name} • ${summary.leader_name}` : 'Loading...'
    const failures = summary?.total_failures_detected || 0
    const fixes = summary?.total_fixes_applied || 0
    const time = summary?.total_time_seconds || 0
    const ciStatus = summary?.cicd_status || 'pending'

    const getStatusBadge = (s) => {
        switch (s.toLowerCase()) {
            case 'passed': return <span className="badge badge-passed"><CheckCircle size={12} /> PASSED</span>
            case 'failed': return <span className="badge badge-failed"><AlertCircle size={12} /> FAILED</span>
            case 'running': return <span className="badge badge-running"><div className="spinner" style={{ width: 12, height: 12, borderWidth: 1 }} /> RUNNING</span>
            default: return <span className="badge badge-pending">PENDING</span>
        }
    }

    const handleDownload = async () => {
        if (!state.runId) return
        try {
            const baseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8080'
            const response = await fetch(`${baseUrl}/api/runs/${state.runId}`)
            if (!response.ok) throw new Error('Failed to fetch results')
            const data = await response.json()
            const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
            const url = URL.createObjectURL(blob)
            const a = document.createElement('a')
            a.href = url
            a.download = `rift_results_${state.runId}.json`
            document.body.appendChild(a)
            a.click()
            document.body.removeChild(a)
            URL.revokeObjectURL(url)
        } catch (error) {
            console.error('Download failed:', error)
        }
    }

    return (
        <div className="glass-card summary-card" style={{ position: 'relative' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div>
                    <h2 className="section-title">Run Summary</h2>
                    <p className="section-subtitle">{repoUrl}</p>
                </div>
                {getStatusBadge(ciStatus)}
            </div>

            <div style={{ marginTop: '1.5rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem', color: 'var(--text-accent)', fontSize: '0.9rem' }}>
                    <UsersIcon size={14} />
                    {teamInfo}
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontFamily: 'var(--font-mono)', fontSize: '0.85rem', background: 'rgba(0,0,0,0.3)', padding: '0.5rem', borderRadius: 6 }}>
                    <GitBranch size={14} color="var(--accent-purple)" />
                    {branchName}
                </div>
            </div>

            <div className="summary-grid">
                <div className="stat-item">
                    <div className="stat-label">Failures Detected</div>
                    <div className="stat-value" style={{ color: 'var(--accent-red)' }}>{failures}</div>
                </div>
                <div className="stat-item">
                    <div className="stat-label">Fixes Applied</div>
                    <div className="stat-value" style={{ color: 'var(--accent-green)' }}>{fixes}</div>
                </div>
                <div className="stat-item">
                    <div className="stat-label">Total Time</div>
                    <div className="stat-value mono">{time}s</div>
                </div>
                <div className="stat-item">
                    <div className="stat-label">Avg. Fix Time</div>
                    <div className="stat-value mono">{fixes > 0 ? (time / fixes).toFixed(1) : 0}s</div>
                </div>
            </div>

            {status === 'completed' && (
                <button
                    onClick={handleDownload}
                    className="run-btn"
                    style={{
                        marginTop: '1.5rem',
                        width: '100%',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        gap: '0.5rem',
                        padding: '0.6rem'
                    }}
                >
                    <Download size={16} />
                    Download results.json
                </button>
            )}
        </div>
    )
}

function UsersIcon({ size }) {
    return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path>
            <circle cx="9" cy="7" r="4"></circle>
            <path d="M23 21v-2a4 4 0 0 0-3-3.87"></path>
            <path d="M16 3.13a4 4 0 0 1 0 7.75"></path>
        </svg>
    )
}
