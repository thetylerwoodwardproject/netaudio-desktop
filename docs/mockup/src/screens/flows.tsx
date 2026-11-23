import { PageHeader } from "@/components/page-header"
import { StatCard, StatGrid } from "@/components/stat-card"
import { StatusPill } from "@/components/status-pill"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Card } from "@/components/ui/card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { FLOWS } from "@/data"
import { Info, Radio, Lock } from "lucide-react"

export function FlowsPage() {
  const listenable = FLOWS.filter((f) => f.listen).length
  return (
    <>
      <PageHeader title="Flows" description="Every multicast, AES67 and unicast flow on the network. NetAudio Monitor only reads them." />
      <StatGrid>
        <StatCard label="Can listen" value={listenable} icon={Radio} footer="Multicast and AES67 flows" />
        <StatCard label="Levels only" value={FLOWS.length - listenable} icon={Lock} footer="Unicast flows" />
      </StatGrid>
      <Card className="mb-4 py-2">
        <Table>
          <TableHeader>
            <TableRow>
              {["Source", "Channels", "Type", "Destination", "Format", "Levels", "Listen"].map((h) => <TableHead key={h} className="px-4">{h}</TableHead>)}
            </TableRow>
          </TableHeader>
          <TableBody>
            {FLOWS.map((f, i) => (
              <TableRow key={i}>
                <TableCell className="px-4 font-medium">{f.source}</TableCell>
                <TableCell className="px-4">{f.channels}</TableCell>
                <TableCell className="px-4"><StatusPill tone={f.listen ? "info" : "idle"} dot={false}>{f.type}</StatusPill></TableCell>
                <TableCell className="px-4 font-mono text-xs">{f.dest}</TableCell>
                <TableCell className="px-4 font-mono text-xs text-muted-foreground">{f.format}</TableCell>
                <TableCell className="px-4">Yes</TableCell>
                <TableCell className="px-4">{f.listen ? <StatusPill tone="ok">Yes</StatusPill> : <span className="text-muted-foreground">No</span>}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
      <Alert>
        <Info />
        <AlertTitle>Where the levels come from</AlertTitle>
        <AlertDescription>Levels are the meter values each device reports, the same ones Dante Controller shows. Listening joins an existing multicast or AES67 group like any other receiver; unicast flows can't be heard without changing routing, so they show levels only.</AlertDescription>
      </Alert>
    </>
  )
}
