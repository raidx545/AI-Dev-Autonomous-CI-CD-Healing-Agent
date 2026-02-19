import React from 'react'
import { Activity } from 'lucide-react'
import { useAgent } from '../context/AgentContext'

export default function CICDTimeline() {
    const { state } = useAgent()
    const { summary } = state

    if (!summary || !summary.iterations || summary.iterations.length === 0) return null

    return (
        <div className="glass-card timeline-container">
            <h2 className="section-title">
                <Activity size={20} />
                CI/CD Pipeline
            </h2>
            <p className="section-subtitle" style={{ marginBottom: '1.5rem' }}>
                Automated iteration history
            </p>

            <div className="timeline">
                {summary.iterations.map((it, idx) => {
                    const isSuccess = it.failures_after === 0
                    const statusClass = isSuccess ? 'success' : 'failed'

                    return (
                        <div className="timeline-item" key={idx}>
                            <div className={`timeline-dot ${statusClass}`} />
                            <div className="timeline-content">
                                <div className="timeline-header">
                                    <div className="timeline-title">
                                        Iteration {it.iteration}
                                    </div>
                                    <div className="timeline-time">
                                        {new Date(it.timestamp).toLocaleTimeString()}
                                    </div>
                                </div>
                                <div className="timeline-details">
                                    Failures: <span style={{ color: 'var(--accent-red)' }}>{it.failures_before}</span>
                                    {' → '}
                                    <span style={{ color: isSuccess ? 'var(--accent-green)' : 'var(--accent-red)' }}>
                                        {it.failures_after}
                                    </span>
                                </div>
                            </div>
                        </div>
                    )
                })}
            </div>

            <div style={{ marginTop: '1rem', textAlign: 'center', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                Total Iterations: <span className="iteration-count">{summary.iterations.length}/5</span>
            </div>
        </div>
    )
}
