import { useEffect, useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { login } from "../api/auth";
import { ApiError } from "../api/http";
import { Button } from "../components/Button/Button";
import { Card } from "../components/Card/Card";
import { ErrorSummary, type ErrorSummaryItem } from "../components/ErrorSummary/ErrorSummary";
import { FormField } from "../components/FormField/FormField";
import { AppShell } from "../layouts/AppShell";
import { ME_QUERY_KEY, useAuth } from "../app/providers/auth-context";

export function LoginPage() {
  const { me } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  const from = (location.state as { from?: string } | null)?.from ?? "/";

  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [countdown, setCountdown] = useState<number | null>(null);

  const signIn = useMutation({
    mutationFn: () => login(identifier, password),
    onSuccess: async (response) => {
      if (response.status === "mfa_required") {
        // The mfa_token travels in navigation state only — never storage.
        navigate("/login/mfa", { state: { mfaToken: response.mfa_token, from } });
        return;
      }
      // authenticated / password_change_required / mfa_setup_required:
      // refresh me and let the route guards direct the forced flows.
      await queryClient.invalidateQueries({ queryKey: ME_QUERY_KEY });
      navigate(from, { replace: true });
    },
    onError: (error) => {
      if (error instanceof ApiError && error.code === "too_many_attempts") {
        setCountdown(error.retryAfter ?? 30);
      }
    },
  });

  const apiError = signIn.error instanceof ApiError ? signIn.error : null;

  useEffect(() => {
    if (countdown === null) return;
    const timer = setTimeout(() => {
      setCountdown((seconds) => (seconds !== null && seconds > 1 ? seconds - 1 : null));
    }, 1000);
    return () => clearTimeout(timer);
  }, [countdown]);

  if (me) return <Navigate to="/" replace />;

  let summaryErrors: ErrorSummaryItem[] = [];
  let credentialError: string | undefined;
  if (apiError) {
    if (apiError.code === "invalid_credentials") {
      credentialError = "Check your email and password and try again.";
      summaryErrors = [{ message: credentialError, fieldId: "identifier" }];
    } else if (apiError.code === "too_many_attempts") {
      summaryErrors = [{ message: "Too many sign-in attempts. Wait, then try again." }];
    } else {
      summaryErrors = [{ message: apiError.message }];
    }
  }

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    signIn.mutate();
  };

  return (
    <AppShell minimal>
      <div className="mx-auto max-w-md pt-8">
        <Card title="Sign in">
          <form onSubmit={onSubmit} className="flex flex-col gap-4">
            {summaryErrors.length > 0 ? (
              <ErrorSummary key={signIn.failureCount} errors={summaryErrors} />
            ) : null}
            <FormField
              id="identifier"
              label="Email"
              autoComplete="username"
              value={identifier}
              onChange={(event) => setIdentifier(event.target.value)}
              required
              error={credentialError}
            />
            <FormField
              id="password"
              label="Password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
            {countdown !== null ? (
              <p className="text-sm font-medium text-status-blocked">
                Too many attempts. Try again in {countdown}s.
              </p>
            ) : null}
            <Button type="submit" loading={signIn.isPending} disabled={countdown !== null}>
              Sign in
            </Button>
          </form>
        </Card>
      </div>
    </AppShell>
  );
}
