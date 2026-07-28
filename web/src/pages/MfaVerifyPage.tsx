import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { mfaVerify } from "../api/auth";
import { ApiError } from "../api/http";
import { Button } from "../components/Button/Button";
import { Card } from "../components/Card/Card";
import { ErrorSummary } from "../components/ErrorSummary/ErrorSummary";
import { FormField } from "../components/FormField/FormField";
import { AppShell } from "../layouts/AppShell";
import { ME_QUERY_KEY } from "../app/providers/auth-context";

export function MfaVerifyPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  const state = location.state as { mfaToken?: string; from?: string } | null;

  const [code, setCode] = useState("");

  const verify = useMutation({
    mutationFn: () => mfaVerify(state?.mfaToken ?? "", code),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ME_QUERY_KEY });
      navigate(state?.from ?? "/", { replace: true });
    },
  });

  // Deep-linking here without a token from a fresh login makes no sense.
  if (!state?.mfaToken) return <Navigate to="/login" replace />;

  const apiError = verify.error instanceof ApiError ? verify.error : null;
  const codeError = apiError ? "Check the 6-digit code from your authenticator and try again." : undefined;

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    verify.mutate();
  };

  return (
    <AppShell minimal>
      <div className="mx-auto max-w-md pt-8">
        <Card title="Enter your verification code">
          <form onSubmit={onSubmit} className="flex flex-col gap-4">
            {codeError ? (
              <ErrorSummary
                key={verify.failureCount}
                errors={[{ message: codeError, fieldId: "code" }]}
              />
            ) : null}
            <FormField
              id="code"
              label="6-digit code"
              help="Open your authenticator app and enter the current code."
              inputMode="numeric"
              autoComplete="one-time-code"
              value={code}
              onChange={(event) => setCode(event.target.value)}
              required
              error={codeError}
            />
            <Button type="submit" loading={verify.isPending}>
              Verify
            </Button>
          </form>
        </Card>
      </div>
    </AppShell>
  );
}
