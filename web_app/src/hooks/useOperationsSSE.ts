import { useState, useEffect, useRef, useCallback } from 'react';
import { API_BASE } from './useAgentSSE';

interface SSEEvent {
  type: string;
  [key: string]: any;
}

export const useOperationsSSE = () => {
  const [events, setEvents] = useState<SSEEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout>();
  const reconnectAttemptsRef = useRef(0);
  const maxReconnectDelay = 30000; // 30 seconds max

  const connect = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    try {
      eventSourceRef.current = new EventSource(`${API_BASE}/agent/stream`);
      
      eventSourceRef.current.onopen = () => {
        setConnected(true);
        setError(null);
        reconnectAttemptsRef.current = 0;
      };

      eventSourceRef.current.onmessage = (event) => {
        try {
          const data = event.data;
          
          // Skip heartbeat comments
          if (data.startsWith(':')) {
            return;
          }

          const parsedEvent = JSON.parse(data);
          setEvents(prev => [...prev, parsedEvent]);
        } catch (err) {
          console.error('Failed to parse SSE event:', err);
        }
      };

      eventSourceRef.current.onerror = () => {
        setConnected(false);
        setError('Connection error');
        
        if (eventSourceRef.current) {
          eventSourceRef.current.close();
          eventSourceRef.current = null;
        }

        // Exponential backoff with max delay
        const delay = Math.min(5000 * Math.pow(2, reconnectAttemptsRef.current), maxReconnectDelay);
        reconnectAttemptsRef.current++;

        reconnectTimeoutRef.current = setTimeout(() => {
          connect();
        }, delay);
      };

      eventSourceRef.current.onclose = () => {
        setConnected(false);
      };

    } catch (err) {
      setError('Failed to create connection');
      console.error('SSE connection failed:', err);
    }
  }, []);

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
    }
    
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    
    setConnected(false);
  }, []);

  useEffect(() => {
    connect();
    
    return () => {
      disconnect();
    };
  }, [connect, disconnect]);

  return {
    events,
    connected,
    error,
    reconnect: connect,
    disconnect
  };
};
