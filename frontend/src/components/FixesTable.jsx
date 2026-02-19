import React from 'react'
import { FileCode } from 'lucide-react'
import { useAgent } from '../context/AgentContext'

export default function FixesTable() {
    const { state } = useAgent()
    const { summary } = state

    if (!summary || !summary.fixes || summary.fixes.length === 0) return null

    return (
        <div className="glass-card" style={{ padding: 0, overflow: 'hidden' }}>
            <div style={{ padding: '1.5rem', paddingBottom: '0.5rem' }}>
                <h2 className="section-title">
                    <FileCode size={20} />
                    Fixes Applied
                </h2>
            </div>

            <div className="fixes-table-container" style={{ padding: 0 }}>
                <table className="fixes-table">
                    <thead>
                        <tr>
                            <th>File</th>
                            <th>Bug Type</th>
                            <th>Line #</th>
                            <th>Commit</th>
                            <th>Status</th>
                        </tr>
                    </thead>
                    <tbody>
                        {summary.fixes.map((fix, idx) => (
                            <tr key={idx}>
                                <td style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>
                                    {fix.file}
                                </td>
                                <td>
                                    <span className={`bug-type-badge bug-${fix.bug_type}`}>
                                        {fix.bug_type}
                                    </span>
                                </td>
                                <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.85rem' }}>
                                    {fix.line_number || '-'}
                                </td>
                                <td style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                                    {fix.commit_message}
                                </td>
                                <td>
                                    <span className={`status-${fix.status}`}>
                                        {fix.status === 'fixed' ? '✓ Fixed' : '✗ Failed'}
                                    </span>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    )
}
