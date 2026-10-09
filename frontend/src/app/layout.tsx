import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "DocQuest Voice",
  description: "Assistant pour interroger le DEU TotalEnergies 2025",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="fr">
      <body>{children}</body>
    </html>
  );
}
