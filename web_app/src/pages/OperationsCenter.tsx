import React, { useState, useEffect, useCallback, useRef } from 'react';
import { TopBar } from '@/components/operations/TopBar';
import { FundingPanel } from '@/components/operations/FundingPanel';
import { WatchQueueColumn } from '@/components/operations/WatchQueueColumn';
import { ReasoningColumn } from '@/components/operations/ReasoningColumn';
import { ExecutionsColumn } from '@/components/operations/ExecutionsColumn';
import { ActivityFeed } from '@/components/operations/ActivityFeed';
import { StatusBar } from '@/components/operations/StatusBar';
import { useOperationsSSE } from '@/hooks/useOperationsSSE';
import { API_BASE } from '@/hooks/useAgentSSE';

interface WalletData {
  address: string;
  label?: string;
  last_signal?: string;
  risk_score?: number;
  times_flagged?: number;
}

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

interface ActivityEntry {
  timestamp: string;
  type: string;
  description: string;
}

const OperationsCenter: React.FC = () => {
  const [showFundingPanel, setShowFundingPanel] = useState(false);
  const [watchedWallets, setWatchedWallets] = useState<WalletData[]>([]);
  const [executions, setExecutions] = useState<ExecutionData[]>([]);
  const [activityFeed, setActivityFeed] = useState<ActivityEntry[]>([]);
  const [selectedWallet, setSelectedWallet] = useState<string | null>(null);
  const [agentStatus, setAgentStatus] = useState<any>(null);
  const [nextCycleIn, setNextCycleIn] = useState<number>(0);
  const [streamStatus, setStreamStatus] = useState<'connected' | 'reconnecting'>('connected');
  const [lastBlock, setLastBlock] = useState<string | null>(null);
  
  const { events, connected, error } = useOperationsSSE();
  const reconnectTimeoutRef = useRef<NodeJS.Timeout>();

  // Load initial data
  useEffect(() => {
    const loadInitialData = async () => {
      try {
        // Load agent status
        const statusRes = await fetch(`${API_BASE}/agent/status`);
        const statusData = await statusRes.json();
        setAgentStatus(statusData);

        // Load watched wallets
        const watchRes = await fetch(`${API_BASE}/agent/watch`);
        const watchData = await watchRes.json();
        setWatchedWallets(watchData.wallets || []);

        // Load execution history
        const historyRes = await fetch(`${API_BASE}/agent/history`);
        const historyData = await historyRes.json();
        setExecutions(historyData.executions || []);
      } catch (err) {
        console.error('Failed to load initial data:', err);
      }
    };

    loadInitialData();
  }, []);

  // Handle SSE events
  useEffect(() => {
    if (events.length === 0) return;

    const latestEvent = events[events.length - 1];
    
    switch (latestEvent.type) {
      case 'cycle_start':
        setActivityFeed(prev => [{
          timestamp: new Date().toISOString(),
          type: 'cycle_start',
          description: `Cycle ${latestEvent.cycle} started - ${latestEvent.total_wallets} wallets to analyze`
        }, ...prev.slice(0, 49)]);
        break;

      case 'wallet_analyzing':
        setActivityFeed(prev => [{
          timestamp: new Date().toISOString(),
          type: 'wallet_analyzing',
          description: `Analyzing ${latestEvent.wallet}${latestEvent.label ? ` (${latestEvent.label})` : ''}`
        }, ...prev.slice(0, 49)]);
        break;

      case 'reasoning_complete':
        setActivityFeed(prev => [{
          timestamp: new Date().toISOString(),
          type: latestEvent.decision.toLowerCase(),
          description: `${latestEvent.decision}: ${latestEvent.wallet} - threat score ${latestEvent.threat_score}`
        }, ...prev.slice(0, 49)]);
        
        // Update watched wallet with new signal
        setWatchedWallets(prev => prev.map(wallet => 
          wallet.address === latestEvent.wallet 
            ? { ...wallet, last_signal: latestEvent.decision, risk_score: latestEvent.threat_score }
            : wallet
        ));
        break;

      case 'execution_start':
        setActivityFeed(prev => [{
          timestamp: new Date().toISOString(),
          type: 'execution_start',
          description: `Starting execution: ${latestEvent.action_type} for ${latestEvent.wallet}`
        }, ...prev.slice(0, 49)]);
        break;

      case 'execution_confirmed':
        setActivityFeed(prev => [{
          timestamp: new Date().toISOString(),
          type: 'tx_confirmed',
          description: `Transaction confirmed: ${latestEvent.tx_hash} for ${latestEvent.wallet}`
        }, ...prev.slice(0, 49)]);

        // Add to executions list
        setExecutions(prev => [{
          id: latestEvent.tx_hash || Date.now().toString(),
          timestamp: new Date().toISOString(),
          wallet: latestEvent.wallet,
          decision: 'ALERT', // Assume confirmed executions were alerts
          action: `transfer ${latestEvent.amount_eth} ETH`,
          status: 'confirmed',
          tx_hash: latestEvent.tx_hash,
          contract_address: latestEvent.contract_address
        }, ...prev.slice(0, 99)]);

        // Update agent balance
        if (agentStatus) {
          setAgentStatus(prev => ({
            ...prev,
            agent_balance_eth: prev.agent_balance_eth + (latestEvent.amount_eth || 0)
          }));
        }
        break;

      case 'execution_failed':
        setActivityFeed(prev => [{
          timestamp: new Date().toISOString(),
          type: 'execution_failed',
          description: `Execution failed for ${latestEvent.wallet}: ${latestEvent.error}`
        }, ...prev.slice(0, 49)]);
        break;

      case 'execution_simulated':
        setActivityFeed(prev => [{
          timestamp: new Date().toISOString(),
          type: 'execution_simulated',
          description: `Simulated: ${latestEvent.action_type} for ${latestEvent.wallet}`
        }, ...prev.slice(0, 49)]);

        // Add to executions list
        setExecutions(prev => [{
          id: latestEvent.tx_hash || Date.now().toString(),
          timestamp: new Date().toISOString(),
          wallet: latestEvent.wallet,
          decision: 'ALERT',
          action: `transfer ${latestEvent.amount_eth} ETH`,
          status: 'simulated',
          tx_hash: latestEvent.tx_hash
        }, ...prev.slice(0, 99)]);
        break;

      case 'agent_idle':
        setNextCycleIn(latestEvent.next_cycle_in);
        break;

      case 'balance_update':
        if (agentStatus) {
          setAgentStatus(prev => ({
            ...prev,
            agent_balance_eth: latestEvent.balance_eth
          }));
        }
        break;

      case 'heartbeat':
        // Ignore heartbeat events
        break;

      default:
        console.log('Unhandled event type:', latestEvent.type);
    }
  }, [events, agentStatus]);

  // Handle connection status
  useEffect(() => {
    if (!connected && !error) {
      setStreamStatus('reconnecting');
    } else if (connected) {
      setStreamStatus('connected');
      // Reload data when reconnecting
      const reloadInitialData = async () => {
        try {
          const watchRes = await fetch(`${API_BASE}/agent/watch`);
          const watchData = await watchRes.json();
          setWatchedWallets(watchData.wallets || []);

          const historyRes = await fetch(`${API_BASE}/agent/history`);
          const historyData = await historyRes.json();
          setExecutions(historyData.executions || []);
        } catch (err) {
          console.error('Failed to reload data:', err);
        }
      };
      reloadInitialData();
    }
  }, [connected, error]);

  // Countdown timer for next cycle
  useEffect(() => {
    if (nextCycleIn <= 0) return;

    const timer = setInterval(() => {
      setNextCycleIn(prev => Math.max(0, prev - 1));
    }, 1000);

    return () => clearInterval(timer);
  }, [nextCycleIn]);

  const handleStartAgent = async () => {
    try {
      await fetch(`${API_BASE}/agent/start`, { method: 'POST' });
      const statusRes = await fetch(`${API_BASE}/agent/status`);
      const statusData = await statusRes.json();
      setAgentStatus(statusData);
    } catch (err) {
      console.error('Failed to start agent:', err);
    }
  };

  const handleStopAgent = async () => {
    try {
      await fetch(`${API_BASE}/agent/stop`, { method: 'POST' });
      const statusRes = await fetch(`${API_BASE}/agent/status`);
      const statusData = await statusRes.json();
      setAgentStatus(statusData);
    } catch (err) {
      console.error('Failed to stop agent:', err);
    }
  };

  const handleAddWallet = async (address: string, label?: string) => {
    try {
      await fetch(`${API_BASE}/agent/watch`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ address, label })
      });
      
      const watchRes = await fetch(`${API_BASE}/agent/watch`);
      const watchData = await watchRes.json();
      setWatchedWallets(watchData.wallets || []);
    } catch (err) {
      console.error('Failed to add wallet:', err);
    }
  };

  const handleRemoveWallet = async (address: string) => {
    try {
      await fetch(`${API_BASE}/agent/watch/${address}`, { method: 'DELETE' });
      setWatchedWallets(prev => prev.filter(w => w.address !== address));
      if (selectedWallet === address) {
        setSelectedWallet(null);
      }
    } catch (err) {
      console.error('Failed to remove wallet:', err);
    }
  };

  return (
    <div className="min-h-screen" style={{ backgroundColor: '#080a10' }}>
      {/* Top Bar */}
      <TopBar
        agentStatus={agentStatus}
        onStartAgent={handleStartAgent}
        onStopAgent={handleStopAgent}
        onToggleFunding={() => setShowFundingPanel(!showFundingPanel)}
      />

      {/* Funding Panel */}
      {showFundingPanel && (
        <FundingPanel
          agentAddress={agentStatus?.agent_wallet}
          currentBalance={agentStatus?.agent_balance_eth || 0}
          onClose={() => setShowFundingPanel(false)}
          onFundingSuccess={(newBalance) => {
            if (agentStatus) {
              setAgentStatus(prev => ({ ...prev, agent_balance_eth: newBalance }));
            }
          }}
        />
      )}

      {/* Main Content - Three Column Layout */}
      <div className="flex" style={{ height: 'calc(100vh - 200px)' }}>
        {/* Left Column - Watch Queue */}
        <div className="w-1/3 border-r" style={{ borderColor: '#1a1f2e', backgroundColor: '#0e1018' }}>
          <WatchQueueColumn
            wallets={watchedWallets}
            selectedWallet={selectedWallet}
            onSelectWallet={setSelectedWallet}
            onAddWallet={handleAddWallet}
            onRemoveWallet={handleRemoveWallet}
          />
        </div>

        {/* Center Column - Agent Reasoning */}
        <div className="w-1/3 border-r" style={{ borderColor: '#1a1f2e', backgroundColor: '#0e1018' }}>
          <ReasoningColumn
            selectedWallet={selectedWallet}
            nextCycleIn={nextCycleIn}
            isRunning={agentStatus?.running}
          />
        </div>

        {/* Right Column - Executions */}
        <div className="w-1/3" style={{ backgroundColor: '#0e1018' }}>
          <ExecutionsColumn executions={executions} />
        </div>
      </div>

      {/* Activity Feed */}
      <div className="border-t" style={{ borderColor: '#1a1f2e', backgroundColor: '#0e1018', height: '120px' }}>
        <ActivityFeed activities={activityFeed} />
      </div>

      {/* Status Bar */}
      <div className="border-t" style={{ borderColor: '#1a1f2e', backgroundColor: '#080a10' }}>
        <StatusBar
          lastBlock={lastBlock}
          nextCycleIn={nextCycleIn}
          streamStatus={streamStatus}
        />
      </div>
    </div>
  );
};

export default OperationsCenter;
