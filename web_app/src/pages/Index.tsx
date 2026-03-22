import React, { useState, useEffect, useCallback, useRef } from 'react';
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

const Index: React.FC = () => {
  const [showFundingPanel, setShowFundingPanel] = useState(false);
  const [watchedWallets, setWatchedWallets] = useState<WalletData[]>([]);
  const [executions, setExecutions] = useState<ExecutionData[]>([]);
  const [selectedWallet, setSelectedWallet] = useState<string | null>(null);
  const [agentStatus, setAgentStatus] = useState<any>(null);
  const [nextCycleIn, setNextCycleIn] = useState<number>(0);
  const [streamStatus, setStreamStatus] = useState<'connected' | 'reconnecting'>('connected');
  const [lastBlock, setLastBlock] = useState<string | null>(null);
  
  const { events, connected, error } = useOperationsSSE();

  // Load initial data
  useEffect(() => {
    const loadInitialData = async () => {
      try {
        const statusRes = await fetch(`${API_BASE}/agent/status`);
        const statusData = await statusRes.json();
        setAgentStatus(statusData);

        const watchRes = await fetch(`${API_BASE}/agent/watch`);
        const watchData = await watchRes.json();
        setWatchedWallets(watchData.wallets || []);

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
        setNextCycleIn(20); // Reset countdown
        break;
      case 'agent_idle':
        setNextCycleIn(latestEvent.next_cycle_in || 0);
        break;
      case 'reasoning_complete':
        setWatchedWallets(prev => prev.map(wallet => 
          wallet.address === latestEvent.wallet 
            ? { ...wallet, last_signal: latestEvent.decision, risk_score: latestEvent.threat_score }
            : wallet
        ));
        break;
      case 'execution_confirmed':
        setExecutions(prev => [{
          id: latestEvent.tx_hash || Date.now().toString(),
          timestamp: new Date().toISOString(),
          wallet: latestEvent.wallet,
          decision: 'ALERT',
          action: `transfer ${latestEvent.amount_eth || 0} ETH`,
          status: 'confirmed',
          tx_hash: latestEvent.tx_hash,
          contract_address: latestEvent.contract_address
        }, ...prev.slice(0, 99)]);
        break;
      case 'balance_update':
        if (agentStatus) {
          setAgentStatus(prev => ({
            ...prev,
            agent_balance_eth: latestEvent.balance_eth
          }));
        }
        break;
    }
  }, [events, agentStatus]);

  // Handle connection status
  useEffect(() => {
    setStreamStatus(connected ? 'connected' : 'reconnecting');
  }, [connected]);

  // Countdown timer
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

  const formatAddress = (address: string) => `${address.slice(0, 6)}...${address.slice(-4)}`;
  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  return (
    <div style={{ 
      height: '100vh', 
      backgroundColor: '#080a10',
      fontFamily: 'system-ui, sans-serif',
      overflow: 'hidden',
      display: 'flex',
      flexDirection: 'column'
    }}>
      {/* TOP BAR */}
      <div style={{
        height: '56px',
        backgroundColor: '#0e1018',
        borderBottom: '1px solid #1a1f2e',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 20px',
        flexShrink: 0
      }}>
        {/* Left - Title */}
        <div style={{ 
          color: '#e2e8f0', 
          fontSize: '14px', 
          fontFamily: "'Courier New', monospace",
          fontWeight: '600'
        }}>
          ChainSignal
        </div>

        {/* Center - Agent Info */}
        <div style={{ 
          display: 'flex', 
          alignItems: 'center', 
          gap: '20px',
          color: '#e2e8f0',
          fontSize: '13px'
        }}>
          <div style={{ fontFamily: "'Courier New', monospace" }}>
            {formatAddress(agentStatus?.agent_wallet || '')}
          </div>
          <div style={{ fontFamily: "'Courier New', monospace" }}>
            {(agentStatus?.agent_balance_eth || 0).toFixed(4)} ETH
          </div>
          <div style={{
            padding: '4px 8px',
            borderRadius: '3px',
            fontSize: '11px',
            backgroundColor: agentStatus?.running ? '#22c55e20' : '#64748b20',
            color: agentStatus?.running ? '#22c55e' : '#64748b',
            border: `1px solid ${agentStatus?.running ? '#22c55e40' : '#64748b40'}`
          }}>
            {agentStatus?.running ? 'RUNNING' : 'STOPPED'}
          </div>
        </div>

        {/* Right - Buttons */}
        <div style={{ display: 'flex', gap: '8px' }}>
          <button
            onClick={() => setShowFundingPanel(!showFundingPanel)}
            style={{
              padding: '6px 14px',
              fontSize: '13px',
              backgroundColor: '#3b82f610',
              color: '#3b82f6',
              border: '1px solid #3b82f640',
              borderRadius: '3px',
              cursor: 'pointer',
              whiteSpace: 'nowrap'
            }}
          >
            Fund
          </button>
          <button
            onClick={handleStartAgent}
            disabled={agentStatus?.running}
            style={{
              padding: '6px 14px',
              fontSize: '13px',
              backgroundColor: agentStatus?.running ? '#1a1f2e' : '#22c55e10',
              color: agentStatus?.running ? '#64748b' : '#22c55e',
              border: `1px solid ${agentStatus?.running ? '#1a1f2e' : '#22c55e40'}`,
              borderRadius: '3px',
              cursor: agentStatus?.running ? 'not-allowed' : 'pointer',
              whiteSpace: 'nowrap'
            }}
          >
            Start
          </button>
          <button
            onClick={handleStopAgent}
            disabled={!agentStatus?.running}
            style={{
              padding: '6px 14px',
              fontSize: '13px',
              backgroundColor: !agentStatus?.running ? '#1a1f2e' : '#ef444410',
              color: !agentStatus?.running ? '#64748b' : '#ef4444',
              border: `1px solid ${!agentStatus?.running ? '#1a1f2e' : '#ef444440'}`,
              borderRadius: '3px',
              cursor: !agentStatus?.running ? 'not-allowed' : 'pointer',
              whiteSpace: 'nowrap'
            }}
          >
            Stop
          </button>
        </div>
      </div>

      {/* FUNDING PANEL */}
      {showFundingPanel && (
        <div style={{
          backgroundColor: '#0e1018',
          borderBottom: '1px solid #1a1f2e',
          padding: '16px 20px',
          flexShrink: 0
        }}>
          <FundingPanelContent
            agentAddress={agentStatus?.agent_wallet}
            currentBalance={agentStatus?.agent_balance_eth || 0}
            onClose={() => setShowFundingPanel(false)}
            onSuccess={(newBalance) => {
              if (agentStatus) {
                setAgentStatus(prev => ({ ...prev, agent_balance_eth: newBalance }));
              }
            }}
          />
        </div>
      )}

      {/* THREE COLUMNS */}
      <div style={{ 
        flex: 1, 
        display: 'flex', 
        overflow: 'hidden' 
      }}>
        {/* LEFT - Watched Wallets (22%) */}
        <div style={{ 
          width: '22%', 
          backgroundColor: '#0e1018',
          borderRight: '1px solid #1a1f2e',
          display: 'flex',
          flexDirection: 'column'
        }}>
          <WatchedWalletsColumn
            wallets={watchedWallets}
            selectedWallet={selectedWallet}
            onSelectWallet={setSelectedWallet}
            onAddWallet={handleAddWallet}
            onRemoveWallet={handleRemoveWallet}
          />
        </div>

        {/* CENTER - Agent Reasoning (44%) */}
        <div style={{ 
          width: '44%', 
          backgroundColor: '#0e1018',
          borderRight: '1px solid #1a1f2e',
          display: 'flex',
          flexDirection: 'column'
        }}>
          <ReasoningColumn
            selectedWallet={selectedWallet}
            nextCycleIn={nextCycleIn}
            isRunning={agentStatus?.running}
          />
        </div>

        {/* RIGHT - Executions (34%) */}
        <div style={{ 
          width: '34%', 
          backgroundColor: '#0e1018',
          display: 'flex',
          flexDirection: 'column'
        }}>
          <ExecutionsColumn executions={executions} />
        </div>
      </div>

      {/* BOTTOM STRIP */}
      <div style={{
        height: '32px',
        backgroundColor: '#0e1018',
        borderTop: '1px solid #1a1f2e',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 20px',
        fontSize: '11px',
        color: '#64748b',
        fontFamily: "'Courier New', monospace",
        flexShrink: 0
      }}>
        <div style={{ display: 'flex', gap: '20px' }}>
          <span>Last Block: {lastBlock || 'N/A'}</span>
          <span>Next Cycle: {formatTime(nextCycleIn)}</span>
          <span style={{ 
            color: '#22c55e',
            backgroundColor: '#22c55e20',
            padding: '2px 6px',
            borderRadius: '2px'
          }}>
            WDK Live
          </span>
        </div>
        <div style={{
          color: streamStatus === 'connected' ? '#22c55e' : '#f59e0b',
          backgroundColor: streamStatus === 'connected' ? '#22c55e20' : '#f59e0b20',
          padding: '2px 6px',
          borderRadius: '2px'
        }}>
          {streamStatus === 'connected' ? 'Connected' : 'Reconnecting...'}
        </div>
      </div>
    </div>
  );
};

// Funding Panel Component
const FundingPanelContent: React.FC<{
  agentAddress?: string;
  currentBalance: number;
  onClose: () => void;
  onSuccess: (newBalance: number) => void;
}> = ({ agentAddress, currentBalance, onClose, onSuccess }) => {
  const [amount, setAmount] = useState('0.05');
  const [status, setStatus] = useState<'idle' | 'funding' | 'success' | 'error'>('idle');
  const [txHash, setTxHash] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
  };

  const fundWithMetaMask = async () => {
    if (!window.ethereum) {
      setErrorMessage('MetaMask not detected');
      setStatus('error');
      return;
    }

    setStatus('funding');
    setErrorMessage(null);

    try {
      console.log('🚀 Starting funding process...');
      
      const ethereum = window.ethereum as any;
      
      const accounts = await ethereum.request({
        method: 'eth_requestAccounts',
      });

      // Switch to Sepolia
      await ethereum.request({
        method: 'wallet_switchEthereumChain',
        params: [{ chainId: '0xaa36a7' }],
      });

      const amountWei = Math.floor(parseFloat(amount) * 1e18);
      const amountHex = `0x${amountWei.toString(16)}`;

      const txParams = {
        from: accounts[0],
        to: agentAddress,
        value: amountHex,
      };

      console.log('Transaction params:', txParams);

      const hash = await ethereum.request({
        method: 'eth_sendTransaction',
        params: [txParams],
      });

      setTxHash(hash);
      setStatus('success');
      console.log('Transaction sent:', hash);

      // Register with API
      await fetch(`${API_BASE}/agent/budget`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          wallet: agentAddress,
          tx_hash: hash
        }),
      });

      // Refresh balance
      const statusRes = await fetch(`${API_BASE}/agent/status`);
      const statusData = await statusRes.json();
      onSuccess(statusData.agent_balance_eth || currentBalance);

    } catch (error: any) {
      console.error('❌ Funding failed:', error);
      setErrorMessage(error.message || 'Funding failed');
      setStatus('error');
    }
  };

  return (
    <div style={{ display: 'flex', gap: '20px', alignItems: 'center' }}>
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: '11px', color: '#64748b', marginBottom: '4px' }}>Agent Address</div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ 
            fontFamily: "'Courier New', monospace", 
            fontSize: '13px', 
            color: '#e2e8f0' 
          }}>
            {agentAddress}
          </span>
          <button
            onClick={() => copyToClipboard(agentAddress || '')}
            style={{
              padding: '2px 6px',
              fontSize: '11px',
              backgroundColor: '#3b82f610',
              color: '#3b82f6',
              border: '1px solid #3b82f640',
              borderRadius: '2px',
              cursor: 'pointer'
            }}
          >
            Copy
          </button>
        </div>
        <div style={{ fontSize: '11px', color: '#64748b', marginTop: '4px' }}>
          Current balance: {currentBalance.toFixed(4)} ETH
        </div>
      </div>

      <div>
        <div style={{ fontSize: '11px', color: '#64748b', marginBottom: '4px' }}>Amount (ETH)</div>
        <input
          type="number"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          step="0.001"
          min="0.001"
          style={{
            backgroundColor: '#080a10',
            border: '1px solid #1a1f2e',
            color: '#e2e8f0',
            fontSize: '13px',
            fontFamily: "'Courier New', monospace",
            padding: '6px 10px',
            borderRadius: '3px',
            width: '100px'
          }}
        />
      </div>

      <div>
        <button
          onClick={fundWithMetaMask}
          disabled={status === 'funding'}
          style={{
            padding: '8px 16px',
            fontSize: '13px',
            backgroundColor: status === 'funding' ? '#1a1f2e' : '#3b82f610',
            color: status === 'funding' ? '#64748b' : '#3b82f6',
            border: `1px solid ${status === 'funding' ? '#1a1f2e' : '#3b82f640'}`,
            borderRadius: '3px',
            cursor: status === 'funding' ? 'not-allowed' : 'pointer',
            whiteSpace: 'nowrap'
          }}
        >
          {status === 'funding' ? 'Funding...' : 'Fund with MetaMask'}
        </button>
      </div>

      <button
        onClick={onClose}
        style={{
          padding: '4px 8px',
          fontSize: '16px',
          backgroundColor: 'transparent',
          color: '#64748b',
          border: 'none',
          cursor: 'pointer'
        }}
      >
        ×
      </button>

      {status === 'success' && txHash && (
        <div style={{ 
          color: '#22c55e', 
          fontSize: '11px',
          position: 'absolute',
          bottom: '4px',
          right: '20px'
        }}>
          <a 
            href={`https://sepolia.etherscan.io/tx/${txHash}`}
            target="_blank"
            rel="noopener noreferrer"
            style={{ color: '#3b82f6', marginLeft: '8px' }}
          >
            View on Etherscan
          </a>
        </div>
      )}

      {status === 'error' && errorMessage && (
        <div style={{ 
          color: '#ef4444', 
          fontSize: '11px',
          position: 'absolute',
          bottom: '4px',
          right: '20px'
        }}>
          {errorMessage}
        </div>
      )}
    </div>
  );
};

// Watched Wallets Column
const WatchedWalletsColumn: React.FC<{
  wallets: any[];
  selectedWallet: string | null;
  onSelectWallet: (address: string) => void;
  onAddWallet: (address: string, label?: string) => void;
  onRemoveWallet: (address: string) => void;
}> = ({ wallets, selectedWallet, onSelectWallet, onAddWallet, onRemoveWallet }) => {
  const [newAddress, setNewAddress] = useState('');
  const [newLabel, setNewLabel] = useState('');
  const [addError, setAddError] = useState<string | null>(null);

  const formatAddress = (address: string) => `${address.slice(0, 6)}...${address.slice(-4)}`;
  const isValidAddress = (address: string) => /^0x[a-fA-F0-9]{40}$/.test(address);

  const handleAdd = () => {
    setAddError(null);
    if (!isValidAddress(newAddress)) {
      setAddError('Invalid address format');
      return;
    }
    onAddWallet(newAddress.toLowerCase(), newLabel || undefined);
    setNewAddress('');
    setNewLabel('');
  };

  const getSignalColor = (signal?: string) => {
    switch (signal) {
      case 'MONITOR': return '#f59e0b';
      case 'ALERT': return '#3b82f6';
      case 'INTERVENE': return '#ef4444';
      default: return '#64748b';
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{
        padding: '12px 16px',
        borderBottom: '1px solid #1a1f2e',
        fontSize: '11px',
        textTransform: 'uppercase',
        color: '#64748b',
        fontWeight: '600',
        letterSpacing: '0.5px'
      }}>
        Watched Wallets
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '8px' }}>
        {wallets.length === 0 ? (
          <div style={{ 
            textAlign: 'center', 
            color: '#64748b', 
            fontSize: '12px',
            marginTop: '20px'
          }}>
            No wallets in queue. Add one below.
          </div>
        ) : (
          wallets.map((wallet) => (
            <div
              key={wallet.address}
              onClick={() => onSelectWallet(wallet.address)}
              style={{
                padding: '10px',
                marginBottom: '6px',
                backgroundColor: selectedWallet === wallet.address ? '#3b82f610' : 'transparent',
                border: selectedWallet === wallet.address ? '1px solid #3b82f640' : '1px solid #1a1f2e',
                borderRadius: '4px',
                cursor: 'pointer'
              }}
            >
              <div style={{ 
                display: 'flex', 
                justifyContent: 'space-between', 
                alignItems: 'center',
                marginBottom: '6px'
              }}>
                <span style={{ 
                  fontFamily: "'Courier New', monospace", 
                  fontSize: '12px', 
                  color: '#e2e8f0' 
                }}>
                  {formatAddress(wallet.address)}
                </span>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onRemoveWallet(wallet.address);
                  }}
                  style={{
                    padding: '2px 6px',
                    fontSize: '10px',
                    backgroundColor: '#ef444410',
                    color: '#ef4444',
                    border: '1px solid #ef444440',
                    borderRadius: '2px',
                    cursor: 'pointer'
                  }}
                >
                  Remove
                </button>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                {wallet.last_signal && (
                  <span style={{
                    fontSize: '10px',
                    padding: '2px 6px',
                    borderRadius: '2px',
                    backgroundColor: `${getSignalColor(wallet.last_signal)}20`,
                    color: getSignalColor(wallet.last_signal),
                    border: `1px solid ${getSignalColor(wallet.last_signal)}40`
                  }}>
                    {wallet.last_signal}
                  </span>
                )}
                
                {wallet.risk_score !== undefined && (
                  <span style={{ 
                    fontSize: '10px', 
                    color: '#64748b',
                    fontFamily: "'Courier New', monospace"
                  }}>
                    Risk: {wallet.risk_score.toFixed(1)}
                  </span>
                )}
              </div>
            </div>
          ))
        )}
      </div>

      <div style={{
        padding: '12px',
        borderTop: '1px solid #1a1f2e',
        backgroundColor: '#080a10'
      }}>
        <input
          type="text"
          placeholder="Wallet address (0x...)"
          value={newAddress}
          onChange={(e) => setNewAddress(e.target.value)}
          style={{
            width: '100%',
            backgroundColor: '#0e1018',
            border: '1px solid #1a1f2e',
            color: '#e2e8f0',
            fontSize: '12px',
            fontFamily: "'Courier New', monospace",
            padding: '8px',
            borderRadius: '3px',
            marginBottom: '8px'
          }}
        />
        
        <input
          type="text"
          placeholder="Label (optional)"
          value={newLabel}
          onChange={(e) => setNewLabel(e.target.value)}
          style={{
            width: '100%',
            backgroundColor: '#0e1018',
            border: '1px solid #1a1f2e',
            color: '#e2e8f0',
            fontSize: '12px',
            padding: '8px',
            borderRadius: '3px',
            marginBottom: '8px'
          }}
        />

        {addError && (
          <div style={{ color: '#ef4444', fontSize: '10px', marginBottom: '8px' }}>
            {addError}
          </div>
        )}

        <button
          onClick={handleAdd}
          disabled={!newAddress.trim()}
          style={{
            width: '100%',
            padding: '8px',
            fontSize: '12px',
            backgroundColor: !newAddress.trim() ? '#1a1f2e' : '#3b82f610',
            color: !newAddress.trim() ? '#64748b' : '#3b82f6',
            border: `1px solid ${!newAddress.trim() ? '#1a1f2e' : '#3b82f640'}`,
            borderRadius: '3px',
            cursor: !newAddress.trim() ? 'not-allowed' : 'pointer'
          }}
        >
          Add Wallet
        </button>
      </div>
    </div>
  );
};

// Reasoning Column
const ReasoningColumn: React.FC<{
  selectedWallet: string | null;
  nextCycleIn: number;
  isRunning: boolean;
}> = ({ selectedWallet, nextCycleIn, isRunning }) => {
  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  // Mock data for demonstration
  const mockScores = {
    activity: 75,
    risk: 45,
    defi_engagement: 60,
    diversity: 30,
    exploration: 85
  };

  const ScoreBar = ({ label, score, color }: { label: string; score: number; color: string }) => (
    <div style={{ marginBottom: '12px' }}>
      <div style={{ 
        display: 'flex', 
        justifyContent: 'space-between', 
        marginBottom: '4px',
        fontSize: '11px'
      }}>
        <span style={{ color: '#64748b' }}>{label}</span>
        <span style={{ 
          color: '#e2e8f0',
          fontFamily: "'Courier New', monospace"
        }}>
          {score}
        </span>
      </div>
      <div style={{
        height: '6px',
        backgroundColor: '#080a10',
        border: '1px solid #1a1f2e',
        borderRadius: '2px'
      }}>
        <div style={{
          height: '100%',
          width: `${score}%`,
          backgroundColor: color,
          borderRadius: '2px',
          transition: 'width 0.5s ease-out'
        }} />
      </div>
    </div>
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{
        padding: '12px 16px',
        borderBottom: '1px solid #1a1f2e',
        fontSize: '11px',
        textTransform: 'uppercase',
        color: '#64748b',
        fontWeight: '600',
        letterSpacing: '0.5px'
      }}>
        Agent Reasoning
      </div>

      <div style={{ flex: 1, padding: '16px', overflowY: 'auto' }}>
        {!isRunning ? (
          <div style={{ 
            height: '100%', 
            display: 'flex', 
            alignItems: 'center', 
            justifyContent: 'center' 
          }}>
            <div style={{ textAlign: 'center', color: '#64748b', fontSize: '14px' }}>
              Agent stopped. Start the agent to begin monitoring.
            </div>
          </div>
        ) : selectedWallet ? (
          <div>
            <div style={{ marginBottom: '16px' }}>
              <div style={{ fontSize: '11px', color: '#64748b', marginBottom: '4px' }}>
                Analyzing:
              </div>
              <div style={{ 
                fontFamily: "'Courier New', monospace", 
                fontSize: '14px', 
                color: '#e2e8f0' 
              }}>
                {selectedWallet}
              </div>
            </div>

            <div style={{ marginBottom: '20px' }}>
              <ScoreBar label="Activity" score={mockScores.activity} color="#3b82f6" />
              <ScoreBar label="Risk" score={mockScores.risk} color="#ef4444" />
              <ScoreBar label="DeFi Engagement" score={mockScores.defi_engagement} color="#3b82f6" />
              <ScoreBar label="Diversity" score={mockScores.diversity} color="#3b82f6" />
              <ScoreBar label="Exploration" score={mockScores.exploration} color="#3b82f6" />
            </div>

            <div style={{ textAlign: 'center', marginBottom: '20px' }}>
              <div style={{ 
                fontSize: '32px', 
                fontWeight: '600',
                fontFamily: "'Courier New', monospace",
                color: '#e2e8f0',
                marginBottom: '12px'
              }}>
                0.71
              </div>
              
              <div style={{
                display: 'inline-block',
                padding: '6px 12px',
                fontSize: '12px',
                fontWeight: '600',
                backgroundColor: '#3b82f620',
                color: '#3b82f6',
                border: '1px solid #3b82f640',
                borderRadius: '4px'
              }}>
                ALERT
              </div>
            </div>

            <div style={{
              padding: '12px',
              backgroundColor: '#080a10',
              border: '1px solid #1a1f2e',
              borderRadius: '4px',
              fontSize: '12px',
              color: '#e2e8f0',
              lineHeight: '1.4'
            }}>
              Wallet shows moderate risk patterns with high DeFi engagement but limited diversity. Recent activity suggests automated behavior warranting monitoring.
            </div>
          </div>
        ) : (
          <div style={{ 
            height: '100%', 
            display: 'flex', 
            alignItems: 'center', 
            justifyContent: 'center' 
          }}>
            <div style={{ textAlign: 'center' }}>
              <div style={{ color: '#64748b', fontSize: '14px', marginBottom: '16px' }}>
                Select a wallet to view analysis
              </div>
              {nextCycleIn > 0 && (
                <div>
                  <div style={{ fontSize: '11px', color: '#64748b', marginBottom: '4px' }}>
                    Next cycle in:
                  </div>
                  <div style={{ 
                    fontSize: '18px', 
                    fontFamily: "'Courier New', monospace",
                    fontWeight: '600',
                    color: '#e2e8f0'
                  }}>
                    {formatTime(nextCycleIn)}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

// Executions Column
const ExecutionsColumn: React.FC<{ executions: any[] }> = ({ executions }) => {
  const formatAddress = (address: string) => `${address.slice(0, 6)}...${address.slice(-4)}`;
  const formatTxHash = (hash: string) => `${hash.slice(0, 8)}...${hash.slice(-6)}`;
  const getRelativeTime = (timestamp: string) => {
    const now = new Date();
    const then = new Date(timestamp);
    const diffMs = now.getTime() - then.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    
    if (diffMins < 1) return 'just now';
    if (diffMins < 60) return `${diffMins} min ago`;
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours}h ago`;
    return `${Math.floor(diffHours / 24)}d ago`;
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'confirmed': return '#22c55e';
      case 'failed': return '#ef4444';
      case 'simulated': return '#64748b';
      default: return '#64748b';
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

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{
        padding: '12px 16px',
        borderBottom: '1px solid #1a1f2e',
        fontSize: '11px',
        textTransform: 'uppercase',
        color: '#64748b',
        fontWeight: '600',
        letterSpacing: '0.5px'
      }}>
        Executions
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '8px' }}>
        {executions.length === 0 ? (
          <div style={{ 
            textAlign: 'center', 
            color: '#64748b', 
            fontSize: '12px',
            marginTop: '20px'
          }}>
            No executions yet
          </div>
        ) : (
          executions.map((execution, index) => (
            <div
              key={execution.id}
              style={{
                padding: '12px',
                marginBottom: '6px',
                backgroundColor: index === 0 ? '#22c55e10' : 'transparent',
                border: '1px solid #1a1f2e',
                borderRadius: '4px'
              }}
            >
              <div style={{ 
                display: 'flex', 
                justifyContent: 'space-between', 
                alignItems: 'center',
                marginBottom: '8px'
              }}>
                <span style={{ 
                  fontSize: '10px',
                  color: '#64748b',
                  fontFamily: "'Courier New', monospace"
                }}>
                  {getRelativeTime(execution.timestamp)}
                </span>
                
                <span style={{
                  fontSize: '10px',
                  padding: '2px 6px',
                  borderRadius: '2px',
                  backgroundColor: `${getStatusColor(execution.status)}20`,
                  color: getStatusColor(execution.status),
                  border: `1px solid ${getStatusColor(execution.status)}40`
                }}>
                  {execution.status}
                </span>
              </div>

              <div style={{ marginBottom: '8px' }}>
                <div style={{ 
                  fontFamily: "'Courier New', monospace", 
                  fontSize: '12px',
                  color: '#e2e8f0',
                  marginBottom: '4px'
                }}>
                  {formatAddress(execution.wallet)}
                </div>
                
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span style={{
                    fontSize: '10px',
                    padding: '2px 6px',
                    borderRadius: '2px',
                    backgroundColor: `${getDecisionColor(execution.decision)}20`,
                    color: getDecisionColor(execution.decision),
                    border: `1px solid ${getDecisionColor(execution.decision)}40`
                  }}>
                    {execution.decision}
                  </span>
                  
                  <span style={{ 
                    fontSize: '11px', 
                    color: '#e2e8f0' 
                  }}>
                    {execution.action}
                  </span>
                </div>
              </div>

              {execution.tx_hash && (
                <a
                  href={`https://sepolia.etherscan.io/tx/${execution.tx_hash}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{ 
                    color: '#3b82f6', 
                    fontSize: '10px',
                    fontFamily: "'Courier New', monospace",
                    textDecoration: 'underline'
                  }}
                >
                  {formatTxHash(execution.tx_hash)}
                </a>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
};

export default Index;
