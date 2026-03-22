import React, { useState } from 'react';

interface WalletData {
  address: string;
  label?: string;
  last_signal?: string;
  risk_score?: number;
  times_flagged?: number;
}

interface WatchQueueColumnProps {
  wallets: WalletData[];
  selectedWallet: string | null;
  onSelectWallet: (address: string) => void;
  onAddWallet: (address: string, label?: string) => void;
  onRemoveWallet: (address: string) => void;
}

export const WatchQueueColumn: React.FC<WatchQueueColumnProps> = ({
  wallets,
  selectedWallet,
  onSelectWallet,
  onAddWallet,
  onRemoveWallet
}) => {
  const [newAddress, setNewAddress] = useState('');
  const [newLabel, setNewLabel] = useState('');
  const [addError, setAddError] = useState<string | null>(null);

  const formatAddress = (address: string) => {
    return `${address.slice(0, 6)}...${address.slice(-4)}`;
  };

  const isValidAddress = (address: string) => {
    return /^0x[a-fA-F0-9]{40}$/.test(address);
  };

  const handleAddWallet = () => {
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

  const getSignalBg = (signal?: string) => {
    switch (signal) {
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
          Watched Wallets
        </h2>
      </div>

      {/* Wallet List */}
      <div className="flex-1 overflow-y-auto">
        {wallets.length === 0 ? (
          <div className="p-4 text-center" style={{ color: '#64748b', fontSize: '12px' }}>
            No wallets in queue. Add one below.
          </div>
        ) : (
          <div className="p-2">
            {wallets.map((wallet) => (
              <div
                key={wallet.address}
                className={`p-3 mb-2 border cursor-pointer transition-colors ${
                  selectedWallet === wallet.address ? 'ring-1' : ''
                }`}
                style={{
                  borderColor: selectedWallet === wallet.address ? '#3b82f6' : '#1a1f2e',
                  backgroundColor: selectedWallet === wallet.address ? '#3b82f610' : 'transparent',
                  ringColor: selectedWallet === wallet.address ? '#3b82f6' : 'transparent'
                }}
                onClick={() => onSelectWallet(wallet.address)}
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span style={{ 
                      fontFamily: 'monospace', 
                      fontSize: '13px', 
                      color: '#e2e8f0' 
                    }}>
                      {formatAddress(wallet.address)}
                    </span>
                    {wallet.label && (
                      <span style={{ 
                        fontSize: '11px', 
                        color: '#64748b',
                        fontStyle: 'italic'
                      }}>
                        {wallet.label}
                      </span>
                    )}
                  </div>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onRemoveWallet(wallet.address);
                    }}
                    className="px-2 py-1 text-xs border"
                    style={{
                      backgroundColor: '#ef444410',
                      color: '#ef4444',
                      borderColor: '#ef444440',
                      cursor: 'pointer'
                    }}
                  >
                    Remove
                  </button>
                </div>

                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    {wallet.last_signal && (
                      <span 
                        className="px-2 py-0.5 text-xs font-medium"
                        style={{
                          backgroundColor: getSignalBg(wallet.last_signal),
                          color: getSignalColor(wallet.last_signal),
                          border: `1px solid ${getSignalColor(wallet.last_signal)}40`
                        }}
                      >
                        {wallet.last_signal}
                      </span>
                    )}
                    
                    {wallet.risk_score !== undefined && (
                      <span style={{ 
                        fontSize: '12px', 
                        color: '#64748b',
                        fontFamily: 'monospace'
                      }}>
                        Risk: {wallet.risk_score.toFixed(2)}
                      </span>
                    )}
                  </div>

                  {wallet.times_flagged !== undefined && wallet.times_flagged > 0 && (
                    <span style={{ 
                      fontSize: '11px', 
                      color: '#f59e0b' 
                    }}>
                      {wallet.times_flagged}× flagged
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Add Wallet Section */}
      <div className="p-4 border-t" style={{ 
        borderColor: '#1a1f2e',
        backgroundColor: '#080a10'
      }}>
        <div className="space-y-3">
          <input
            type="text"
            placeholder="Wallet address (0x...)"
            value={newAddress}
            onChange={(e) => setNewAddress(e.target.value)}
            className="w-full px-3 py-2 border"
            style={{
              backgroundColor: '#0e1018',
              borderColor: '#1a1f2e',
              color: '#e2e8f0',
              fontSize: '12px',
              fontFamily: 'monospace'
            }}
          />
          
          <input
            type="text"
            placeholder="Label (optional)"
            value={newLabel}
            onChange={(e) => setNewLabel(e.target.value)}
            className="w-full px-3 py-2 border"
            style={{
              backgroundColor: '#0e1018',
              borderColor: '#1a1f2e',
              color: '#e2e8f0',
              fontSize: '12px'
            }}
          />

          {addError && (
            <div style={{ color: '#ef4444', fontSize: '11px' }}>
              {addError}
            </div>
          )}

          <button
            onClick={handleAddWallet}
            disabled={!newAddress.trim()}
            className="w-full px-3 py-2 text-sm font-medium border"
            style={{
              backgroundColor: !newAddress.trim() ? '#1a1f2e' : '#3b82f610',
              color: !newAddress.trim() ? '#64748b' : '#3b82f6',
              borderColor: !newAddress.trim() ? '#1a1f2e' : '#3b82f640',
              cursor: !newAddress.trim() ? 'not-allowed' : 'pointer'
            }}
          >
            Add Wallet
          </button>
        </div>
      </div>
    </div>
  );
};
