import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import Index from "./pages/Index.tsx";
import NotFound from "./pages/NotFound.tsx";

const queryClient = new QueryClient();

class ErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { hasError: boolean; errorMessage: string }
> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { hasError: false, errorMessage: "" };
  }

  static getDerivedStateFromError(error: unknown) {
    return {
      hasError: true,
      errorMessage: error instanceof Error ? error.message : "Unknown UI error",
    };
  }

  componentDidCatch(error: unknown) {
    console.error("[UI] Uncaught render error:", error);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-background text-foreground flex items-center justify-center p-6">
          <div className="w-full max-w-lg bg-card border border-border rounded-xl p-6">
            <div className="text-sm font-semibold">UI crashed</div>
            <div className="mt-2 text-sm text-muted-foreground">
              {this.state.errorMessage}
            </div>
            <div className="mt-4 flex gap-2">
              <button
                onClick={() => window.location.reload()}
                className="text-xs px-3 py-2 rounded bg-primary/10 text-primary border border-primary/20 hover:bg-primary/15"
              >
                Reload
              </button>
            </div>
            <div className="mt-4 text-[11px] text-muted-foreground">
              Open DevTools Console to see the exact exception and stack trace.
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <Toaster />
      <Sonner />
      <ErrorBoundary>
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<Index />} />
            {/* ADD ALL CUSTOM ROUTES ABOVE THE CATCH-ALL "*" ROUTE */}
            <Route path="*" element={<NotFound />} />
          </Routes>
        </BrowserRouter>
      </ErrorBoundary>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;
