import React from 'react'
import { Trophy, Zap, AlertTriangle } from 'lucide-react'
import { useAgent } from '../context/AgentContext'

export default function ScoreBreakdown() {
    const { state } = useAgent()
    const { summary } = state

    if (!summary || !summary.score) return null

    const { base_score, speed_bonus, efficiency_penalty, final_score } = summary.score

    return (
        <div className="glass-card score-panel">
            <h2 className="section-title">
                <Trophy size={20} className="text-yellow-500" />
                Score Breakdown
            </h2>

            <div className="score-final">{final_score}</div>
            <div className="score-label">Total Score</div>

            <div className="score-bar">
                <div className="score-bar-track">
                    <div
                        className="score-bar-fill"
                        style={{ width: `${Math.min(100, Math.max(0, final_score))}%` }}
                    />
                </div>
            </div>

            <div className="score-breakdown-list">
                <div className="score-item">
                    <span className="score-item-label">Base Score</span>
                    <span className="score-item-value neutral">{base_score}</span>
                </div>
                <div className="score-item">
                    <span className="score-item-label">
                        <Zap size={12} style={{ display: 'inline', marginRight: 4 }} />
                        Speed Bonus ({'<'} 5 mins)
                    </span>
                    <span className="score-item-value positive">+{speed_bonus}</span>
                </div>
                <div className="score-item">
                    <span className="score-item-label">
                        <AlertTriangle size={12} style={{ display: 'inline', marginRight: 4 }} />
                        Efficiency Penalty
                    </span>
                    <span className="score-item-value negative">−{efficiency_penalty}</span>
                </div>
            </div>
        </div>
    )
}
