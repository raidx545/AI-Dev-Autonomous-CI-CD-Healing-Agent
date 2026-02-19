import React from 'react'
import { Trophy, Zap, AlertTriangle, Target } from 'lucide-react'
import { useAgent } from '../context/AgentContext'

export default function ScoreBreakdown() {
    const { state } = useAgent()
    const { summary } = state

    if (!summary || !summary.score) return null

    const { base_score, speed_bonus, efficiency_penalty, final_score } = summary.score

    // Calculate widths for visual bar (max 110)
    const MAX_SCORE = 110;
    const effectiveBase = Math.max(0, base_score - efficiency_penalty);
    const penaltyWidth = Math.min(base_score, efficiency_penalty);

    return (
        <div className="glass-card score-panel">
            <h2 className="section-title">
                <Trophy size={20} style={{ color: 'var(--accent-yellow)' }} />
                Score Breakdown
            </h2>

            <div className="score-final">{final_score}</div>
            <div className="score-label">Total Score</div>

            <div className="score-bar" style={{ marginTop: '2rem', marginBottom: '1.5rem' }}>
                <div className="score-bar-track" style={{ display: 'flex', width: '100%', height: '14px', borderRadius: 'var(--radius-full)', overflow: 'hidden', background: 'var(--bg-glass)', border: '1px solid var(--border-glass)' }}>
                    {/* Active Base */}
                    <div
                        style={{ width: `${(effectiveBase / MAX_SCORE) * 100}%`, background: 'var(--accent-blue)', transition: 'width 1s ease' }}
                        title={`Base: ${effectiveBase}`}
                    />
                    {/* Penalty */}
                    {penaltyWidth > 0 && (
                        <div
                            style={{ width: `${(penaltyWidth / MAX_SCORE) * 100}%`, background: 'var(--accent-red)', opacity: 0.8, transition: 'width 1s ease' }}
                            title={`Penalty: -${penaltyWidth}`}
                        />
                    )}
                    {/* Bonus */}
                    {speed_bonus > 0 && (
                        <div
                            style={{ width: `${(speed_bonus / MAX_SCORE) * 100}%`, background: 'var(--accent-green)', transition: 'width 1s ease' }}
                            title={`Bonus: +${speed_bonus}`}
                        />
                    )}
                </div>
                <div style={{ display: 'flex', justifySelf: 'stretch', justifyContent: 'space-between', fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.5rem', fontFamily: 'var(--font-mono)' }}>
                    <span>0</span>
                    <span>MAX: 110</span>
                </div>
            </div>

            <div className="score-breakdown-list">
                <div className="score-item">
                    <span className="score-item-label">
                        <Target size={14} style={{ display: 'inline', marginRight: 6, verticalAlign: 'text-bottom' }} />
                        Base Score
                    </span>
                    <span className="score-item-value neutral">{base_score}</span>
                </div>
                <div className="score-item">
                    <span className="score-item-label">
                        <Zap size={14} style={{ display: 'inline', marginRight: 6, verticalAlign: 'text-bottom', color: 'var(--accent-green)' }} />
                        Speed Bonus ({'<'} 5 mins)
                    </span>
                    <span className="score-item-value positive">+{speed_bonus}</span>
                </div>
                <div className="score-item">
                    <span className="score-item-label">
                        <AlertTriangle size={14} style={{ display: 'inline', marginRight: 6, verticalAlign: 'text-bottom', color: 'var(--accent-red)' }} />
                        Efficiency Penalty
                    </span>
                    <span className="score-item-value negative">−{efficiency_penalty}</span>
                </div>
            </div>
        </div>
    )
}
