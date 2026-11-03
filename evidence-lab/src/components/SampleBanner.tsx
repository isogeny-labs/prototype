import { Link } from "react-router-dom";
import { Marker } from "./Marker";

/** Persistent banner shown whenever sample data is loaded. */
export function SampleBanner({ projectName, devState }: { projectName?: string; devState?: string | null }) {
  return (
    <div role="status" data-testid="sample-banner" className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-sample/40 bg-sample/10 px-4 py-1.5 text-xs text-ink">
      <Marker kind="sample" />
      <span>
        Sample data is loaded{projectName ? <> for <strong>{projectName}</strong></> : null}. Every project, person, number and run is fictional and illustrative. No backend is connected.
      </span>
      {devState ? <span className="tag border-warn/60 text-warn" data-testid="dev-state-banner">Developer state: {devState.replace(/_/g, " ")}</span> : null}
      <Link to="/settings/sample-data" className="ml-auto underline">Sample data settings</Link>
    </div>
  );
}
