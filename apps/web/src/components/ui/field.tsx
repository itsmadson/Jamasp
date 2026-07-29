import { useId } from "react";

import { cn } from "@/lib/cn";

interface TextFieldProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label: string;
  hint?: string;
}

export function TextField({ label, hint, className, ...props }: TextFieldProps) {
  const generated = useId();
  const id = props.id ?? generated;

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-medium text-foreground">
        {label}
      </label>
      <input
        {...props}
        id={id}
        className={cn(
          "rounded-md border border-border bg-surface px-3 py-2 text-sm",
          "outline-none focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/25",
          "disabled:opacity-60",
          className,
        )}
      />
      {hint ? <p className="text-xs text-muted">{hint}</p> : null}
    </div>
  );
}
