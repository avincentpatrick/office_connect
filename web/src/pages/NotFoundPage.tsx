import { Link } from "react-router";
import { Card } from "../components/Card/Card";

export function NotFoundPage() {
  return (
    <div className="mx-auto max-w-md pt-8">
      <Card title="Page not found">
        <p className="text-base text-text">
          This page does not exist or is not available to you.
        </p>
        <p className="mt-2">
          <Link
            to="/"
            className="text-base text-link underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
          >
            Go to the home page
          </Link>
        </p>
      </Card>
    </div>
  );
}
