"use client";

import { useRouter } from "next/navigation";

import { LoginForm } from "./login-form";

export function LoginPanel({ locale }: { locale: string }) {
  const router = useRouter();

  return (
    <LoginForm
      onSuccess={() => {
        router.replace(`/${locale}/sources`);
        router.refresh();
      }}
    />
  );
}
