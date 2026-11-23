import * as React from "react"
import { Activity, Clock, Eye, GitBranch, Settings } from "lucide-react"

import { AppShell } from "@/components/app-shell"
import { ListenBar } from "@/components/listen-bar"
import { StatusPill } from "@/components/status-pill"
import { SidebarMenuButton, SidebarMenuItem } from "@/components/ui/sidebar"
import { useHashRoute } from "@/lib/use-hash-route"
import { AboutPage } from "@/screens/about"
import { ClockPage } from "@/screens/clock"
import { FlowsPage } from "@/screens/flows"
import { LevelsPage } from "@/screens/levels"
import { SettingsPage } from "@/screens/settings"

export default function App() {
  const [route, navigate] = useHashRoute("levels")
  const [listening, setListening] = React.useState("FOH-Console/tx/1–2")
  const page = route.split("/")[0]
  return (
    <AppShell
      brand={{ name: "NetAudio Monitor", context: "Dante network", icon: Activity }}
      groups={[{ label: "Monitor", items: [
        { id: "levels", label: "Levels", icon: Activity },
        { id: "flows", label: "Flows", icon: GitBranch },
        { id: "clock", label: "Clock", icon: Clock },
        { id: "settings", label: "Settings", icon: Settings },
      ] }]}
      route={route}
      onNavigate={navigate}
      version="2026.11.23"
      showThemeToggle={false}
      headerActions={<StatusPill tone="ok">Metering</StatusPill>}
      sidebarStatus={<>
        <SidebarMenuItem>
          <SidebarMenuButton tooltip="Read-only: never changes routing or settings"><Eye /><span>Read-only</span></SidebarMenuButton>
        </SidebarMenuItem>
        <SidebarMenuItem>
          <SidebarMenuButton tooltip="Ethernet 2 · 192.168.10.5">
            <span className="ml-1 size-2 shrink-0 rounded-full bg-success" /><span>Ethernet 2 · 192.168.10.5</span>
          </SidebarMenuButton>
        </SidebarMenuItem>
      </>}
      bottomBar={page === "levels" || page === "flows" ? <ListenBar source="Stage Mix (1–2)" detail="Existing multicast flow 239.255.12.4 · passive" left={-6.5} right={-7.0} extra={<span className="font-mono text-xs text-muted-foreground">≈ 40 ms</span>} /> : undefined}
    >
      {page === "levels" && <LevelsPage listening={listening} setListening={setListening} />}
      {page === "flows" && <FlowsPage />}
      {page === "clock" && <ClockPage />}
      {page === "settings" && <SettingsPage />}
      {page === "about" && <AboutPage />}
    </AppShell>
  )
}
