import { useEffect, useRef, useState } from "react";
import { api, type WatchListView } from "../api";
import { ChangeWatchScreen } from "./ChangeWatchScreen";
import { WatchListScreen } from "./changewatch/WatchListScreen";
import { GroupTabs } from "./layout";

type Which = "changes" | "watch-list";
const VIEWS: { key: Which; label: string }[] = [
  { key: "changes", label: "Changes" },
  { key: "watch-list", label: "Watch list" },
];

interface Props {
  planId: number;
  /** An item to open: a change's id, or a watch item's key (it has a "~": an advisory's id, then the library). */
  openItem?: string | null;
  /** "watch-list" opens the page on its second view (a link from the Overview or from Advisories). */
  section?: string | null;
}

const wants = (openItem: string | null, section: string | null): Which =>
  section === "watch-list" || (openItem !== null && openItem.includes("~")) ? "watch-list" : "changes";

/** The Change watch page. With Sandbox research off (the default) it is the Changes view exactly as before: no tabs,
 * nothing else drawn. With it on, the page has two views: Changes, and the Watch list (published weaknesses with no fix
 * yet). The backend says which. */
export function ChangeWatchPage({ planId, openItem = null, section = null }: Props) {
  const [watch, setWatch] = useState<WatchListView | null>(null);
  const [which, setWhich] = useState<Which>(wants(openItem, section));
  const asked = useRef(0);

  useEffect(() => setWhich(wants(openItem, section)), [openItem, section]);

  useEffect(() => {
    const mine = ++asked.current;
    setWatch(null);
    api
      .getWatchList(planId)
      .then((next) => {
        if (asked.current === mine) setWatch(next);
      })
      .catch(() => {
        // (a backend without the Watch list, or a read that failed: the page is the Changes view, as before)
        if (asked.current === mine) setWatch(null);
      });
    return () => {
      asked.current += 1;
    };
  }, [planId]);

  if (!watch?.on) return <ChangeWatchScreen planId={planId} openItem={openItem} />;
  const tabs = (
    <GroupTabs
      groups={VIEWS}
      active={which}
      onChoose={(key) => setWhich(key as Which)}
      idBase="change-watch-view"
      label="Views of Change watch"
    />
  );
  if (which === "changes")
    return <ChangeWatchScreen planId={planId} openItem={openItem?.includes("~") ? null : openItem} tabs={tabs} />;
  return (
    <WatchListScreen
      planId={planId}
      view={watch}
      onView={setWatch}
      openItem={openItem?.includes("~") ? openItem : null}
      tabs={tabs}
    />
  );
}
