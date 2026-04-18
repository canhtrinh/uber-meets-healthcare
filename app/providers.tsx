"use client";

import { PrimVoicesProvider } from "primvoices-react";
import type { ReactNode } from "react";

const AGENT_ID = process.env.NEXT_PUBLIC_PRIMVOICES_AGENT_ID ?? "";
const ENVIRONMENT = process.env.NEXT_PUBLIC_PRIMVOICES_ENVIRONMENT ?? "production";

export function Providers({ children }: { children: ReactNode }) {
  return (
    <PrimVoicesProvider
      config={{
        agentId: AGENT_ID,
        environment: ENVIRONMENT,
        strategy: "cascade",
        origin: "web",
        logLevel: "INFO",
        // Route the POST /v1/agents/.../call through a Next.js rewrite.
        // api.primvoices.com doesn't send Access-Control-Allow-Origin,
        // so same-origin via /api/pv avoids CORS. The rewrite lives in next.config.ts.
        apiUrl: "/api/pv",
      }}
    >
      {children}
    </PrimVoicesProvider>
  );
}
