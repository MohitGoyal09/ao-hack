import type { Metadata } from "next";
import "./globals.css";
import "@copilotkit/react-core/v2/styles.css";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "Covenant Certificate | Treasury control room",
  description: "Evidence-first loan covenant workflow",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body><Providers>{children}</Providers></body></html>;
}
