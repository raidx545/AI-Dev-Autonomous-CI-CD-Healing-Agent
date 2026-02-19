import { useEffect, useRef, useCallback } from 'react'
import { useAgent } from '../context/AgentContext'

export function useWebSocket(runId) {
    const wsRef = useRef(null)
    const { addEvent, setSummary, setError } = useAgent()

    const connect = useCallback(() => {
        if (!runId) return

        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
        const host = window.location.host
        const url = `${protocol}//${host}/ws/${runId}`

        const ws = new WebSocket(url)
        wsRef.current = ws

        ws.onopen = () => {
            console.log(`[WS] Connected to ${runId}`)
        }

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data)

                // Add to events log
                addEvent(data)

                // If run is complete, fetch the full summary
                if (data.event_type === 'run_complete' || data.event_type === 'error') {
                    fetchSummary(runId)
                }
            } catch (e) {
                console.error('[WS] Parse error:', e)
            }
        }

        ws.onerror = (error) => {
            console.error('[WS] Error:', error)
        }

        ws.onclose = (event) => {
            console.log(`[WS] Disconnected (code=${event.code})`)
            // Auto-reconnect if not a normal close and still running
            if (event.code !== 1000) {
                setTimeout(() => connect(), 3000)
            }
        }
    }, [runId, addEvent])

    const fetchSummary = useCallback(async (id) => {
        try {
            const resp = await fetch(`/api/runs/${id}`)
            if (resp.ok) {
                const data = await resp.json()
                if (data.summary) {
                    setSummary(data.summary)
                } else {
                    setSummary(data)
                }
            }
        } catch (e) {
            setError('Failed to fetch run summary')
        }
    }, [setSummary, setError])

    useEffect(() => {
        connect()
        return () => {
            if (wsRef.current) {
                wsRef.current.close(1000)
            }
        }
    }, [connect])

    return wsRef
}
