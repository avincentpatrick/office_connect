import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { mfaConfirm, mfaEnroll } from "../api/auth";
import { ApiError } from "../api/http";
import { Button } from "../components/Button/Button";
import { ErrorSummary } from "../components/ErrorSummary/ErrorSummary";
import { FormField } from "../components/FormField/FormField";
import { toast } from "../components/Toast/toast-bus";
import { AdminPage, AdminSection } from "../layouts/AdminPage";
import { ME_QUERY_KEY, useAuth } from "../app/providers/auth-context";

export function MfaSetupPage() {
  const { me } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [code, setCode] = useState("");

  const enroll = useMutation({ mutationFn: mfaEnroll });

  const confirm = useMutation({
    mutationFn: () => mfaConfirm(code),
    onSuccess: async () => {
      toast("Two-factor authentication is set up.", "success");
      await queryClient.invalidateQueries({ queryKey: ME_QUERY_KEY });
      navigate("/", { replace: true });
    },
  });

  const confirmError =
    confirm.error instanceof ApiError
      ? "Check the 6-digit code from your authenticator and try again."
      : undefined;

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    confirm.mutate();
  };

  return (
    <AdminPage title="Set up two-factor authentication">
      {me?.mfa_setup_required ? (
        <p className="text-base text-text">
          Your role requires two-factor authentication before continuing.
        </p>
      ) : null}
      <AdminSection
        title="1. Add the secret to your authenticator"
        description="Generate a secret, then add it to an authenticator app (manual entry — QR code arrives later)."
      >
        {enroll.data ? (
          <dl className="flex flex-col gap-2">
            <div>
              <dt className="text-sm font-medium text-text-muted">Secret</dt>
              <dd>
                <code className="text-base break-all text-text">{enroll.data.secret}</code>
              </dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-text-muted">Or the full otpauth URI</dt>
              <dd>
                <code className="text-sm break-all text-text-muted">{enroll.data.otpauth_uri}</code>
              </dd>
            </div>
          </dl>
        ) : (
          <Button onClick={() => enroll.mutate()} loading={enroll.isPending}>
            Generate secret
          </Button>
        )}
      </AdminSection>
      <AdminSection title="2. Confirm with a code">
        <form onSubmit={onSubmit} className="flex max-w-md flex-col gap-4">
          {confirmError ? (
            <ErrorSummary
              key={confirm.failureCount}
              errors={[{ message: confirmError, fieldId: "code" }]}
            />
          ) : null}
          <FormField
            id="code"
            label="6-digit code"
            inputMode="numeric"
            autoComplete="one-time-code"
            value={code}
            onChange={(event) => setCode(event.target.value)}
            required
            disabled={!enroll.data}
            error={confirmError}
          />
          <Button type="submit" loading={confirm.isPending} disabled={!enroll.data}>
            Confirm
          </Button>
        </form>
      </AdminSection>
    </AdminPage>
  );
}
