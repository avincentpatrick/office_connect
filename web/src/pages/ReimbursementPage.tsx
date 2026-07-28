import { ReceiptText } from "lucide-react";
import { ListPage } from "../layouts/ListPage";

/**
 * Placeholder list for the Local Travel Reimbursement module — the claim
 * wizard and the module's first API endpoints land next session (R-2-wizard).
 */
export function ReimbursementPage() {
  return (
    <ListPage
      title="Travel claims"
      loading={false}
      isEmpty
      emptyState={{
        icon: ReceiptText,
        title: "Your travel claims will appear here",
        description:
          "Once the claim wizard opens you will be able to file a local travel reimbursement and track it through approval.",
      }}
    />
  );
}
