import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { changePassword } from "../api/auth";
import { ApiError } from "../api/http";
import { Button } from "../components/Button/Button";
import { ErrorSummary, type ErrorSummaryItem } from "../components/ErrorSummary/ErrorSummary";
import { FormField } from "../components/FormField/FormField";
import { toast } from "../components/Toast/toast-bus";
import { AdminPage, AdminSection } from "../layouts/AdminPage";
import { ME_QUERY_KEY, useAuth } from "../app/providers/auth-context";

function policyMessages(details: unknown): string[] {
  if (!Array.isArray(details)) return [];
  return details
    .map((detail) => (typeof detail === "object" && detail !== null ? (detail as { msg?: string }).msg : undefined))
    .filter((msg): msg is string => typeof msg === "string");
}

export function PasswordChangePage() {
  const { me } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [mismatch, setMismatch] = useState(false);

  const change = useMutation({
    mutationFn: () => changePassword(currentPassword, newPassword),
    onSuccess: async () => {
      toast("Your password has been changed.", "success");
      // The server rotated the session; refresh me and let the guards route
      // onward (e.g. straight into forced MFA setup for admins).
      await queryClient.invalidateQueries({ queryKey: ME_QUERY_KEY });
      navigate("/", { replace: true });
    },
  });

  const apiError = change.error instanceof ApiError ? change.error : null;

  let summaryErrors: ErrorSummaryItem[] = [];
  let newPasswordError: string | undefined;
  if (mismatch) {
    newPasswordError = "Enter the same new password in both fields.";
    summaryErrors = [{ message: newPasswordError, fieldId: "new-password" }];
  } else if (apiError) {
    if (apiError.code === "password_policy") {
      const messages = policyMessages(apiError.details);
      newPasswordError = messages.join(" ") || apiError.message;
      summaryErrors = (messages.length > 0 ? messages : [apiError.message]).map((message) => ({
        message,
        fieldId: "new-password",
      }));
    } else {
      summaryErrors = [{ message: apiError.message }];
    }
  }

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (newPassword !== confirmPassword) {
      setMismatch(true);
      return;
    }
    setMismatch(false);
    change.mutate();
  };

  return (
    <AdminPage title="Change your password">
      {me?.must_change_password ? (
        <p className="text-base text-text">
          You need to change your password before continuing.
        </p>
      ) : null}
      <AdminSection title="New password">
        <form onSubmit={onSubmit} className="flex max-w-md flex-col gap-4">
          {summaryErrors.length > 0 ? (
            <ErrorSummary key={`${change.failureCount}-${String(mismatch)}`} errors={summaryErrors} />
          ) : null}
          <FormField
            id="current-password"
            label="Current password"
            type="password"
            autoComplete="current-password"
            value={currentPassword}
            onChange={(event) => setCurrentPassword(event.target.value)}
            required
          />
          <FormField
            id="new-password"
            label="New password"
            type="password"
            help="At least 12 characters; avoid names and common words."
            autoComplete="new-password"
            value={newPassword}
            onChange={(event) => setNewPassword(event.target.value)}
            required
            error={newPasswordError}
          />
          <FormField
            id="confirm-password"
            label="Confirm new password"
            type="password"
            autoComplete="new-password"
            value={confirmPassword}
            onChange={(event) => setConfirmPassword(event.target.value)}
            required
          />
          <Button type="submit" loading={change.isPending}>
            Change password
          </Button>
        </form>
      </AdminSection>
    </AdminPage>
  );
}
