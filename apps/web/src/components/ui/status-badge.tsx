import { cn } from "@/lib/cn";

const TONES: Record<string, string> = {
  approved: "bg-accent/12 text-accent",
  ready: "bg-accent/12 text-accent",
  succeeded: "bg-accent/12 text-accent",
  pending: "bg-foreground/8 text-muted",
  draft: "bg-foreground/8 text-muted",
  queued: "bg-foreground/8 text-muted",
  running: "bg-foreground/8 text-muted",
  scanning: "bg-foreground/8 text-muted",
  stale: "bg-warning/15 text-warning",
  partial: "bg-warning/15 text-warning",
  ignored: "bg-foreground/8 text-muted",
  archived: "bg-foreground/8 text-muted",
  describe_failed: "bg-danger/12 text-danger",
  failed: "bg-danger/12 text-danger",
  error: "bg-danger/12 text-danger",
};

export function StatusBadge({ status, label }: { status: string; label?: string }) {
  return (
    <span
      className={cn(
        "inline-flex rounded-full px-2 py-0.5 text-xs font-medium",
        TONES[status] ?? "bg-foreground/8 text-muted",
      )}
    >
      {label ?? status}
    </span>
  );
}
