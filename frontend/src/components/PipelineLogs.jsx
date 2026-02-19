import React, { useEffect, useRef } from 'react'
import { Terminal } from 'lucide-react'
import { useAgent } from '../context/AgentContext'

export default function PipelineLogs() {
    const { state } = useAgent()
    const bottomRef = useRef(null)

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
    }, [state.events])

    if (state.status === 'idle') return null

    return (
        <div className="glass-card logs-container full-width">
            <h2 className="section-title">
                <Terminal size={20} />
                Live Agent Logs
            </h2>

            <div className="logs-terminal">
                {state.events.map((ev, idx) => (
                    <div className={`log-line phase-${ev.phase}`} key={idx}>
                        <span className="log-phase">
                            [{ev.phase?.replace('_', ' ').toUpperCase() || 'INFO'}]
                        </span>
                        <span className="log-message">{ev.message}</span>
                    </div>
                ))}
                {state.status === 'running' && (
                    <div className="log-line">
                        <span className="log-phase">...</span>
                        <span className="log-message"><span className="pulse-dot" style={{ display: 'inline-block' }} /> Processing</span>
                    </div>
                )}
                <div ref={bottomRef} />
            </div>
        </div>
    )
}
