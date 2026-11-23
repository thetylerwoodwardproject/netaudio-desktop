import * as React from "react"
import { Activity, AlertTriangle, Clock, Headphones, Search, Volume2 } from "lucide-react"

import { FilterChips } from "@/components/filter-chips"
import { LevelMeter } from "@/components/level-meter"
import { PageHeader } from "@/components/page-header"
import { StatCard, StatGrid } from "@/components/stat-card"
import { StatusPill } from "@/components/status-pill"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Kbd } from "@/components/ui/kbd"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { DEVICES, chCount, maxDb, type Channel, type Device } from "@/data"

const FLOW_LABEL = { multicast: "Multicast", aes67: "AES67", unicast: "Unicast · levels only" } as const

function ChannelRow({ c, listening, onListen }: { c: Channel; listening: boolean; onListen: () => void }) {
  const canListen = c.flow !== "unicast"
  return (
    <div className="grid grid-cols-[2.25rem_minmax(0,1fr)_minmax(0,1.2fr)_2rem] items-center gap-3 py-2">
      <span className="font-mono text-xs text-muted-foreground tabular-nums">{c.n}</span>
      <div className="min-w-0 leading-tight">
        <div className="truncate text-sm">{c.name}</div>
        <div className="truncate font-mono text-[11px] text-muted-foreground">
          {c.source ?? `${FLOW_LABEL[c.flow]}${c.group ? ` · ${c.group}` : ""}`}
        </div>
      </div>
      {c.r ? (
        <div className="space-y-1">
          <LevelMeter label="L" db={c.db} peak={c.peak} clip={c.clip} note={c.muted ? "muted" : undefined} />
          <LevelMeter label="R" db={c.r.db} peak={c.r.peak} clip={c.r.clip} note={c.muted ? "muted" : undefined} />
        </div>
      ) : (
        <LevelMeter db={c.db} peak={c.peak} clip={c.clip} note={c.muted ? "muted" : undefined} />
      )}
      {canListen ? (
        <Button variant={listening ? "secondary" : "ghost"} size="icon" className="size-8" aria-label={`Listen to ${c.name}`} onClick={onListen}>
          <Headphones />
        </Button>
      ) : (
        <Tooltip>
          <TooltipTrigger asChild><span className="size-8" /></TooltipTrigger>
          <TooltipContent>Unicast flow: levels only</TooltipContent>
        </Tooltip>
      )}
    </div>
  )
}

function DeviceCard({ d, rows, listening, onListen }: { d: Device; rows: Channel[]; listening: string; onListen: (k: string) => void }) {
  const tx = rows.filter((c) => c.dir === "tx")
  const rx = rows.filter((c) => c.dir === "rx")
  return (
    <Card className="gap-3 py-4">
      <CardHeader className="px-4">
        <CardTitle className="flex items-center gap-2">{d.name}
          <StatusPill tone={d.clock === "unlocked" ? "bad" : "ok"}>{d.clock === "leader" ? "Clock leader" : d.clock === "locked" ? "Locked" : "Not locked"}</StatusPill>
        </CardTitle>
        <CardDescription className="font-mono text-xs">{d.model} · {d.ip} · {d.format}</CardDescription>
      </CardHeader>
      <CardContent className="px-4">
        {[["Transmit", tx], ["Receive", rx]].map(([label, list]) => (list as Channel[]).length > 0 && (
          <div key={label as string}>
            <div className="border-b pb-1 pt-2 text-[11px] font-medium tracking-wide text-muted-foreground uppercase">{label as string}</div>
            <div className="divide-y">
              {(list as Channel[]).map((c) => {
                const key = `${d.name}/${c.dir}/${c.n}`
                return <ChannelRow key={key} c={c} listening={listening === key} onListen={() => onListen(key)} />
              })}
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  )
}

export function LevelsPage({ listening, setListening }: { listening: string; setListening: (k: string) => void }) {
  const [filter, setFilter] = React.useState("all")
  const [q, setQ] = React.useState("")
  const all = DEVICES.flatMap((d) => d.channels)
  const total = (l: Channel[]) => l.reduce((n, c) => n + chCount(c), 0)
  const withSignal = all.filter((c) => c.db != null || c.r?.db != null)
  const hot = all.filter((c) => maxDb(c) > -12)
  const listenable = all.filter((c) => c.flow !== "unicast")
  const pass = (c: Channel) =>
    (filter === "all" || (filter === "signal" && (c.db != null || c.r?.db != null)) || (filter === "hot" && maxDb(c) > -12) || (filter === "listen" && c.flow !== "unicast")) &&
    (!q || `${c.name} ${c.source ?? ""}`.toLowerCase().includes(q.toLowerCase()))
  return (
    <>
      <PageHeader title="Levels" description="Live dBFS for every transmit and receive channel, as each device reports it." />
      <StatGrid>
        <StatCard label="Channels with signal" value={`${total(withSignal)} / ${total(all)}`} icon={Activity} footer="Across 3 devices" />
        <StatCard label="Loudest feed" value="−6.5 dBFS" icon={Volume2} footer="FOH-Console · 1–2 Stage Mix (L)" />
        <StatCard label="Clips, last 10 min" value="2" tone="bad" icon={AlertTriangle} footer="Stagebox-A · 3 Kick" />
        <StatCard label="Clock" value="Locked" tone="ok" icon={Clock} footer="Leader: FOH-Console" />
      </StatGrid>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <FilterChips value={filter} onChange={setFilter} chips={[
          { value: "all", label: "All channels", count: total(all) },
          { value: "signal", label: "With signal", count: total(withSignal) },
          { value: "hot", label: "Above −12 dBFS", count: total(hot) },
          { value: "listen", label: "Can listen", count: total(listenable) },
        ]} />
        <div className="relative w-full sm:w-64">
          <Search className="absolute top-2.5 left-2.5 size-4 text-muted-foreground" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search channels" className="pl-8" />
          <Kbd className="absolute top-2 right-2">Ctrl K</Kbd>
        </div>
      </div>
      <div className="grid grid-cols-[repeat(auto-fill,minmax(min(100%,440px),1fr))] gap-4 pb-4">
        {DEVICES.map((d) => (
          <DeviceCard key={d.name} d={d} rows={d.channels.filter(pass)} listening={listening} onListen={setListening} />
        ))}
      </div>
    </>
  )
}
