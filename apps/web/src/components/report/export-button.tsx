"use client";

import { Printer } from "lucide-react";
import { useTranslations } from "next-intl";

import { Button } from "@/components/ui/button";

/**
 * Exports through the browser's own print-to-PDF.
 *
 * The alternative is rendering the page server-side in a headless browser, which
 * means shipping Chromium in the API image and re-solving Persian text shaping and
 * RTL layout there. The browser already has the fonts installed, already shapes
 * Persian correctly, and already writes PDF. A print stylesheet is the whole
 * implementation.
 */
export function ExportButton() {
  const t = useTranslations("report");

  return (
    <Button
      variant="secondary"
      onClick={() => window.print()}
      className="flex items-center gap-1.5 print:hidden"
    >
      <Printer aria-hidden size={15} />
      {t("exportPdf")}
    </Button>
  );
}
