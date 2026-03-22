import React from 'react';

interface TopBarProps {
  agentStatus: any;
  onStartAgent: () => void;
  onStopAgent: () => void;
  onToggleFunding: () => void;
}

export const TopBar: React.FC<TopBarProps> = ({
  agentStatus,
  onStartAgent,
  onStopAgent,
  onToggleFunding
}) => {
  const formatAddress = (address: string) => {
    if (!address) return 'Unknown';
    return `${address.slice(0, 6)}...${address.slice(-4)}`;
  };

  const isRunning = agentStatus?.running || false;

  return (
    <div className="flex items-center justify-between px-4 py-3 border-b" style={{ 
      backgroundColor: '#0e1018', 
      borderColor: '#1a1f2e',
      color: '#e2e8f0'
    }}>
      {/* Left side - Agent info */}
      <div className="flex items-center gap-6">
        <div className="flex items-center gap-2">
          <span style={{ color: '#64748b', fontSize: '12px' }}>Agent:</span>
          <span 
            style={{ 
              fontFamily: 'monospace', 
              fontSize: '14px',
              cursor: 'help'
            }}
            title={agentStatus?.agent_wallet || 'Unknown'}
          >
            {formatAddress(agentStatus?.agent_wallet || '')}
          </span>
        </div>

        <div className="flex items-center gap-2">
          <span style={{ color: '#64748b', fontSize: '12px' }}>Balance:</span>
          <span style={{ fontFamily: 'monospace', fontSize: '14px' }}>
            {(agentStatus?.agent_balance_eth || 0).toFixed(4)} ETH
          </span>
        </div>

        <div className="flex items-center gap-2">
          <span style={{ color: '#64748b', fontSize: '12px' }}>Total Moved:</span>
          <span style={{ fontFamily: 'monospace', fontSize: '14px' }}>
            {(agentStatus?.total_eth_moved || 0).toFixed(4)} ETH
          </span>
        </div>

        <div className="flex items-center gap-2">
          <span style={{ color: '#64748b', fontSize: '12px' }}>Status:</span>
          <span 
            className="px-2 py-1 text-xs font-medium"
            style={{
              backgroundColor: isRunning ? '#22c55e20' : '#64748b20',
              color: isRunning ? '#22c55e' : '#64748b',
              border: `1px solid ${isRunning ? '#22c55e40' : '#64748b40'}`
            }}
          >
            {isRunning ? 'RUNNING' : 'STOPPED'}
          </span>
        </div>
      </div>

      {/* Right side - Controls */}
      <div className="flex items-center gap-3">
        <button
          onClick={onStartAgent}
          disabled={isRunning}
          className="px-3 py-1.5 text-sm font-medium border"
          style={{
            backgroundColor: isRunning ? '#1a1f2e' : '#22c55e10',
            color: isRunning ? '#64748b' : '#22c55e',
            borderColor: isRunning ? '#1a1f2e' : '#22c55e40',
            cursor: isRunning ? 'not-allowed' : 'pointer'
          }}
        >
          Start Agent
        </button>

        <button
          onClick={onStopAgent}
          disabled={!isRunning}
          className="px-3 py-1.5 text-sm font-medium border"
          style={{
            backgroundColor: !isRunning ? '#1a1f2e' : '#ef444410',
            color: !isRunning ? '#64748b' : '#ef4444',
            borderColor: !isRunning ? '#1a1f2e' : '#ef444440',
            cursor: !isRunning ? 'not-allowed' : 'pointer'
          }}
        >
          Stop Agent
        </button>

        <button
          onClick={onToggleFunding}
          className="px-3 py-1.5 text-sm font-medium border"
          style={{
            backgroundColor: '#3b82f610',
            color: '#3b82f6',
            borderColor: '#3b82f640',
            cursor: 'pointer'
          }}
        >
          Fund Agent
        </button>
      </div>
    </div>
  );
};
