import { createBrowserRouter, Outlet } from "react-router";
import { HomePage } from "../pages/HomePage";
import { LoginPage } from "../pages/LoginPage";
import { MfaSetupPage } from "../pages/MfaSetupPage";
import { MfaVerifyPage } from "../pages/MfaVerifyPage";
import { NotFoundPage } from "../pages/NotFoundPage";
import { PasswordChangePage } from "../pages/PasswordChangePage";
import { ClaimConfirmationPage } from "../pages/reimbursement/ClaimConfirmationPage";
import { ClaimPage } from "../pages/reimbursement/ClaimPage";
import { ItineraryStepPage } from "../pages/reimbursement/ItineraryStepPage";
import { MoneyStepPage } from "../pages/reimbursement/MoneyStepPage";
import { MyWorkPage } from "../pages/reimbursement/MyWorkPage";
import { ReviewStepPage } from "../pages/reimbursement/ReviewStepPage";
import { TripStepPage } from "../pages/reimbursement/TripStepPage";
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
        // The reimbursement branch (R-2-wizard): flag OFF renders NotFoundPage
        // in place for the whole subtree (fail-safe; flag is boot-fetched, so a
        // flip bites on reload).
        path: "/reimbursement",
        element: (
          <RequireFlag flag="module.reimbursement">
            <Outlet />
          </RequireFlag>
        ),
        children: [
          { index: true, element: <MyWorkPage /> },
          { path: "claims/:claimId", element: <ClaimPage /> },
          { path: "claims/:claimId/trip", element: <TripStepPage /> },
          { path: "claims/:claimId/itinerary", element: <ItineraryStepPage /> },
          { path: "claims/:claimId/money", element: <MoneyStepPage /> },
          { path: "claims/:claimId/review", element: <ReviewStepPage /> },
          { path: "claims/:claimId/confirmation", element: <ClaimConfirmationPage /> },
        ],
      },
      // DEV-only component catalog — statically eliminated from prod builds.
      ...(import.meta.env.DEV ? [{ path: "/ui-foundation", element: <UiFoundationPage /> }] : []),
      { path: "*", element: <NotFoundPage /> },
    ],
  },
]);
