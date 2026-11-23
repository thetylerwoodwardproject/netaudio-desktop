import { PageHeader } from "@/components/page-header"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Slider } from "@/components/ui/slider"

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-2 sm:grid-cols-[14rem_1fr] sm:items-center">
      <div><Label>{label}</Label>{hint && <p className="text-xs text-muted-foreground">{hint}</p>}</div>
      {children}
    </div>
  )
}

export function SettingsPage() {
  return (
    <>
      <PageHeader title="Settings" description="Network, audio and meter display. Nothing here changes a Dante device." actions={<Button>Save</Button>} />
      <div className="grid max-w-3xl gap-4">
        <Card>
          <CardHeader><CardTitle>Network and audio</CardTitle><CardDescription>Where levels are read from and where listening plays.</CardDescription></CardHeader>
          <CardContent className="grid gap-5">
            <Field label="Dante network adapter" hint="Used for metering and multicast joins.">
              <Select defaultValue="eth1"><SelectTrigger className="w-full"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="eth1">Ethernet 2 · 192.168.10.5</SelectItem><SelectItem value="eth0">Ethernet · 10.0.0.12</SelectItem></SelectContent></Select>
            </Field>
            <Field label="Output device">
              <Select defaultValue="spk"><SelectTrigger className="w-full"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="spk">Speakers (Realtek Audio)</SelectItem><SelectItem value="hp">Headphones (USB)</SelectItem></SelectContent></Select>
            </Field>
            <Field label="Listen buffer" hint="5–100 ms. Higher survives a busy network."><div className="flex items-center gap-3"><Slider defaultValue={[20]} min={5} max={100} /><span className="w-14 font-mono text-sm">20 ms</span></div></Field>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Meters</CardTitle><CardDescription>How levels are drawn.</CardDescription></CardHeader>
          <CardContent className="grid gap-5">
            <Field label="Peak hold"><div className="flex items-center gap-3"><Slider defaultValue={[2]} min={0} max={10} /><span className="w-14 font-mono text-sm">2 s</span></div></Field>
            <Field label="Refresh rate"><Select defaultValue="30"><SelectTrigger className="w-40"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="15">15 / s</SelectItem><SelectItem value="30">30 / s</SelectItem><SelectItem value="60">60 / s</SelectItem></SelectContent></Select></Field>
            <Field label="Amber from" hint="Green is below this."><Input defaultValue="−12" className="w-28 font-mono" /></Field>
            <Field label="Red from"><Input defaultValue="−3" className="w-28 font-mono" /></Field>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Daemon</CardTitle><CardDescription>The bundled netaudio-daemon runs in private mode.</CardDescription></CardHeader>
          <CardContent><Field label="Local port" hint="Localhost only."><Input defaultValue="auto" className="w-28 font-mono" /></Field></CardContent>
          <CardFooter className="text-xs text-muted-foreground">Metering stops when the app quits.</CardFooter>
        </Card>
      </div>
    </>
  )
}
