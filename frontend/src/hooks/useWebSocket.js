import { useEffect, useRef, useCallback } from 'react'
import { useAgent } from '../context/AgentContext'

const BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

function getApiUrl(path) {
    return `${BASE_URL}${path}`
}

function getWsUrl(runId) {
    if (BASE_URL) {
        // Convert https:// → wss://, http:// → ws:// for the deployed backend
        return BASE_URL.replace(/^https/, 'wss').replace(/^http/, 'ws') + `/ws/${runId}`
    }
    // Local dev: use Vite proxy on the same host
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    return `${protocol}//${window.location.host}/ws/${runId}`
}

export function useWebSocket(runId) {
    const wsRef = useRef(null)
    const pollRef = useRef(null)
    const completedRef = useRef(false)
    const { addEvent, setSummary, setError } = useAgent()

    const fetchSummary = useCallback(async (id) => {
        try {
            const resp = await fetch(getApiUrl(`/api/runs/${id}`))
            if (resp.ok) {
                const data = await resp.json()
                if (data.summary) {
                    setSummary(data.summary)
                    return true // run is done
                } else if (data.status === 'completed' || data.status === 'failed') {
                    setSummary(data)
                    return true
                }
            }
        } catch (e) {
            console.warn('[WS] fetchSummary failed:', e)
        }
        return false // run still in progress
    }, [setSummary])

    const stopPolling = useCallback(() => {
        if (pollRef.current) {
            clearInterval(pollRef.current)
            pollRef.current = null
        }
    }, [])

    // Polling fallback — kicks in when WS drops before run_complete
    const startPolling = useCallback((id) => {
        if (pollRef.current || completedRef.current) return
        console.log('[WS] Starting polling fallback for run:', id)
        pollRef.current = setInterval(async () => {
            const done = await fetchSummary(id)
            if (done) {
                completedRef.current = true
                stopPolling()
            }
        }, 4000)
    }, [fetchSummary, stopPolling])

    const connect = useCallback(() => {
        if (!runId) return

        const url = getWsUrl(runId)
        console.log('[WS] Connecting to:', url)

        const ws = new WebSocket(url)
        wsRef.current = ws

        ws.onopen = () => {
            console.log(`[WS] Connected to ${runId}`)
            stopPolling() // stop polling if WS reconnects
        }

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data)

                // Ignore heartbeat pings — don't flood the event log
                if (data.event_type === 'ping') return

                addEvent(data)

                if (data.event_type === 'run_complete' || data.event_type === 'error') {
                    completedRef.current = true
                    stopPolling()
                    fetchSummary(runId)
                }
            } catch (e) {
                console.error('[WS] Parse error:', e)
            }
        }

        ws.onerror = (error) => {
            console.error('[WS] Error:', error)
            // Start polling immediately on WS error so user still sees results
            if (!completedRef.current) startPolling(runId)
        }

        ws.onclose = (event) => {
            console.log(`[WS] Disconnected (code=${event.code})`)
            if (!completedRef.current) {
                // Start polling so we don't miss the final result
                startPolling(runId)
                // Also try to reconnect after 5s (in case it was a transient drop)
                if (event.code !== 1000) {
                    setTimeout(() => {
                        if (!completedRef.current) connect()
                    }, 5000)
                }
            }
        }
    }, [runId, addEvent, fetchSummary, startPolling, stopPolling])

    useEffect(() => {
        completedRef.current = false
        connect()
        return () => {
            stopPolling()
            if (wsRef.current) {
                wsRef.current.close(1000)
            }
        }
    }, [connect, stopPolling])

    return wsRef
}
