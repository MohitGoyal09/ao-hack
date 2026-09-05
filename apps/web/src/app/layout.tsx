import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Covenant Certificate | Treasury control room",
  description: "Evidence-first loan covenant workflow",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
