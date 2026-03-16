import { Suspense } from "react";
import type { Metadata } from "next";

import { AppFrame } from "@/components/AppFrame";

import "./globals.css";

export const metadata: Metadata = {
  title: "Pocket Nori",
  description: "Pocket Nori — personal intelligence layer",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>
        <Suspense>
          <AppFrame>{children}</AppFrame>
        </Suspense>
      </body>
    </html>
  );
}
