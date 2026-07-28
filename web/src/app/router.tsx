import { createBrowserRouter } from "react-router";
import { HomePage } from "../pages/HomePage";
import { LoginPage } from "../pages/LoginPage";
import { MfaSetupPage } from "../pages/MfaSetupPage";
import { MfaVerifyPage } from "../pages/MfaVerifyPage";
import { NotFoundPage } from "../pages/NotFoundPage";
import { PasswordChangePage } from "../pages/PasswordChangePage";
import { ReimbursementPage } from "../pages/ReimbursementPage";
import { UiFoundationPage } from "../pages/UiFoundationPage";
import { RequireAuth, RequireFlag } from "./guards";

export const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  { path: "/login/mfa", element: <MfaVerifyPage /> },
  {
    element: <RequireAuth />,
    children: [
      { path: "/", element: <HomePage /> },
      { path: "/account/password", element: <PasswordChangePage /> },
      { path: "/account/mfa", element: <MfaSetupPage /> },
      {
        path: "/reimbursement",
        element: (
          <RequireFlag flag="module.reimbursement">
            <ReimbursementPage />
          </RequireFlag>
        ),
      },
      // DEV-only component catalog — statically eliminated from prod builds.
      ...(import.meta.env.DEV ? [{ path: "/ui-foundation", element: <UiFoundationPage /> }] : []),
      { path: "*", element: <NotFoundPage /> },
    ],
  },
]);
