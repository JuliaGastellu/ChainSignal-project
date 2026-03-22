import React from 'react';

interface StatusBarProps {
  lastBlock: string | null;
  nextCycleIn: number;
  streamStatus: 'connected' | 'reconnecting';
}

export const StatusBar: React.FC<StatusBarProps> = ({
  lastBlock,
  nextCycleIn,
  streamStatus
}) => {
  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'connected': return '#22c55e';
      case 'reconnecting': return '#f59e0b';
      default: return '#64748b';
    }
  };

  return (
    <div className="flex items-center justify-between px-4 py-2" style={{ 
      fontSize: '11px',
      fontFamily: 'monospace',
      color: '#64748b'
    }}>
      <div className="flex items-center gap-6">
        {/* Last Block */}
        <div className="flex items-center gap-2">
          <span>Last Block:</span>
          <span style={{ color: '#e2e8f0' }}>
            {lastBlock || 'N/A'}
          </span>
        </div>

        {/* Next Cycle */}
        <div className="flex items-center gap-2">
          <span>Next Cycle:</span>
          <span style={{ color: '#e2e8f0' }}>
            {formatTime(nextCycleIn)}
          </span>
        </div>

        {/* WDK Mode */}
        <div className="flex items-center gap-2">
          <span>WDK Mode:</span>
          <span 
            className="px-2 py-0.5 text-xs"
            style={{
              backgroundColor: '#22c55e20',
              color: '#22c55e',
              border: '1px solid #22c55e40'
            }}
          >
            WDK Live
          </span>
        </div>
      </div>

      {/* Stream Status */}
      <div className="flex items-center gap-2">
        <span>Stream:</span>
        <span 
          className="px-2 py-0.5 text-xs"
          style={{
            backgroundColor: streamStatus === 'connected' ? '#22c55e20' : '#f59e0b20',
            color: getStatusColor(streamStatus),
            border: `1px solid ${getStatusColor(streamStatus)}40`
          }}
        >
          {streamStatus === 'connected' ? 'Connected' : 'Reconnecting...'}
        </span>
      </div>
    </div>
  );
};
