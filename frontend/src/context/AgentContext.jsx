import React, { createContext, useContext, useReducer, useCallback } from 'react'

const AgentContext = createContext(null)

const initialState = {
    status: 'idle', // idle, running, completed, error
    runId: null,
    summary: null,
    events: [],
    error: null,
}

function agentReducer(state, action) {
    switch (action.type) {
        case 'START_RUN':
            return {
                ...initialState,
                status: 'running',
                runId: action.runId,
                events: [],
            }
        case 'ADD_EVENT':
            return {
                ...state,
                events: [...state.events, action.event],
            }
        case 'SET_SUMMARY':
            return {
                ...state,
                status: 'completed',
                summary: action.summary,
            }
        case 'SET_ERROR':
            return {
                ...state,
                status: 'error',
                error: action.error,
            }
        case 'RESET':
            return initialState
        default:
            return state
    }
}

export function AgentProvider({ children }) {
    const [state, dispatch] = useReducer(agentReducer, initialState)

    const startRun = useCallback((runId) => {
        dispatch({ type: 'START_RUN', runId })
    }, [])

    const addEvent = useCallback((event) => {
        dispatch({ type: 'ADD_EVENT', event })
    }, [])

    const setSummary = useCallback((summary) => {
        dispatch({ type: 'SET_SUMMARY', summary })
    }, [])

    const setError = useCallback((error) => {
        dispatch({ type: 'SET_ERROR', error })
    }, [])

    const reset = useCallback(() => {
        dispatch({ type: 'RESET' })
    }, [])

    return (
        <AgentContext.Provider value={{ state, startRun, addEvent, setSummary, setError, reset }}>
            {children}
        </AgentContext.Provider>
    )
}

export function useAgent() {
    const ctx = useContext(AgentContext)
    if (!ctx) throw new Error('useAgent must be inside AgentProvider')
    return ctx
}
