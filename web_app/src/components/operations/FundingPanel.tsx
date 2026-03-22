import React, { useState } from 'react';
import { API_BASE } from '@/hooks/useAgentSSE';

interface FundingPanelProps {
  agentAddress?: string;
  currentBalance: number;
  onClose: () => void;
  onFundingSuccess: (newBalance: number) => void;
}

export const FundingPanel: React.FC<FundingPanelProps> = ({
  agentAddress,
  currentBalance,
  onClose,
  onFundingSuccess
}) => {
  const [amount, setAmount] = useState('0.05');
  const [fundingStatus, setFundingStatus] = useState<'idle' | 'funding' | 'success' | 'error'>('idle');
  const [txHash, setTxHash] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const formatAddress = (address: string) => {
    return `${address.slice(0, 6)}...${address.slice(-4)}`;
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
  };

  const switchToSepolia = async () => {
    if (!window.ethereum) throw new Error('MetaMask not found');

    const sepoliaChainId = '0xaa36a7';
    
    try {
      await window.ethereum.request({
        method: 'wallet_switchEthereumChain',
        params: [{ chainId: sepoliaChainId }],
      });
    } catch (switchError: any) {
      // Chain not found, add it
      if (switchError.code === 4902) {
        try {
          await window.ethereum.request({
            method: 'wallet_addEthereumChain',
            params: [{
              chainId: sepoliaChainId,
              chainName: 'Sepolia Testnet',
              nativeCurrency: {
                name: 'ETH',
                symbol: 'ETH',
                decimals: 18,
              },
              rpcUrls: ['https://rpc.sepolia.org'],
              blockExplorerUrls: ['https://sepolia.etherscan.io'],
            }],
          });
        } catch (addError) {
          throw new Error('Failed to add Sepolia network');
        }
      } else {
        throw new Error('Failed to switch to Sepolia');
      }
    }
  };

  const fundWithMetaMask = async () => {
    if (!window.ethereum) {
      setErrorMessage('MetaMask not detected. Please install MetaMask.');
      setFundingStatus('error');
      return;
    }

    if (!agentAddress) {
      setErrorMessage('Agent address not available.');
      setFundingStatus('error');
      return;
    }

    setFundingStatus('funding');
    setErrorMessage(null);

    try {
      // Request accounts
      const accounts = await window.ethereum.request({
        method: 'eth_requestAccounts',
      });

      if (!accounts || accounts.length === 0) {
        throw new Error('No accounts available');
      }

      // Switch to Sepolia
      await switchToSepolia();

      // Send transaction
      const txHash = await window.ethereum.request({
        method: 'eth_sendTransaction',
        params: [{
          from: accounts[0],
          to: agentAddress,
          value: `0x${(parseFloat(amount) * 1e18).toString(16)}`,
        }],
      });

      setTxHash(txHash);
      setFundingStatus('success');

      // Verify and register the funding
      const response = await fetch(`${API_BASE}/agent/budget`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          wallet: agentAddress,
          tx_hash: txHash
        }),
      });

      if (response.ok) {
        // Refresh balance
        const statusRes = await fetch(`${API_BASE}/agent/status`);
        const statusData = await statusRes.json();
        onFundingSuccess(statusData.agent_balance_eth || currentBalance);
      }

    } catch (error: any) {
      console.error('Funding failed:', error);
      setErrorMessage(error.message || 'Funding failed');
      setFundingStatus('error');
    }
  };

  // Close panel when clicking outside
  React.useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as HTMLElement;
      if (!target.closest('.funding-panel-content')) {
        onClose();
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [onClose]);

  if (!window.ethereum) {
    return (
      <div className="border-b" style={{ 
        backgroundColor: '#0e1018', 
        borderColor: '#1a1f2e',
        padding: '16px'
      }}>
        <div className="funding-panel-content">
          <div className="flex items-center justify-between mb-3">
            <h3 style={{ color: '#e2e8f0', fontSize: '14px', fontWeight: '600' }}>Fund Agent</h3>
            <button 
              onClick={onClose}
              style={{ color: '#64748b', fontSize: '18px', background: 'none', border: 'none', cursor: 'pointer' }}
            >
              ×
            </button>
          </div>
          
          <div style={{ color: '#64748b', fontSize: '12px' }}>
            MetaMask not detected. Please fund the agent address directly:
          </div>
          
          {agentAddress && (
            <div className="mt-3 p-3 border" style={{ 
              backgroundColor: '#080a10', 
              borderColor: '#1a1f2e',
              borderRadius: '4px'
            }}>
              <div style={{ color: '#64748b', fontSize: '12px', marginBottom: '8px' }}>Agent Address:</div>
              <div className="flex items-center gap-2">
                <span style={{ 
                  fontFamily: 'monospace', 
                  fontSize: '14px', 
                  color: '#e2e8f0' 
                }}>
                  {agentAddress}
                </span>
                <button
                  onClick={() => copyToClipboard(agentAddress)}
                  className="px-2 py-1 text-xs border"
                  style={{
                    backgroundColor: '#3b82f610',
                    color: '#3b82f6',
                    borderColor: '#3b82f640',
                    cursor: 'pointer'
                  }}
                >
                  Copy
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="border-b" style={{ 
      backgroundColor: '#0e1018', 
      borderColor: '#1a1f2e',
      padding: '16px'
    }}>
      <div className="funding-panel-content">
        <div className="flex items-center justify-between mb-3">
          <h3 style={{ color: '#e2e8f0', fontSize: '14px', fontWeight: '600' }}>Fund Agent</h3>
          <button 
            onClick={onClose}
            style={{ color: '#64748b', fontSize: '18px', background: 'none', border: 'none', cursor: 'pointer' }}
          >
            ×
          </button>
        </div>

        {agentAddress && (
          <div className="mb-4">
            <div style={{ color: '#64748b', fontSize: '12px', marginBottom: '4px' }}>Agent Address:</div>
            <div className="flex items-center gap-2">
              <span style={{ 
                fontFamily: 'monospace', 
                fontSize: '14px', 
                color: '#e2e8f0' 
              }}>
                {formatAddress(agentAddress)}
              </span>
              <button
                onClick={() => copyToClipboard(agentAddress)}
                className="px-2 py-1 text-xs border"
                style={{
                  backgroundColor: '#3b82f610',
                  color: '#3b82f6',
                  borderColor: '#3b82f640',
                  cursor: 'pointer'
                }}
              >
                Copy
              </button>
            </div>
            <div style={{ color: '#64748b', fontSize: '12px', marginTop: '4px' }}>
              Current balance: {currentBalance.toFixed(4)} ETH
            </div>
          </div>
        )}

        <div className="flex items-center gap-3 mb-4">
          <div style={{ color: '#64748b', fontSize: '12px' }}>Amount (ETH):</div>
          <input
            type="number"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            step="0.001"
            min="0.001"
            className="px-3 py-2 border"
            style={{
              backgroundColor: '#080a10',
              borderColor: '#1a1f2e',
              color: '#e2e8f0',
              fontSize: '14px',
              fontFamily: 'monospace',
              width: '120px'
            }}
          />
        </div>

        <button
          onClick={fundWithMetaMask}
          disabled={fundingStatus === 'funding'}
          className="px-4 py-2 text-sm font-medium border"
          style={{
            backgroundColor: fundingStatus === 'funding' ? '#1a1f2e' : '#3b82f610',
            color: fundingStatus === 'funding' ? '#64748b' : '#3b82f6',
            borderColor: fundingStatus === 'funding' ? '#1a1f2e' : '#3b82f640',
            cursor: fundingStatus === 'funding' ? 'not-allowed' : 'pointer'
          }}
        >
          {fundingStatus === 'funding' ? 'Funding...' : 'Fund with MetaMask'}
        </button>

        {fundingStatus === 'success' && txHash && (
          <div className="mt-3" style={{ color: '#22c55e', fontSize: '12px' }}>
            Transaction sent! 
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

        {fundingStatus === 'error' && errorMessage && (
          <div className="mt-3" style={{ color: '#ef4444', fontSize: '12px' }}>
            {errorMessage}
          </div>
        )}
      </div>
    </div>
  );
};
