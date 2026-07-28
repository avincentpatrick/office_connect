import { Card } from "../components/Card/Card";
import { StatusChip } from "../components/StatusChip/StatusChip";
import { useAuth } from "../app/providers/auth-context";
import { useConfig } from "../app/providers/config-context";

export function HomePage() {
  const { tenant } = useConfig();
  const { me } = useAuth();

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-bold text-text">Welcome to {tenant.name}</h1>
      <Card title="Your account" status={<StatusChip status="done">Signed in</StatusChip>}>
        <dl className="flex flex-col gap-2">
          <div>
            <dt className="text-sm font-medium text-text-muted">Email</dt>
            <dd className="text-base text-text">{me?.email}</dd>
          </div>
          <div>
            <dt className="text-sm font-medium text-text-muted">Roles</dt>
            <dd className="text-base text-text">
              {me && me.roles.length > 0 ? me.roles.join(", ") : "No roles assigned yet"}
            </dd>
          </div>
        </dl>
      </Card>
      <p className="text-base text-text-muted">
        Use the navigation above to open a module. Modules appear as they are enabled for your
        tenant.
      </p>
    </div>
  );
}
