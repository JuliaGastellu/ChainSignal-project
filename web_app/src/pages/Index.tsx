import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useOperationsSSE } from '@/hooks/useOperationsSSE';
import { API_BASE } from '@/hooks/useAgentSSE';

// --- TYPES ---

interface WalletData {
  address: string;
  label?: string;
  last_signal?: 'MONITOR' | 'ALERT' | 'INTERVENE' | 'WAITING';
  risk_score?: number;
  times_flagged?: number;
}

interface ScoreData {
  label: string;
  score: number;
  color: string;
}

interface ExecutionData {
  id: string;
  timestamp: string; // ISO
  wallet: string;
  decision: string;
  action: string;
  status: 'pending' | 'confirmed' | 'failed' | 'simulated';
  tx_hash?: string;
  error?: string;
}

interface ActivityEntry {
  timestamp: number;
  type: string;
  description: string;
  color: string;
}

// --- MAIN COMPONENT ---

const Index: React.FC = () => {
  // State
  const [agentStatus, setAgentStatus] = useState<any>(null);
  const [showFunding, setShowFunding] = useState(false);
  const [fundingAmount, setFundingAmount] = useState('0.05');
  const [fundingStatus, setFundingStatus] = useState<string | null>(null);
  const [watchedWallets, setWatchedWallets] = useState<WalletData[]>([]);
  const [newWalletAddress, setNewWalletAddress] = useState('');
  const [newWalletLabel, setNewWalletLabel] = useState('');
  const [addWalletStatus, setAddWalletStatus] = useState<string | null>(null);
  const [executions, setExecutions] = useState<ExecutionData[]>([]);
  const [activityLog, setActivityLog] = useState<ActivityEntry[]>([]);
  const [selectedWalletAddress, setSelectedWalletAddress] = useState<string | null>(null);
  const [analyzingWallet, setAnalyzingWallet] = useState<string | null>(null);
  const [analysisScores, setAnalysisScores] = useState<any>(null);
  const [showScores, setShowScores] = useState(false);
  const [reasoningText, setReasoningText] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [threatScore, setThreatScore] = useState<number | null>(null);
  const [decision, setDecision] = useState<string | null>(null);
  const [pendingAction, setPendingAction] = useState<string | null>(null);
  const [lastConfirmedTx, setLastConfirmedTx] = useState<string | null>(null);
  const [currentCycle, setCurrentCycle] = useState(0);
  const [nextCycleIn, setNextCycleIn] = useState(0);
  const [blockNumber, setBlockNumber] = useState<number | string>('...');
  
  // SSE
  const { events, connected } = useOperationsSSE();

  // Resync on reconnect
  useEffect(() => {
    if (connected) {
      const resync = async () => {
        try {
          const [watchRes, historyRes] = await Promise.all([
            fetch(`${API_BASE}/agent/watch`),
            fetch(`${API_BASE}/agent/history`)
          ]);
          const watch = await watchRes.json();
          const history = await historyRes.json();
          setWatchedWallets(watch.wallets || []);
          setExecutions(history.executions || []);
        } catch (err) {
          console.error("Resync failed", err);
        }
      };
      resync();
    }
  }, [connected]);

  // Handlers
  const getRelativeTime = (timestamp: string) => {
    const diff = Date.now() - new Date(timestamp).getTime();
    const minutes = Math.floor(diff / 60000);
    if (minutes < 1) return 'just now';
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    return `${Math.floor(hours / 24)}d ago`;
  };

  const logEntry = useCallback((type: string, desc: string, color: string) => {
    setActivityLog(prev => [{
      timestamp: Date.now(),
      type,
      description: desc,
      color
    }, ...prev].slice(0, 60));
  }, []);

  // Event Processing
  useEffect(() => {
    if (events.length === 0) return;
    const latestEvent = events[events.length - 1];

    switch (latestEvent.type) {
      case 'cycle_start':
        setCurrentCycle(prev => prev + 1);
        setNextCycleIn(0);
        logEntry('cycle_start', `Cycle ${currentCycle + 1} started`, '#374151');
        break;
      case 'wallet_analyzing':
        setAnalyzingWallet(latestEvent.wallet);
        setAnalysisScores(null);
        setShowScores(false);
        setReasoningText('');
        setThreatScore(null);
        setDecision(null);
        setPendingAction(null);
        logEntry('wallet_analyzing', `Analyzing wallet ${latestEvent.wallet.slice(0, 8)}...`, '#3b82f6');
        // Start staggered bar fill sequence (visually start at 0)
        setTimeout(() => setShowScores(true), 150);
        break;
      case 'reasoning_token':
        setReasoningText(prev => prev + latestEvent.token);
        setIsStreaming(true);
        break;
      case 'reasoning_complete':
        setIsStreaming(false);
        setAnalysisScores({
          activity: latestEvent.scores?.activity || 0,
          risk: latestEvent.scores?.risk || 0,
          defi: latestEvent.scores?.defi_engagement || latestEvent.scores?.defi || 0,
          diversity: latestEvent.scores?.diversity || 0,
          exploration: latestEvent.scores?.exploration || 0
        });
        setThreatScore(latestEvent.threat_score);
        setDecision(latestEvent.decision);
        if (latestEvent.decision === 'ALERT' || latestEvent.decision === 'INTERVENE') {
          setPendingAction(latestEvent.intended_action || 'Executing strategy...');
        }
        logEntry('reasoning_complete', 'AI reasoning generated', '#8b5cf6');
        logEntry(`${latestEvent.decision}_decision`, `${latestEvent.decision} decision for ${latestEvent.wallet.slice(0, 8)}...`,
          latestEvent.decision === 'MONITOR' ? '#f59e0b' :
          latestEvent.decision === 'ALERT' ? '#3b82f6' :
          latestEvent.decision === 'INTERVENE' ? '#ef4444' : '#374151');
        break;
      case 'execution_start':
        const newEx: ExecutionData = {
          id: latestEvent.id || Date.now().toString(),
          timestamp: new Date().toISOString(),
          wallet: latestEvent.wallet,
          decision: latestEvent.decision,
          action: latestEvent.action,
          status: 'pending'
        };
        setExecutions(prev => [newEx, ...prev]);
        logEntry('execution_start', `Action pending: ${latestEvent.action}`, '#3b82f6');
        break;
      case 'execution_confirmed':
        setExecutions(prev => prev.map(ex => 
          (ex.wallet === latestEvent.wallet && ex.status === 'pending') ? { ...ex, status: 'confirmed', tx_hash: latestEvent.tx_hash } : ex
        ));
        setLastConfirmedTx(latestEvent.tx_hash);
        logEntry('execution_confirmed', `Confirmed: ${latestEvent.tx_hash.slice(0, 8)}...`, '#22c55e');
        setTimeout(() => setLastConfirmedTx(null), 400);
        break;
      case 'execution_failed':
        setExecutions(prev => prev.map(ex => 
          (ex.wallet === latestEvent.wallet && ex.status === 'pending') ? { ...ex, status: 'failed', error: latestEvent.error } : ex
        ));
        logEntry('execution_failed', `Failed: ${latestEvent.error}`, '#ef4444');
        break;
      case 'execution_simulated':
        setExecutions(prev => prev.map(ex =>
          (ex.wallet === latestEvent.wallet && ex.status === 'pending') ? { ...ex, status: 'simulated' } : ex
        ));
        logEntry('execution_simulated', `Simulated: ${latestEvent.action}`, '#374151');
        break;
      case 'balance_update':
        setAgentStatus((prev: any) => ({ ...prev, balance: latestEvent.balance_eth }));
        logEntry('balance_update', `Balance: ${latestEvent.balance_eth} ETH`, '#22c55e');
        break;
      case 'agent_idle':
        setNextCycleIn(latestEvent.next_cycle_in);
        // Keep analyzingWallet and other states but they will be styled as idle
        logEntry('agent_idle', `Agent idle. Next cycle in ${latestEvent.next_cycle_in}s`, '#374151');
        break;
      case 'new_block':
        setBlockNumber(latestEvent.block_number);
        break;
    }
  }, [events, currentCycle, logEntry]);

  // Countdown Timer
  useEffect(() => {
    if (nextCycleIn <= 0) return;
    const timer = setInterval(() => {
      setNextCycleIn(prev => Math.max(0, prev - 1));
    }, 1000);
    return () => clearInterval(timer);
  }, [nextCycleIn]);

  const addWallet = useCallback(async () => {
    if (!newWalletAddress.match(/^0x[a-fA-F0-9]{40}$/)) {
      setAddWalletStatus("Invalid address");
      setTimeout(() => setAddWalletStatus(null), 2000);
      return;
    }
    try {
      const res = await fetch(`${API_BASE}/agent/watch`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ address: newWalletAddress, label: newWalletLabel })
      });
      if (res.ok) {
        const data = await res.json();
        setWatchedWallets(data.wallets || []);
        setNewWalletAddress('');
        setNewWalletLabel('');
        setAddWalletStatus("Added");
        setTimeout(() => setAddWalletStatus(null), 2000);
      }
    } catch (err) {
      console.error("Failed to add wallet", err);
    }
  }, [newWalletAddress, newWalletLabel]);

  const removeWallet = useCallback(async (address: string) => {
    try {
      await fetch(`${API_BASE}/agent/watch/${address}`, { method: 'DELETE' });
      setWatchedWallets(prev => prev.filter(w => w.address !== address));
    } catch (err) {
      console.error("Failed to remove wallet", err);
    }
  }, []);

  const fundWithMetaMask = useCallback(async () => {
    if (!window.ethereum) {
      setFundingStatus("Error: MetaMask not detected. Send ETH manually.");
      return;
    }

    try {
      setFundingStatus("Connecting...");
      const accounts = await (window.ethereum as any).request({ method: "eth_requestAccounts" });

      setFundingStatus("Switching network...");
      try {
        await (window.ethereum as any).request({
          method: "wallet_switchEthereumChain",
          params: [{ chainId: "0xaa36a7" }],
        });
      } catch (err: any) {
        if (err.code === 4902) {
          await (window.ethereum as any).request({
            method: "wallet_addEthereumChain",
            params: [{
              chainId: "0xaa36a7",
              chainName: "Sepolia",
              nativeCurrency: { name: "ETH", symbol: "ETH", decimals: 18 },
              rpcUrls: ["https://rpc.sepolia.org"],
              blockExplorerUrls: ["https://sepolia.etherscan.io"]
            }]
          });
        } else {
          throw err;
        }
      }

      const from = accounts[0];
      const amountEth = parseFloat(fundingAmount);
      if (isNaN(amountEth)) throw new Error("Invalid amount");

      const hexWei = "0x" + BigInt(Math.floor(amountEth * 1e18)).toString(16);

      setFundingStatus("Awaiting confirmation...");
      const txHash = await (window.ethereum as any).request({
        method: "eth_sendTransaction",
        params: [{
          from,
          to: agentStatus?.address,
          value: hexWei
        }]
      });

      setFundingStatus(`Success: ${txHash.slice(0, 10)}...`);
      
      // Poll for balance increase
      const startBalance = agentStatus?.balance;
      const poll = setInterval(async () => {
        const res = await fetch(`${API_BASE}/health`);
        const data = await res.json();
        const currentBalance = data.agent_budget?.total_balance_eth || 0;
        if (currentBalance > startBalance) {
          setAgentStatus((prev: any) => ({ ...prev, balance: currentBalance }));
          clearInterval(poll);
          setFundingStatus("Balance updated");
        }
      }, 3000);
      setTimeout(() => clearInterval(poll), 60000);

    } catch (err: any) {
      setFundingStatus(`Error: ${err.code === 4001 ? "Transaction rejected" : err.message}`);
    }
  }, [fundingAmount, agentStatus?.address, agentStatus?.balance]);

  // Derived
  const totalEthMoved = useMemo(() => {
    return executions
      .filter(ex => ex.status === 'confirmed')
      .reduce((sum, ex) => {
        const match = ex.action.match(/(\d+\.?\d*)\s*ETH/);
        return sum + (match ? parseFloat(match[1]) : 0);
      }, 0);
  }, [executions]);

  // Initial Load
  useEffect(() => {
    const fetchData = async () => {
      try {
        const [healthRes, watchRes, historyRes] = await Promise.all([
          fetch(`${API_BASE}/health`),
          fetch(`${API_BASE}/agent/watch`),
          fetch(`${API_BASE}/agent/history`)
        ]);

        const health = await healthRes.json();
        const watch = await watchRes.json();
        const history = await historyRes.json();

        setAgentStatus({
          running: health.agent_loop === 'active',
          address: health.agent_budget?.agent_wallet || health.agent_wallet || '',
          balance: health.agent_budget?.total_balance_eth || 0,
        });
        setWatchedWallets(watch.wallets || []);
        setExecutions(history.executions || []);
      } catch (err) {
        console.error("Initial fetch failed", err);
      }
    };
    fetchData();
  }, []);

  // Layout Render
  return (
    <div style={{
      display: 'grid',
      gridTemplateRows: '48px 1fr 130px 28px',
      gridTemplateColumns: '22% 44% 34%',
      height: '100vh',
      width: '100vw',
      backgroundColor: '#080a10',
      color: '#e2e8f0',
      overflow: 'hidden'
    }}>
      {/* HEADER */}
      <div style={{
        gridColumn: '1 / -1',
        borderBottom: '1px solid #1a2332',
        height: '48px',
        display: 'flex',
        alignItems: 'center',
        padding: '0 12px',
        backgroundColor: '#0d1117',
        justifyContent: 'space-between',
        position: 'relative',
        zIndex: 110
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          {/* Logo */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <div style={{ width: '16px', height: '16px', backgroundColor: '#06b6d4' }}></div>
            <span className="font-mono" style={{ fontSize: '13px', color: '#e2e8f0' }}>ChainSignal</span>
          </div>
          {/* Agent Address */}
          <span
            className="font-mono"
            title={agentStatus?.address}
            style={{ fontSize: '11px', color: '#64748b', cursor: 'help' }}
          >
            {agentStatus?.address ? `${agentStatus.address.slice(0, 8)}...${agentStatus.address.slice(-6)}` : '0x0000...0000'}
          </span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '24px' }}>
          {/* Balance */}
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '4px' }}>
            <span className="font-mono" style={{
              fontSize: '15px',
              color: (agentStatus?.balance > 0.01) ? '#22c55e' : (agentStatus?.balance < 0.003 ? '#ef4444' : '#e2e8f0')
            }}>
              {(agentStatus?.balance || 0).toFixed(4)}
            </span>
            <span style={{ fontSize: '10px', color: '#64748b' }}>ETH</span>
          </div>
          {/* Loop Status */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <div className={agentStatus?.running ? "animate-pulse-dot" : ""} style={{
              width: '6px',
              height: '6px',
              borderRadius: '50%',
              backgroundColor: agentStatus?.running ? '#22c55e' : '#64748b'
            }}></div>
            <span style={{ fontSize: '11px', color: agentStatus?.running ? '#22c55e' : '#64748b' }}>
              {agentStatus?.running ? 'ACTIVE' : 'STOPPED'}
            </span>
          </div>
        </div>

        <div style={{ display: 'flex', gap: '6px' }}>
          <button
            onClick={() => setShowFunding(!showFunding)}
            style={{ border: '1px solid #1a2332', background: '#0e1421', color: '#e2e8f0', fontSize: '11px', padding: '5px 12px', cursor: 'pointer', whiteSpace: 'nowrap' }}
          >
            Fund
          </button>
          <button
            disabled={agentStatus?.running}
            onClick={async () => {
              await fetch(`${API_BASE}/agent/start`, { method: 'POST' });
              setAgentStatus((prev: any) => ({ ...prev, running: true }));
            }}
            style={{
              border: '1px solid #22c55e40',
              background: '#22c55e15',
              color: '#22c55e',
              fontSize: '11px',
              padding: '5px 12px',
              cursor: agentStatus?.running ? 'not-allowed' : 'pointer',
              whiteSpace: 'nowrap',
              opacity: agentStatus?.running ? 0.35 : 1
            }}
          >
            Start
          </button>
          <button
            disabled={!agentStatus?.running}
            onClick={async () => {
              await fetch(`${API_BASE}/agent/stop`, { method: 'POST' });
              setAgentStatus((prev: any) => ({ ...prev, running: false }));
            }}
            style={{
              border: '1px solid #ef444440',
              background: '#ef444415',
              color: '#ef4444',
              fontSize: '11px',
              padding: '5px 12px',
              cursor: !agentStatus?.running ? 'not-allowed' : 'pointer',
              whiteSpace: 'nowrap',
              opacity: !agentStatus?.running ? 0.35 : 1
            }}
          >
            Stop
          </button>
        </div>

        {/* FUNDING DROPDOWN */}
        {showFunding && (
          <>
          <div
            onClick={() => setShowFunding(false)}
            style={{ position: 'fixed', top: '48px', left: 0, right: 0, bottom: 0, zIndex: 90 }}
          />
          <div
            onKeyDown={(e) => e.key === 'Escape' && setShowFunding(false)}
            style={{
              position: 'absolute',
              top: '48px',
              left: 0,
              width: '100%',
              zIndex: 100,
              backgroundColor: '#0d1117',
              borderBottom: '1px solid #1a2332',
              padding: '20px 24px',
              display: 'flex',
              flexDirection: 'column',
              gap: '16px'
            }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                <span style={{ fontSize: '10px', color: '#64748b', textTransform: 'uppercase' }}>Agent Wallet Address</span>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  <span className="font-mono" style={{ fontSize: '13px', color: '#e2e8f0' }}>{agentStatus?.address}</span>
                  <button
                    onClick={() => {
                      navigator.clipboard.writeText(agentStatus?.address);
                      setFundingStatus("Address copied");
                      setTimeout(() => setFundingStatus(null), 2000);
                    }}
                    style={{ border: '1px solid #1a2332', background: '#0e1421', color: '#64748b', fontSize: '11px', padding: '2px 8px', cursor: 'pointer' }}
                  >
                    Copy
                  </button>
                </div>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', alignItems: 'flex-end' }}>
                <span style={{ fontSize: '10px', color: '#64748b', textTransform: 'uppercase' }}>Current Balance</span>
                <span className="font-mono" style={{ fontSize: '15px', color: '#22c55e' }}>{(agentStatus?.balance || 0).toFixed(4)} ETH</span>
              </div>
            </div>

            <div style={{ display: 'flex', alignItems: 'flex-end', gap: '12px' }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', flex: 1 }}>
                <span style={{ fontSize: '10px', color: '#64748b', textTransform: 'uppercase' }}>Amount to Fund (ETH)</span>
                <input
                  type="text"
                  value={fundingAmount}
                  onChange={(e) => setFundingAmount(e.target.value)}
                  className="font-mono"
                  style={{ backgroundColor: '#080a10', border: '1px solid #1a2332', color: '#e2e8f0', padding: '8px 12px', fontSize: '13px', width: '100%' }}
                />
              </div>
              <button
                onClick={fundWithMetaMask}
                style={{ border: '1px solid #3b82f640', background: '#3b82f615', color: '#3b82f6', fontSize: '11px', padding: '10px 24px', cursor: 'pointer', height: '36px' }}
              >
                Connect & Fund via MetaMask
              </button>
            </div>

            {fundingStatus && (
              <div style={{ fontSize: '11px', color: fundingStatus.includes('Error') ? '#ef4444' : '#3b82f6', fontFamily: 'monospace' }}>
                {fundingStatus}
              </div>
            )}
          </div>
          </>
        )}
      </div>

      {/* LEFT COLUMN - WATCH QUEUE */}
      <div style={{ 
        gridRow: '2',
        gridColumn: '1',
        borderRight: '1px solid #1a2332',
        overflow: 'hidden',
        display: 'flex', 
        flexDirection: 'column',
        backgroundColor: '#080a10'
      }}>
        <div style={{ padding: '10px 12px', borderBottom: '1px solid #1a2332', fontSize: '10px', color: '#374151', fontWeight: 'bold' }}>WATCHED WALLETS</div>
        <div style={{ flex: 1, overflowY: 'auto' }}>
          {watchedWallets.length === 0 ? (
            <div style={{ padding: '20px', textAlign: 'center', fontSize: '11px', color: '#374151' }}>No wallets. Add one below.</div>
          ) : (
            watchedWallets.map(wallet => (
              <div
                key={wallet.address}
                onClick={() => setSelectedWalletAddress(wallet.address)}
                style={{
                  padding: '8px 12px',
                  borderBottom: '1px solid #0d1117',
                  cursor: 'pointer',
                  backgroundColor: selectedWalletAddress === wallet.address ? '#0e1421' : 'transparent',
                  borderLeft: selectedWalletAddress === wallet.address ? '2px solid #3b82f6' : 'none',
                  position: 'relative'
                }}
                onMouseEnter={(e) => { (e.currentTarget.querySelector('.remove-btn') as HTMLElement).style.opacity = '1'; }}
                onMouseLeave={(e) => { (e.currentTarget.querySelector('.remove-btn') as HTMLElement).style.opacity = '0'; }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span className="font-mono" style={{ fontSize: '11px', color: '#e2e8f0' }}>
                    {wallet.address.slice(0, 8)}...{wallet.address.slice(-6)}
                  </span>
                  {wallet.last_signal && (
                    <span style={{
                      fontSize: '9px',
                      padding: '1px 5px',
                      border: '1px solid currentColor',
                      color: wallet.last_signal === 'MONITOR' ? '#f59e0b' :
                             wallet.last_signal === 'ALERT' ? '#3b82f6' :
                             wallet.last_signal === 'INTERVENE' ? '#ef4444' : '#64748b',
                      backgroundColor: 'rgba(currentColor, 0.2)'
                    }}>
                      {wallet.last_signal}
                    </span>
                  )}
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '2px' }}>
                  <span style={{ fontSize: '10px', color: '#64748b' }}>{wallet.label || ''}</span>
                  {wallet.times_flagged !== undefined && (
                    <span style={{ fontSize: '10px', color: '#374151' }}>flagged {wallet.times_flagged}×</span>
                  )}
                </div>
                <button
                  className="remove-btn"
                  onClick={(e) => { e.stopPropagation(); removeWallet(wallet.address); }}
                  style={{
                    position: 'absolute',
                    right: '12px',
                    top: '50%',
                    transform: 'translateY(-50%)',
                    background: 'none',
                    border: 'none',
                    color: '#374151',
                    cursor: 'pointer',
                    fontSize: '11px',
                    opacity: 0,
                    transition: 'opacity 0.2s'
                  }}
                >
                  ×
                </button>
              </div>
            ))
          )}
        </div>
        <div style={{ borderTop: '1px solid #1a2332', padding: '12px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <input
            type="text"
            placeholder="0x..."
            value={newWalletAddress}
            onChange={(e) => setNewWalletAddress(e.target.value)}
            className="font-mono"
            style={{ width: '100%', backgroundColor: '#080a10', border: '1px solid #1a2332', color: '#e2e8f0', padding: '5px 8px', fontSize: '11px' }}
          />
          <input
            type="text"
            placeholder="Label (optional)"
            value={newWalletLabel}
            onChange={(e) => setNewWalletLabel(e.target.value)}
            style={{ width: '100%', backgroundColor: '#080a10', border: '1px solid #1a2332', color: '#e2e8f0', padding: '5px 8px', fontSize: '11px' }}
          />
          <button
            onClick={addWallet}
            style={{ width: '100%', border: '1px solid #1a2332', background: '#0d1117', color: addWalletStatus === 'Added' ? '#22c55e' : '#64748b', padding: '5px', fontSize: '11px', cursor: 'pointer' }}
          >
            {addWalletStatus || 'Add Wallet'}
          </button>
        </div>
      </div>

      {/* CENTER COLUMN - AGENT REASONING */}
      <div style={{ gridRow: '2', gridColumn: '2', borderRight: '1px solid #1a2332', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
        <div style={{ padding: '10px 12px', borderBottom: '1px solid #1a2332', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontSize: '10px', color: '#374151', fontWeight: 'bold' }}>AGENT REASONING</span>
          <span className="font-mono" style={{ fontSize: '10px', color: '#374151' }}>CYCLE {currentCycle}</span>
        </div>
        <div style={{ flex: 1, overflowY: 'auto', padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: '24px' }}>
          {agentStatus?.running && (analyzingWallet || analysisScores) ? (
            <div style={{ opacity: nextCycleIn > 0 ? 0.5 : 1, display: 'flex', flexDirection: 'column', gap: '24px' }}>
              {/* WALLET BEING ANALYZED */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <span className="font-mono" style={{ fontSize: '12px', color: '#3b82f6' }}>{analyzingWallet || 'Analysis cached'}</span>
                <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <span style={{ fontSize: '10px', color: '#64748b' }}>Analyzing</span>
                  <span className="animate-blink" style={{ width: '6px', height: '10px', backgroundColor: '#64748b' }}></span>
                </div>
              </div>

              {/* SCORE BARS */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                {[
                  { label: 'Activity', key: 'activity', color: '#06b6d4' },
                  { label: 'Risk', key: 'risk', color: '#ef4444' },
                  { label: 'DeFi', key: 'defi', color: '#8b5cf6' },
                  { label: 'Diversity', key: 'diversity', color: '#3b82f6' },
                  { label: 'Exploration', key: 'exploration', color: '#f59e0b' },
                ].map((item, index) => {
                  const score = analysisScores ? (analysisScores[item.key] || 0) : 0;
                  return (
                    <div key={item.key} style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                      <span style={{ fontSize: '10px', color: '#64748b', width: '100px', textTransform: 'uppercase' }}>{item.label}</span>
                      <div style={{ flex: 1, height: '4px', backgroundColor: '#1a2332', position: 'relative' }}>
                        <div style={{
                          position: 'absolute',
                          left: 0,
                          top: 0,
                          height: '100%',
                          backgroundColor: item.color,
                          width: showScores ? `${score}%` : '0%',
                          transition: `width 300ms ease-out ${index * 150}ms`
                        }}></div>
                      </div>
                      <span className="font-mono" style={{ fontSize: '11px', color: '#e2e8f0', width: '30px', textAlign: 'right' }}>
                        {showScores ? Math.round(score) : 0}
                      </span>
                    </div>
                  );
                })}
              </div>

              {/* AI REASONING TEXT */}
              {(reasoningText || isStreaming) && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  <span style={{ fontSize: '9px', color: '#8b5cf6', textTransform: 'uppercase' }}>AI Analysis</span>
                  <div style={{ 
                    borderLeft: '3px solid #8b5cf6',
                    paddingLeft: '12px',
                    fontSize: '12px',
                    color: '#e2e8f0',
                    lineHeight: '1.6',
                    whiteSpace: 'pre-wrap',
                    position: 'relative'
                  }}>
                    {reasoningText}
                    {isStreaming && (
                      <span className="animate-blink" style={{ display: 'inline-block', width: '6px', height: '14px', backgroundColor: '#e2e8f0', marginLeft: '2px', verticalAlign: 'middle' }}></span>
                    )}
                  </div>
                </div>
              )}

              {/* THREAT SCORE & DECISION */}
              {threatScore !== null && (
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: '12px' }}>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    <span style={{ fontSize: '10px', color: '#374151', textTransform: 'uppercase' }}>Threat</span>
                    <span className="font-mono" style={{
                      fontSize: '28px',
                      color: threatScore < 0.35 ? '#22c55e' : threatScore < 0.65 ? '#f59e0b' : '#ef4444'
                    }}>
                      {threatScore.toFixed(2)}
                    </span>
                  </div>
                  {decision && (
                    <div
                      className={
                        decision === 'MONITOR' ? 'animate-flash-amber' :
                        decision === 'ALERT' ? 'animate-flash-blue' :
                        decision === 'INTERVENE' ? 'animate-flash-red' : ''
                      }
                      style={{
                        fontSize: '12px',
                        fontWeight: 'bold',
                        padding: '4px 14px',
                        border: '1px solid currentColor',
                        backgroundColor: 'rgba(currentColor, 0.15)',
                        color: decision === 'MONITOR' ? '#f59e0b' :
                               decision === 'ALERT' ? '#3b82f6' :
                               decision === 'INTERVENE' ? '#ef4444' : '#374151'
                      }}>
                      {decision}
                    </div>
                  )}
                </div>
              )}

              {/* PENDING ACTION */}
              {pendingAction && (
                <div style={{ 
                  border: '1px solid #1a2332',
                  backgroundColor: '#080a10',
                  padding: '8px 10px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '4px'
                }}>
                  <span style={{ fontSize: '9px', color: '#f59e0b', textTransform: 'uppercase' }}>Pending Action</span>
                  <span className="font-mono" style={{ fontSize: '11px', color: '#e2e8f0' }}>{pendingAction}</span>
                </div>
              )}

              {/* IDLE TIMER OVERLAY */}
              {nextCycleIn > 0 && (
                <div style={{ display: 'flex', justifyContent: 'center', marginTop: '20px' }}>
                   <span className="font-mono" style={{ fontSize: '13px', color: '#374151' }}>Next cycle in {nextCycleIn}s</span>
                </div>
              )}
            </div>
          ) : agentStatus?.running ? (
            <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
               <span className="font-mono" style={{ fontSize: '13px', color: '#374151' }}>Next cycle in {nextCycleIn}s</span>
            </div>
          ) : (
            <div style={{ height: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '8px' }}>
              <span style={{ fontSize: '11px', color: '#374151' }}>Agent stopped.</span>
              <span style={{ fontSize: '10px', color: '#374151' }}>Start the agent to begin monitoring.</span>
            </div>
          )}
        </div>
      </div>

      {/* RIGHT COLUMN - EXECUTION FEED */}
      <div style={{ gridRow: '2', gridColumn: '3', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
        <div style={{ padding: '10px 12px', borderBottom: '1px solid #1a2332', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontSize: '10px', color: '#374151', fontWeight: 'bold' }}>EXECUTIONS</span>
          <span className="font-mono" style={{ fontSize: '10px', color: '#64748b' }}>Σ {totalEthMoved.toFixed(4)} ETH</span>
        </div>
        <div style={{ flex: 1, overflowY: 'auto' }}>
          {executions.length === 0 ? (
            <div style={{ padding: '20px', textAlign: 'center', fontSize: '11px', color: '#374151' }}>No executions yet.</div>
          ) : (
            executions.map((ex, index) => (
              <div
                key={ex.id || index}
                className={ex.id === lastConfirmedTx ? "animate-flash-green" : ""}
                style={{ padding: '10px 12px', borderBottom: '1px solid #0d1117' }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                  <span style={{ fontSize: '10px', color: '#64748b' }}>
                    {getRelativeTime(ex.timestamp)}
                  </span>
                  <div style={{
                    fontSize: '9px',
                    padding: '1px 5px',
                    border: '1px solid currentColor',
                    color: ex.decision === 'MONITOR' ? '#f59e0b' :
                           ex.decision === 'ALERT' ? '#3b82f6' :
                           ex.decision === 'INTERVENE' ? '#ef4444' : '#64748b',
                    backgroundColor: 'rgba(currentColor, 0.15)'
                  }}>
                    {ex.decision}
                  </div>
                </div>
                <div className="font-mono" style={{ fontSize: '11px', color: '#64748b', marginBottom: '2px' }}>
                  {ex.wallet.slice(0, 8)}...{ex.wallet.slice(-6)}
                </div>
                <div style={{ fontSize: '11px', color: '#e2e8f0', marginBottom: '4px' }}>
                  {ex.action}
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <div style={{
                    width: '6px',
                    height: '6px',
                    borderRadius: '50%',
                    backgroundColor: ex.status === 'confirmed' ? '#22c55e' :
                                     ex.status === 'failed' ? '#ef4444' :
                                     ex.status === 'simulated' ? '#374151' : '#f59e0b'
                  }}></div>
                  <span style={{ fontSize: '10px', color: '#374151' }}>
                    {ex.status.charAt(0).toUpperCase() + ex.status.slice(1)}
                  </span>
                  {ex.tx_hash && (
                    <a
                      href={`https://sepolia.etherscan.io/tx/${ex.tx_hash}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="font-mono"
                      style={{ fontSize: '10px', color: '#3b82f6', textDecoration: 'none' }}
                    >
                      {ex.tx_hash.slice(0, 8)}...{ex.tx_hash.slice(-6)}
                    </a>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* ACTIVITY LOG */}
      <div style={{ gridRow: '3', gridColumn: '1 / -1', borderTop: '1px solid #1a2332', backgroundColor: '#0d1117', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
        <div style={{ padding: '6px 12px', borderBottom: '1px solid #1a2332', fontSize: '10px', color: '#374151', fontWeight: 'bold', position: 'sticky', top: 0, backgroundColor: '#0d1117', zIndex: 10 }}>ACTIVITY</div>
        <div style={{ flex: 1, overflowY: 'auto', padding: '4px 0' }}>
          {activityLog.map((log, i) => (
            <div key={i} className="font-mono" style={{ padding: '2px 12px', fontSize: '11px', display: 'flex', gap: '8px' }}>
              <span style={{ color: '#374151' }}>{new Date(log.timestamp).toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })}</span>
              <span style={{ color: '#374151' }}>·</span>
              <span style={{ color: log.color, textTransform: 'uppercase', minWidth: '100px' }}>{log.type}</span>
              <span style={{ color: '#e2e8f0' }}>{log.description}</span>
            </div>
          ))}
        </div>
      </div>

      {/* STATUS BAR */}
      <div style={{
        gridRow: '4',
        gridColumn: '1 / -1',
        borderTop: '1px solid #1a2332',
        backgroundColor: '#080a10',
        display: 'flex',
        alignItems: 'center',
        padding: '0 12px',
        fontSize: '10px',
        color: '#374151',
        justifyContent: 'space-between'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <span className="font-mono" style={{ color: '#374151' }}>Block: {blockNumber}</span>
          <span style={{ color: '#374151' }}>·</span>
          <span className="font-mono" style={{ color: '#374151' }}>Next: {nextCycleIn}s</span>
          <span style={{ color: '#374151' }}>·</span>
          <span className="font-mono" style={{ color: '#22c55e' }}>WDK Live</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <div style={{
            width: '6px',
            height: '6px',
            borderRadius: '50%',
            backgroundColor: connected ? '#22c55e' : '#f59e0b'
          }}></div>
          <span className="font-mono">{connected ? 'Connected' : 'Reconnecting...'}</span>
        </div>
      </div>
    </div>
  );
};

export default Index;
