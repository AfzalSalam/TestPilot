import { Compass } from "lucide-react";
import { Link } from "react-router-dom";
import { EmptyState } from "@/components/ui/ui";

export default function NotFound() {
  return (
    <div className="page"><div className="card">
      <EmptyState icon={Compass} title="Page not found" action={<Link className="btn primary" to="/">Go to dashboard</Link>}>The page you're looking for doesn't exist.</EmptyState>
    </div></div>
  );
}
