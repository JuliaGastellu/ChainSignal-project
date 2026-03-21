import { Wallet } from "lucide-react";
import { AgentBudgetPanel } from "@/components/AgentBudgetPanel";

export function AgentTreasuryCard({ wallet }: { wallet: string }) {
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
        <Wallet className="h-4 w-4" /> Agent Treasury
      </div>
      <AgentBudgetPanel wallet={wallet} />
    </div>
  );
}

