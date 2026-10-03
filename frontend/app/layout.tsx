import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "VoxClone — Voice Studio",
  description: "Voice cloning powered by VoxCPM.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
