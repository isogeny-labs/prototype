import { Link } from "react-router-dom";
import { EmptyState, PageHeader } from "@/components";
export function NotFoundPage() {
  return (<><PageHeader title="Page not found" /><EmptyState title="There is nothing at this address." hint="Check the project id or the route." action={<Link className="btn-ghost btn-sm" to="/">Go home</Link>} /></>);
}
