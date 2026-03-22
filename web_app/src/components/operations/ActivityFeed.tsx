import React from 'react';

interface ActivityEntry {
  timestamp: string;
  type: string;
  description: string;
}

interface ActivityFeedProps {
  activities: ActivityEntry[];
}

export const ActivityFeed: React.FC<ActivityFeedProps> = ({ activities }) => {
  const formatTime = (timestamp: string) => {
    const date = new Date(timestamp);
    return date.toLocaleTimeString('en-US', { 
      hour12: false, 
      hour: '2-digit', 
      minute: '2-digit', 
      second: '2-digit' 
    });
  };

  const getEventColor = (type: string) => {
    switch (type) {
      case 'cycle_start':
      case 'wallet_cached':
      case 'agent_idle':
        return '#64748b';
      case 'MONITOR':
        return '#f59e0b';
      case 'ALERT':
      case 'transfer_sent':
        return '#3b82f6';
      case 'INTERVENE':
      case 'contract_deployed':
        return '#ef4444';
      case 'tx_confirmed':
        return '#22c55e';
      default:
        return '#64748b';
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-4 py-2 border-b" style={{ 
        borderColor: '#1a1f2e',
        backgroundColor: '#080a10'
      }}>
        <h3 style={{ 
          color: '#e2e8f0', 
          fontSize: '12px', 
          fontWeight: '600' 
        }}>
          Activity Feed
        </h3>
      </div>

      {/* Feed Content */}
      <div className="flex-1 overflow-y-auto p-2">
        {activities.length === 0 ? (
          <div className="text-center py-4" style={{ color: '#64748b', fontSize: '11px' }}>
            No activity yet
          </div>
        ) : (
          <div className="space-y-1">
            {activities.map((activity, index) => (
              <div
                key={`${activity.timestamp}-${index}`}
                className="flex items-start gap-2 py-1"
                style={{
                  fontSize: '11px',
                  fontFamily: 'monospace',
                  lineHeight: '1.3',
                  color: getEventColor(activity.type)
                }}
              >
                <span style={{ color: '#64748b', minWidth: '60px' }}>
                  {formatTime(activity.timestamp)}
                </span>
                <span style={{ minWidth: '100px' }}>
                  {activity.type.toUpperCase()}
                </span>
                <span style={{ color: '#e2e8f0', flex: 1 }}>
                  {activity.description}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
