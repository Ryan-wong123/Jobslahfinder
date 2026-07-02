import { Suspense } from "react";
import { TwoFactorVerifyPanel } from "@/components/TwoFactorVerifyPanel";

export default function TwoFactorVerifyPage() {
  return (
    <Suspense>
      <TwoFactorVerifyPanel />
    </Suspense>
  );
}
