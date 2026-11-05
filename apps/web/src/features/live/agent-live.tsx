"use client";

import { useQueryClient } from "@tanstack/react-query";
import * as React from "react";

import { useSocket, type SocketStatus } from "@/hooks/use-socket";
import { agentKeysFor, shouldSendTyping, socketUrl, type LiveEvent } from "@/lib/live-events";
import { useTyping } from "@/lib/store";
import { loginUrl } from "@/lib/auth-redirect";
import { qk } from "@/lib/query-keys";
import { toast } from "sonner";

interface LiveContextValue {
  status: SocketStatus;
  /** Tell the customer's widget that an agent is typing in this conversation. */
  sendTyping: (ticketId: string) => void;
}

const LiveContext = React.createContext<LiveContextValue>({ status: "idle", sendTyping: () => undefined });

/**
 * One agent WebSocket for the whole app (cookie auth, through the /ws rewrite). Each
 * event is an invalidation: the matching React Query keys refetch over REST, so a missed
 * event only delays an update. While the socket is down, lists fall back to polling
 * (see `useLivePolling`).
 */
export function AgentLiveProvider({ children }: { children: React.ReactNode }) {
  const client = useQueryClient();
  const markTyping = useTyping((s) => s.mark);
  const [url, setUrl] = React.useState<string | null>(null);
  React.useEffect(() => {
    setUrl(socketUrl("/ws/agent", window.location, process.env.NEXT_PUBLIC_WS_URL || null));
  }, []);
  const onEvent = React.useCallback(
    (event: LiveEvent) => {
      if (event.type === "typing" && event.who === "customer" && event.ticket_id) {
        markTyping(event.ticket_id);
        return;
      }
      for (const key of agentKeysFor(event)) void client.invalidateQueries({ queryKey: key });
    },
    [client, markTyping],
  );
  // 4401: the API refused the session (signed out elsewhere, revoked, or the agent was
  // disabled). Same outcome as a 401 on any request: back to sign in.
  const onRefused = React.useCallback(
    (code: number) => {
      if (code !== 4401 || typeof window === "undefined") return;
      const hadSession = !!client.getQueryData<{ user?: unknown }>(qk.me)?.user;
      client.clear();
      if (hadSession) toast.error("Your session ended. Sign in again.", { id: "session-expired" });
      window.location.assign(loginUrl(window.location.pathname, window.location.search, "expired"));
    },
    [client],
  );
  const { status, send } = useSocket(url, onEvent, onRefused);
  const lastTyping = React.useRef(0);
  const sendTyping = React.useCallback(
    (ticketId: string) => {
      const now = Date.now();
      if (!shouldSendTyping(lastTyping.current, now)) return;
      lastTyping.current = now;
      send({ type: "typing", ticket_id: ticketId });
    },
    [send],
  );
  const value = React.useMemo(() => ({ status, sendTyping }), [status, sendTyping]);
  return <LiveContext.Provider value={value}>{children}</LiveContext.Provider>;
}

export function useLive(): LiveContextValue {
  return React.useContext(LiveContext);
}

/** Poll interval for live views: none while the socket is open, 10 s while it is not. */
export function useLivePolling(): number | false {
  const { status } = useLive();
  return status === "open" ? false : 10_000;
}
