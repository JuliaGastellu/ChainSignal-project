import React, { useState, useEffect } from 'react';

interface ReasoningColumnProps {
  selectedWallet: string | null;
  nextCycleIn: number;
  isRunning: boolean;
}

interface ScoreBarProps {
  label: string;
  score: number;
  color: string;
  delay: number;
}

const ScoreBar: React.FC<ScoreBarProps> = ({ label, score, color, delay }) => {
  const [visible, setVisible] = useState(false);
  const [width, setWidth] = useState(0);

  useEffect(() => {
    const timer = setTimeout(() => {
      setVisible(true);
      setTimeout(() => setWidth(score), 100);
    }, delay);
    return () => clearTimeout(timer);
  }, [score, delay]);

  return (
    <div className="mb-3">
      <div className="flex justify-between items-center mb-1">
        <span style={{ color: '#64748b', fontSize: '12px' }}>{label}</span>
        <span style={{ 
          color: '#e2e8f0', 
          fontSize: '12px', 
          fontFamily: 'monospace' 
        }}>
          {score.toFixed(0)}
        </span>
      </div>
      <div 
        className="h-2 border"
        style={{ 
          backgroundColor: '#080a10', 
          borderColor: '#1a1f2e' 
        }}
      >
        <div
          className="h-full transition-all duration-500 ease-out"
          style={{
            width: visible ? `${width}%` : '0%',
            backgroundColor: color,
            transitionDelay: visible ? '100ms' : '0ms'
          }}
        />
      </div>
    </div>
  );
};

export const ReasoningColumn: React.FC<ReasoningColumnProps> = ({
  selectedWallet,
  nextCycleIn,
  isRunning
}) => {
  const [currentAnalysis, setCurrentAnalysis] = useState<any>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);

  // Mock data for demonstration
  const mockScores = {
    activity: 75,
    risk: 45,
    defi_engagement: 60,
    diversity: 30,
    exploration: 85
  };

  const mockThreatScore = 0.71;
  const mockDecision = 'ALERT';
  const mockReasoning = 'Wallet shows moderate risk patterns with high DeFi engagement but limited diversity. Recent activity suggests automated behavior warranting monitoring.';

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
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
          Agent Reasoning
        </h2>
      </div>

      {/* Content */}
      <div className="flex-1 p-4">
        {!isRunning ? (
          <div className="h-full flex items-center justify-center">
            <div className="text-center">
              <div style={{ color: '#64748b', fontSize: '14px' }}>
                Agent stopped. Start the agent to begin monitoring.
              </div>
            </div>
          </div>
        ) : isAnalyzing ? (
          <div>
            <div className="mb-4">
              <div style={{ color: '#64748b', fontSize: '12px', marginBottom: '2px' }}>
                Analyzing:
              </div>
              <div style={{ 
                color: '#e2e8f0', 
                fontSize: '14px', 
                fontFamily: 'monospace' 
              }}>
                {selectedWallet || 'No wallet selected'}
              </div>
            </div>

            <div className="space-y-2">
              <ScoreBar label="Activity" score={mockScores.activity} color="#3b82f6" delay={0} />
              <ScoreBar label="Risk" score={mockScores.risk} color="#ef4444" delay={150} />
              <ScoreBar label="DeFi Engagement" score={mockScores.defi_engagement} color="#3b82f6" delay={300} />
              <ScoreBar label="Diversity" score={mockScores.diversity} color="#3b82f6" delay={450} />
              <ScoreBar label="Exploration" score={mockScores.exploration} color="#3b82f6" delay={600} />
            </div>
          </div>
        ) : selectedWallet ? (
          <div>
            <div className="mb-4">
              <div style={{ color: '#64748b', fontSize: '12px', marginBottom: '2px' }}>
                Last analyzed:
              </div>
              <div style={{ 
                color: '#e2e8f0', 
                fontSize: '14px', 
                fontFamily: 'monospace' 
              }}>
                {selectedWallet}
              </div>
            </div>

            <div className="space-y-2">
              <ScoreBar label="Activity" score={mockScores.activity} color="#3b82f6" delay={0} />
              <ScoreBar label="Risk" score={mockScores.risk} color="#ef4444" delay={150} />
              <ScoreBar label="DeFi Engagement" score={mockScores.defi_engagement} color="#3b82f6" delay={300} />
              <ScoreBar label="Diversity" score={mockScores.diversity} color="#3b82f6" delay={450} />
              <ScoreBar label="Exploration" score={mockScores.exploration} color="#3b82f6" delay={600} />
            </div>

            <div className="mt-6 text-center">
              <div style={{ 
                color: '#e2e8f0', 
                fontSize: '32px', 
                fontWeight: '600',
                fontFamily: 'monospace' 
              }}>
                {mockThreatScore.toFixed(2)}
              </div>
              
              <div 
                className="inline-block px-3 py-1.5 text-sm font-medium border mt-3"
                style={{
                  backgroundColor: getDecisionBg(mockDecision),
                  color: getDecisionColor(mockDecision),
                  borderColor: `${getDecisionColor(mockDecision)}40`,
                  animation: 'flash 0.5s ease-out'
                }}
              >
                {mockDecision}
              </div>
            </div>

            <div className="mt-4 p-3 border" style={{ 
              backgroundColor: '#080a10', 
              borderColor: '#1a1f2e',
              borderRadius: '4px'
            }}>
              <div style={{ 
                color: '#e2e8f0', 
                fontSize: '12px',
                lineHeight: '1.4'
              }}>
                {mockReasoning}
              </div>
            </div>

            {(mockDecision === 'ALERT' || mockDecision === 'INTERVENE') && (
              <div className="mt-3 p-3 border" style={{ 
                backgroundColor: '#ef444410', 
                borderColor: '#ef444440',
                borderRadius: '4px'
              }}>
                <div style={{ 
                  color: '#ef4444', 
                  fontSize: '12px',
                  fontWeight: '500'
                }}>
                  Intended Action:
                </div>
                <div style={{ 
                  color: '#e2e8f0', 
                  fontSize: '12px',
                  marginTop: '4px'
                }}>
                  Transfer 0.001 ETH to safety contract
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="h-full flex items-center justify-center">
            <div className="text-center">
              <div style={{ color: '#64748b', fontSize: '14px' }}>
                Select a wallet to view analysis
              </div>
              {nextCycleIn > 0 && (
                <div className="mt-4">
                  <div style={{ color: '#64748b', fontSize: '12px', marginBottom: '2px' }}>
                    Next cycle in:
                  </div>
                  <div style={{ 
                    color: '#e2e8f0', 
                    fontSize: '18px', 
                    fontFamily: 'monospace',
                    fontWeight: '600' 
                  }}>
                    {formatTime(nextCycleIn)}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      <style jsx>{`
        @keyframes flash {
          0% { opacity: 0.5; transform: scale(0.95); }
          50% { opacity: 1; transform: scale(1.05); }
          100% { opacity: 1; transform: scale(1); }
        }
      `}</style>
    </div>
  );
};
