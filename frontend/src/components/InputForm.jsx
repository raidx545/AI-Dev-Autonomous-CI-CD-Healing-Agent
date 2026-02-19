import React, { useState } from 'react'
import { Play, Loader2, Github, User, Users } from 'lucide-react'
import { useAgent } from '../context/AgentContext'
import axios from 'axios'

export default function InputForm() {
    const { startRun, state } = useAgent()
    const [loading, setLoading] = useState(false)
    const [formData, setFormData] = useState({
        repo_url: '',
        team_name: '',
        leader_name: '',
        github_token: ''
    })

    const handleSubmit = async (e) => {
        e.preventDefault()
        setLoading(true)

        try {
            const baseUrl = import.meta.env.VITE_API_BASE_URL || ''
            const response = await axios.post(`${baseUrl}/api/runs`, formData)
            startRun(response.data.run_id)
        } catch (error) {
            console.error('Failed to start run:', error)
            alert('Failed to start run. Check console for details.')
        } finally {
            setLoading(false)
        }
    }

    if (state.status !== 'idle') return null

    return (
        <div className="glass-card input-form">
            <h2 className="section-title">
                <Github size={20} />
                Start New Analysis
            </h2>
            <p className="section-subtitle" style={{ marginBottom: '1.5rem' }}>
                Enter repository details to begin autonomous debugging
            </p>

            <form onSubmit={handleSubmit}>
                <div className="form-group">
                    <label>GitHub Repository URL</label>
                    <input
                        required
                        type="url"
                        placeholder="https://github.com/username/repo"
                        value={formData.repo_url}
                        onChange={e => setFormData({ ...formData, repo_url: e.target.value })}
                    />
                </div>

                <div className="dashboard-grid" style={{ marginTop: 0, marginBottom: '1.25rem' }}>
                    <div className="form-group" style={{ marginBottom: 0 }}>
                        <label><Users size={14} style={{ display: 'inline', marginRight: 4 }} /> Team Name</label>
                        <input
                            required
                            type="text"
                            placeholder="e.g. Code Warriors"
                            value={formData.team_name}
                            onChange={e => setFormData({ ...formData, team_name: e.target.value })}
                        />
                    </div>
                    <div className="form-group" style={{ marginBottom: 0 }}>
                        <label><User size={14} style={{ display: 'inline', marginRight: 4 }} /> Team Leader</label>
                        <input
                            required
                            type="text"
                            placeholder="e.g. Jane Doe"
                            value={formData.leader_name}
                            onChange={e => setFormData({ ...formData, leader_name: e.target.value })}
                        />
                    </div>
                </div>

                <div className="form-group">
                    <label>GitHub Token (Optional)</label>
                    <input
                        type="password"
                        placeholder="ghp_..."
                        value={formData.github_token}
                        onChange={e => setFormData({ ...formData, github_token: e.target.value })}
                    />
                </div>

                <button type="submit" className="btn-primary" disabled={loading}>
                    {loading ? (
                        <>
                            <Loader2 className="spinner" />
                            Initializing Agent...
                        </>
                    ) : (
                        <>
                            <Play size={18} fill="currentColor" />
                            Run Agent
                        </>
                    )}
                </button>
            </form>
        </div>
    )
}
