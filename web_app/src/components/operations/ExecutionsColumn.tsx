import React from 'react';

interface ExecutionData {
  id: string;
  timestamp: string;
  wallet: string;
  decision: string;
  action: string;
  status: string;
  tx_hash?: string;
  contract_address?: string;
}

interface ExecutionsColumnProps {
  executions: ExecutionData[];
}

export const ExecutionsColumn: React.FC<ExecutionsColumnProps> = ({ executions }) => {
  const formatAddress = (address: string) => {
    return `${address.slice(0, 6)}...${address.slice(-4)}`;
  };

  const formatTxHash = (hash: string) => {
    return `${hash.slice(0, 8)}...${hash.slice(-6)}`;
  };

  const getRelativeTime = (timestamp: string) => {
    const now = new Date();
    const then = new Date(timestamp);
    const diffMs = now.getTime() - then.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    
    if (diffMins < 1) return 'just now';
    if (diffMins < 60) return `${diffMins} min ago`;
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`;
    const diffDays = Math.floor(diffHours / 24);
    return `${diffDays} day${diffDays > 1 ? 's' : ''} ago`;
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'confirmed': return '#22c55e';
      case 'failed': return '#ef4444';
      case 'simulated': return '#64748b';
      default: return '#64748b';
    }
  };

  const getStatusBg = (status: string) => {
    switch (status) {
      case 'confirmed': return '#22c55e20';
      case 'failed': return '#ef444420';
      case 'simulated': return '#64748b20';
      default: return '#64748b20';
    }
  };

  const getDecisionColor = (decision: string) => {
    switch (decision) {
      case 'MONITOR': return '#f59e0b';
      case 'ALERT': return '#3b82f6';
      case 'INTERVENE': return '#ef4444';
      default: return '#64748b';
    }
  };

  const getDecisionBg = (decision: string) => {
    switch (decision) {
      case 'MONITOR': return '#f59e0b20';
      case 'ALERT': return '#3b82f620';
      case 'INTERVENE': return '#ef444420';
      default: return '#64748b20';
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-4 py-3 border-b" style={{ 
        borderColor: '#1a1f2e',
        backgroundColor: '#080a10'
      }}>
        <h2 style={{ 
          color: '#e2e8f0', 
          fontSize: '14px', 
          fontWeight: '600' 
        }}>
          Executions
        </h2>
      </div>

      {/* Executions List */}
      <div className="flex-1 overflow-y-auto">
        {executions.length === 0 ? (
          <div className="p-4 text-center" style={{ color: '#64748b', fontSize: '12px' }}>
            No executions yet
          </div>
        ) : (
          <div className="p-2">
            {executions.map((execution, index) => (
              <div
                key={execution.id}
                className="p-3 mb-2 border"
                style={{
                  borderColor: '#1a1f2e',
                  backgroundColor: index === 0 ? '#22c55e10' : 'transparent',
                  animation: index === 0 ? 'flashGreen 1s ease-out' : 'none'
                }}
              >
                <div className="flex items-center justify-between mb-2">
                  <div style={{ 
                    color: '#64748b', 
                    fontSize: '11px',
                    fontFamily: 'monospace'
                  }}>
                    {getRelativeTime(execution.timestamp)}
                  </div>
                  
                  <span 
                    className="px-2 py-0.5 text-xs font-medium"
                    style={{
                      backgroundColor: getStatusBg(execution.status),
                      color: getStatusColor(execution.status),
                      border: `1px solid ${getStatusColor(execution.status)}40`
                    }}
                  >
                    {execution.status}
                  </span>
                </div>

                <div className="mb-2">
                  <div style={{ 
                    color: '#e2e8f0', 
                    fontSize: '13px',
                    fontFamily: 'monospace',
                    marginBottom: '4px'
                  }}>
                    {formatAddress(execution.wallet)}
                  </div>
                  
                  <div className="flex items-center gap-2">
                    <span 
                      className="px-2 py-0.5 text-xs font-medium"
                      style={{
                        backgroundColor: getDecisionBg(execution.decision),
                        color: getDecisionColor(execution.decision),
                        border: `1px solid ${getDecisionColor(execution.decision)}40`
                      }}
                    >
                      {execution.decision}
                    </span>
                    
                    <span style={{ 
                      color: '#e2e8f0', 
                      fontSize: '12px' 
                    }}>
                      {execution.action}
                    </span>
                  </div>
                </div>

                <div className="flex items-center gap-3">
                  {execution.tx_hash && (
                    <a
                      href={`https://sepolia.etherscan.io/tx/${execution.tx_hash}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{ 
                        color: '#3b82f6', 
                        fontSize: '11px',
                        fontFamily: 'monospace',
                        textDecoration: 'underline',
                        cursor: 'pointer'
                      }}
                    >
                      {formatTxHash(execution.tx_hash)}
                    </a>
                  )}
                  
                  {execution.contract_address && (
                    <a
                      href={`https://sepolia.etherscan.io/address/${execution.contract_address}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{ 
                        color: '#3b82f6', 
                        fontSize: '11px',
                        fontFamily: 'monospace',
                        textDecoration: 'underline',
                        cursor: 'pointer'
                      }}
                    >
                      Contract: {formatAddress(execution.contract_address)}
                    </a>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <style jsx>{`
        @keyframes flashGreen {
          0% { background-color: transparent; }
          50% { background-color: #22c55e30; }
          100% { background-color: #22c55e10; }
        }
      `}</style>
    </div>
  );
};
