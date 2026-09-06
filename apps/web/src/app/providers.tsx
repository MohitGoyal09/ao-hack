"use client";

import { CopilotKit } from "@copilotkit/react-core/v2";

export function Providers({ children }: { children: React.ReactNode }) {
  // Inspector and dev-only chrome stay off in every build, including the demo.
  return <CopilotKit runtimeUrl="/api/copilotkit" agent="default" enableInspector={false} showDevConsole={false}>{children}</CopilotKit>;
}
