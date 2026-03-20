import { useState } from "react";
import { motion } from "framer-motion";
import { Search, Loader2 } from "lucide-react";

interface WalletInputProps {
  onSubmit: (wallet: string) => void;
  isLoading: boolean;
}

const ETH_ADDRESS_REGEX = /^0x[a-fA-F0-9]{40}$/;

export function WalletInput({ onSubmit, isLoading }: WalletInputProps) {
  const [value, setValue] = useState("");
  const [validationError, setValidationError] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = value.trim();
    if (!ETH_ADDRESS_REGEX.test(trimmed)) {
      setValidationError("Enter a valid Ethereum address (0x...)");
      return;
    }
    setValidationError("");
    onSubmit(trimmed);
  };

  return (
    <motion.form
      onSubmit={handleSubmit}
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: "easeOut" }}
      className="w-full max-w-2xl mx-auto"
    >
      <div className="relative group">
        <div className="absolute -inset-0.5 bg-gradient-to-r from-primary/20 to-primary/5 rounded-lg blur opacity-0 group-focus-within:opacity-100 transition-opacity duration-500" />
        <div className="relative flex items-center gap-2 bg-card border border-border rounded-lg p-1.5 focus-within:glow-border transition-colors">
          <Search className="ml-3 h-4 w-4 text-muted-foreground flex-shrink-0" />
          <input
            type="text"
            value={value}
            onChange={(e) => {
              setValue(e.target.value);
              if (validationError) setValidationError("");
            }}
            placeholder="0x... Enter wallet address"
            className="flex-1 bg-transparent border-0 outline-none text-foreground placeholder:text-muted-foreground font-mono text-sm py-2.5 px-1"
            disabled={isLoading}
            spellCheck={false}
            autoComplete="off"
          />
          <button
            type="submit"
            disabled={isLoading || !value.trim()}
            className="flex items-center gap-2 bg-primary text-primary-foreground px-5 py-2.5 rounded-md text-sm font-medium transition-all hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {isLoading ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                <span>Processing</span>
              </>
            ) : (
              <span>Analyze</span>
            )}
          </button>
        </div>
      </div>
      {validationError && (
        <motion.p
          initial={{ opacity: 0, y: -4 }}
          animate={{ opacity: 1, y: 0 }}
          className="mt-2 text-sm text-destructive pl-1"
        >
          {validationError}
        </motion.p>
      )}
    </motion.form>
  );
}
